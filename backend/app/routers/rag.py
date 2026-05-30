"""RAG router -- extracted from main.py.

Routes:
  POST /api/rag/query           -- RAG query with Redis cache
  POST /api/rag/query/stream    -- Streaming RAG query (SSE)
  POST /api/rag/index           -- Re-index all articles
  POST /api/rag/upload          -- Upload document and index
  GET  /api/rag/uploads         -- List uploaded files
  DELETE /api/rag/upload/{fn}   -- Delete uploaded file
  POST /api/rag/evaluate        -- Run RAG evaluation
  POST /api/rag/experiment      -- Run prompt experiment
  GET  /api/rag/health          -- RAG health check
  GET  /api/rag/benchmark       -- Benchmark results
"""

import asyncio
import json
import logging
import os
import sys
import time

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from app.api.models import StatusResponse
from app.api.rag_stats import record_query
from app.config import settings
from app.rag.models import (
    RAGQueryRequest,
    RAGQueryResponse,
    RAGIndexResponse,
    RAGUploadResponse,
)
from app.rag.qa_chain import (
    rag_query_with_cache,
    rag_query_astream,
    run_index_pipeline,
    run_incremental_index,
)
from app.rag.evaluator import run_full_evaluation
from app.rag.prompt_experiment import run_experiment, STRATEGIES
from app.rag.test_data import TEST_QA_PAIRS
from app.rag.vector_store import retrieve

