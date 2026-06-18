"""Common utilities for enterprise modules.

Extracts repeated patterns across features/observability/security/evaluation/
cost/reliability/knowledge/ai_platform/integration modules.
"""
import asyncio as _asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import TypeVar, Type, Sequence

import structlog as _structlog
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def utc_now_iso() -> str:
    """UTC timestamp in ISO format. Replaces deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).isoformat()


def mask_secret(value: str | None, show_chars: int = 4) -> str | None:
    """Mask sensitive string for API responses.

    Examples:
        mask_secret("sk-abcdefgh") -> "sk-a****"
        mask_secret(None) -> None
        mask_secret("abc") -> "****" (too short to show prefix)
    """
    if not value:
        return value
    if len(value) <= show_chars:
        return "****"
    return value[:show_chars] + "****"


def deterministic_hash(seed: str, modulo: int = 100) -> int:
    """Cross-process deterministic hash. Replaces builtin hash().

    Uses MD5 for speed; collision resistance not needed for feature flags.
    """
    return int(hashlib.md5(seed.encode()).hexdigest(), 16) % modulo


def rows_to_models(rows: Sequence, model_class: Type[T]) -> list[T]:
    """Convert sqlite3.Row objects to Pydantic models."""
    return [model_class(**dict(row)) for row in rows]


# ── FastAPI shared constants ──

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def require_llm_key():
    """FastAPI dependency: raise 503 if no LLM API key is configured."""
    from fastapi import HTTPException
    from app.config import settings

    if not settings.llm_api_key and not settings.fallback_api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM API key not configured. Set LLM_API_KEY or FALLBACK_API_KEY.",
        )


def sse_event(data: dict) -> str:
    """Format a dict as an SSE data event string."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Fire-and-forget background task utility ──

_bg_logger = _structlog.get_logger(__name__)
_background_tasks: set = set()


def fire_and_forget(coro, *, name: str = "") -> None:
    """Safe fire-and-forget: preserve task reference + exception callback.

    Per Python docs: "Save a reference to the result of create_task,
    to avoid a task disappearing mid-execution."

    Replaces `try: asyncio.create_task(...) except Exception: pass` pattern.
    """
    try:
        task = _asyncio.create_task(coro, name=name)
    except RuntimeError:
        _bg_logger.warning("fire_and_forget_no_running_loop", task_name=name)
        coro.close()
        return

    _background_tasks.add(task)

    def _on_done(t: _asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            _bg_logger.error(
                "background_task_failed",
                task_name=name,
                error_type=type(exc).__name__,
                error=str(exc),
            )

    task.add_done_callback(_on_done)
