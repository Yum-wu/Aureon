"""Concurrency rate limiting for LLM API and RAG pipeline.

Uses asyncio.Semaphore to prevent thundering herd when many concurrent
requests hit the same LLM API or RAG pipeline. Each model gets its own
semaphore so different providers don't block each other.

Based on RAG_OPTIMIZATION_PROMPT.md §5.3.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Dict

import structlog

logger = structlog.get_logger()

# ── Configuration ──

QUEUE_TIMEOUT_SECONDS = float(os.getenv("QUEUE_TIMEOUT_SECONDS", "30"))

# LLM API semaphores (per model)
_LLM_SEMAPHORES: Dict[str, asyncio.Semaphore] = {
    "deepseek-chat": asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_DEEPSEEK", "30"))),
    "deepseek-reasoner": asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_REASONER", "10"))),
    "dashscope-embedding": asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_EMBEDDING", "50"))),
}

# RAG pipeline semaphore (vector retrieval + rerank)
_RAG_SEMAPHORE = asyncio.Semaphore(int(os.getenv("RAG_SEMAPHORE", "40")))

# Default semaphore for unknown models
_DEFAULT_LLM_SEMAPHORE = asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_DEFAULT", "20")))


@asynccontextmanager
async def llm_call_with_semaphore(model: str):
    """Rate-limit LLM API calls by model.

    Usage:
        async with llm_call_with_semaphore("deepseek-chat"):
            result = await llm.ainvoke(prompt)
    """
    sem = _LLM_SEMAPHORES.get(model, _DEFAULT_LLM_SEMAPHORE)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        from fastapi import HTTPException
        logger.warning("LLM semaphore timeout", model=model, timeout=QUEUE_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=503,
            detail="System busy. Please try again later.",
        )
    try:
        yield
    finally:
        sem.release()


@asynccontextmanager
async def rag_pipeline_semaphore():
    """Rate-limit RAG pipeline calls.

    Usage:
        async with rag_pipeline_semaphore():
            chunks = await hybrid_retrieve(query)
    """
    try:
        await asyncio.wait_for(_RAG_SEMAPHORE.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        from fastapi import HTTPException
        logger.warning("RAG pipeline semaphore timeout", timeout=QUEUE_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline busy. Please try again later.",
        )
    try:
        yield
    finally:
        _RAG_SEMAPHORE.release()


def get_concurrency_stats() -> dict:
    """Return current concurrency statistics for monitoring."""
    return {
        "llm_semaphores": {
            model: {"limit": sem._value, "available": sem._value}
            for model, sem in _LLM_SEMAPHORES.items()
        },
        "rag_semaphore_available": _RAG_SEMAPHORE._value,
        "queue_timeout_seconds": QUEUE_TIMEOUT_SECONDS,
    }