logger = structlog.get_logger()

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _validate_filename(filename: str) -> str:
    """Validate filename for path traversal attacks."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename

# Module constants for data paths
BASE_DATA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
ARTICLES_DIR = os.path.join(BASE_DATA_DIR, "data", "articles")
UPLOADS_DIR = os.path.join(ARTICLES_DIR, "uploads")


@router.post("/api/rag/query", response_model=RAGQueryResponse)
@limiter.limit("2/second")
async def rag_query_endpoint(req: RAGQueryRequest, request: Request):
    """RAG query: retrieve context + generate answer (with Redis cache)."""
    from app.agent.llm import create_llm
    from app.config import settings

    # Check if LLM API key is configured
    if not settings.llm_api_key and not settings.fallback_api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM API key not configured. Please set LLM_API_KEY or FALLBACK_API_KEY environment variable."
        )

    llm = create_llm()

    def _llm_call(messages):
        response = llm.invoke(messages)
        return response.content

    start_time = time.time()
    result = await rag_query_with_cache(
        req.query, _llm_call, top_k=req.top_k, use_mmr=req.use_mmr
    )
    latency_ms = int((time.time() - start_time) * 1000)
    # Record query for Dashboard stats (fire-and-forget)
    asyncio.create_task(record_query(req.query, len(result.sources), latency_ms))
    return result


@router.post("/api/rag/query/stream")
@limiter.limit("2/second")
async def rag_query_stream_endpoint(req: RAGQueryRequest, request: Request):
    """Streaming RAG: buffered SSE + Redis cache layer."""
    from app.agent.llm import create_llm
    from app.cache.redis_client import get_cached, set_cached
    from app.config import settings

    # Check if LLM API key is configured
    if not settings.llm_api_key and not settings.fallback_api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM API key not configured. Please set LLM_API_KEY or FALLBACK_API_KEY environment variable."
        )

    llm = create_llm()

    async def _buffer_events(generator, flush_interval=0.05, max_chars=200):
        """Buffer text events, flush at interval or max_chars.

        - First text event: flush immediately (zero TTFT impact)
        - Subsequent: buffer at 50ms / 200 chars for smooth streaming
        - Non-text events: flush pending text first, pass through
        """
        buf = ""
        last_flush = 0.0
        is_first = True
        async for event in generator:
            if event.get("type") == "text":
                buf += event["content"]
                now = time.monotonic()
                if not last_flush:
                    last_flush = now
                # Flush first event immediately to keep TTFT low
                if is_first:
                    is_first = False
                    yield {"type": "text", "content": buf}
                    buf = ""
                    last_flush = now
                elif (now - last_flush) >= flush_interval or len(buf) >= max_chars:
                    yield {"type": "text", "content": buf}
                    buf = ""
                    last_flush = now
            else:
                if buf:
                    yield {"type": "text", "content": buf}
                    buf = ""
                    last_flush = 0.0
                yield event
        if buf:
            yield {"type": "text", "content": buf}

    async def event_stream():
        start_time = time.time()
        sources_count = 0
        input_tokens = 0
        output_tokens = 0
        # 1. Try Redis cache hit (JSON format with sources)
        cached = await get_cached(req.query)
        if cached is not None:
            try:
                cached_data = json.loads(cached)
                answer_text = cached_data.get("answer", cached)
                cached_sources = cached_data.get("sources", [])
            except (json.JSONDecodeError, TypeError):
                answer_text = cached
                cached_sources = []
            yield f"data: {json.dumps({'type': 'sources', 'sources': cached_sources}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'text', 'content': answer_text}, ensure_ascii=False)}\n\n"
            yield 'data: {"type": "cache_hit"}\n\n'
            latency_ms = int((time.time() - start_time) * 1000)
            asyncio.create_task(record_query(req.query, len(cached_sources), latency_ms))
            return

        # 2. Stream with buffering, auto-cache full answer on completion
        full_text = ""
        sources_data = []
        try:
            raw_gen = rag_query_astream(
                req.query, llm, top_k=req.top_k, use_mmr=req.use_mmr
            )
            async for event in _buffer_events(raw_gen):
                if event.get("type") == "text":
                    full_text += event["content"]
                    output_tokens = len(full_text) // 2
                elif event.get("type") == "sources":
                    sources_count = len(event.get("sources", []))
                    sources_data = event.get("sources", [])
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # 3. Cache as JSON (answer + sources) for cross-endpoint compatibility
            if full_text:
                cache_payload = json.dumps({"answer": full_text, "sources": sources_data}, ensure_ascii=False)
                asyncio.create_task(set_cached(req.query, cache_payload))
            # 4. Record query for Dashboard stats
            latency_ms = int((time.time() - start_time) * 1000)
            input_tokens = len(req.query) + 500
            asyncio.create_task(record_query(
                req.query, sources_count, latency_ms,
                input_tokens=input_tokens, output_tokens=output_tokens
            ))
            yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/rag/index", response_model=RAGIndexResponse)
@limiter.limit("1/second")
async def rag_index_endpoint(request: Request):
    """Re-index all articles into Chroma."""
    result = run_index_pipeline(ARTICLES_DIR)
    return result


@router.post("/api/rag/upload", response_model=RAGUploadResponse)
async def rag_upload_endpoint(
    file: UploadFile = File(...),
    language: str = Form(None),
    title: str = Form(None),
    api_key: str = Form(None),
):
    """Upload a .md or .txt file and incrementally index it.

    Args:
        file: 上传的文件
        language: 文档语言（"zh" 或 "en"），可选
        title: 文档标题，可选
        api_key: API Key（用于博客同步认证），可选
    """
    # 验证 API Key（如果配置了）
    expected_key = os.getenv("BLOG_SYNC_API_KEY")
    if expected_key and api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    import shutil

    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")

    # Security: prevent path traversal
    _validate_filename(file.filename)

    # Sanitize filename
    safe_filename = os.path.basename(file.filename)

    # Validate extension
    allowed = {".md", ".txt"}
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}, only {', '.join(allowed)}",
        )

    # Save to uploads directory
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    dest = os.path.join(UPLOADS_DIR, safe_filename)

    try:
        content = await file.read()
        with open(dest, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {str(e)}")

    # Incremental index
    result = run_incremental_index(dest)

    # Update metadata with provided language and title
    if language in ("zh", "en") and result.get("metadata"):
        result["metadata"]["language"] = language
    if title and result.get("metadata"):
        result["metadata"]["title"] = title

    if result["status"] == "error":
        raise HTTPException(
            status_code=500, detail=result.get("message", "Index failed")
        )

    return result


@router.get("/api/rag/uploads")
async def rag_list_uploads():
    """List all uploaded files in the uploads directory."""
    if not os.path.isdir(UPLOADS_DIR):
        return {"files": []}
    files = sorted(
        (
            {
                "filename": f,
                "size": os.path.getsize(os.path.join(UPLOADS_DIR, f)),
            }
            for f in os.listdir(UPLOADS_DIR)
            if os.path.isfile(os.path.join(UPLOADS_DIR, f))
        ),
        key=lambda x: x["filename"],
    )
    return {"files": files}


@router.delete("/api/rag/upload/{filename}", response_model=StatusResponse)
async def rag_delete_upload(filename: str):
    """Delete an uploaded file and its chunks from the index."""
    # Security: prevent path traversal
    _validate_filename(filename)

    filepath = os.path.join(UPLOADS_DIR, filename)

    # 1. Remove from Chroma index
    from app.rag.vector_store import delete_from_index

    delete_from_index(filename)

    # 2. Delete physical file
    if os.path.isfile(filepath):
        os.remove(filepath)
        logger.info("Deleted uploaded file", path=filepath)
    else:
        logger.warning("File not found on disk (already deleted)", path=filepath)

    return StatusResponse(status="deleted", session_id=filename)


@router.post("/api/rag/evaluate")
async def rag_evaluate_endpoint():
    """Run full RAG evaluation: Recall@k, Faithfulness, Latency."""
    from app.agent.llm import create_llm

    llm = create_llm(streaming=False)

    def _retrieve(q: str, top_k: int = 3):
        return retrieve(q, top_k=top_k)

    def _rag_query(q: str):
        from app.rag.qa_chain import rag_query as rq

        def llm_call(messages):
            return llm.invoke(messages).content

        return rq(q, llm_call)

    result = run_full_evaluation(_retrieve, _rag_query, llm)
    return result


@router.post("/api/rag/experiment")
async def rag_experiment_endpoint():
    """Run prompt strategy experiment on test dataset."""
    from app.agent.llm import create_llm

    llm = create_llm(streaming=False)

    def _rag_query(q: str):
        from app.rag.qa_chain import rag_query as rq

        def llm_call(messages):
            return llm.invoke(messages).content

        return rq(q, llm_call)

    result = run_experiment(TEST_QA_PAIRS, _rag_query, llm)
    return result


@router.get("/api/rag/health")
async def rag_health():
    """RAG system health + live service status."""
    from app.rag.vector_store import get_bm25_stats

    bm25 = get_bm25_stats()
    return {
        "status": "ok",
        "llm_configured": bool(settings.llm_api_key),
        "model": settings.llm_model,
        "fallback_configured": bool(settings.fallback_api_key),
        "index_status": "ok" if os.path.isdir(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "vectors"))
        ) else "not_initialized",
        "test_qa_pairs": len(TEST_QA_PAIRS),
        "streaming_retrieval": "BM25 keyword (in-memory)",
        "bm25_docs": bm25["docs"],
        "bm25_terms": bm25["terms"],
        "sync_retrieval": "Chroma dense (BGE local embedding)",
        "hybrid_search_enabled": True,
        "guardrails_enabled": True,
        "langsmith_enabled": bool(
            settings.langchain_api_key or os.getenv("LANGCHAIN_API_KEY")
        ),
    }


@router.get("/api/rag/benchmark")
async def rag_benchmark():
    """Latest RAG evaluation benchmark results."""
    benchmark_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "benchmark_results.json"
    )
    if not os.path.isfile(benchmark_path):
        return {"metrics": [], "services": {}, "timestamp": None}
    with open(benchmark_path, encoding="utf-8") as f:
        return json.load(f)
