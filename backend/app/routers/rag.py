"""RAG router -- extracted from main.py.

Routes:
  POST /query           -- RAG query with Redis cache
  POST /query/stream    -- Streaming RAG query (SSE)
  POST /index           -- Re-index all articles
  POST /upload          -- Upload document and index
  GET  /uploads         -- List uploaded files
  DELETE /upload/{fn}   -- Delete uploaded file
  POST /evaluate        -- Run RAG evaluation
  POST /experiment      -- Run prompt experiment
  GET  /health          -- RAG health check
  GET  /benchmark       -- Benchmark results
"""

import json
import os
import time

from fastapi import APIRouter, Request, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from app.api.models import StatusResponse
from app.api.rag_stats import record_query
from app.config import settings
from app.dependencies import get_redis_or_none
from app.common import SSE_HEADERS, sse_event, fire_and_forget
from app.exceptions import (
    LLMServiceError,
    AuthenticationError,
    AureonException,
)
from app.security import UserRole, require_role
from app.rag.models import (
    RAGQueryRequest,
    RAGQueryResponse,
    RAGIndexResponse,
    RAGUploadResponse,
)
from app.rag.qa_chain import (
    rag_query_with_cache,
    rag_query_astream,
    rag_query_async,
    run_index_pipeline,
    run_incremental_index,
)
from app.rag.evaluator import run_full_evaluation
from app.rag.prompt_experiment import run_experiment
from app.rag.test_data import TEST_QA_PAIRS
from app.rag.vector_store import retrieve, get_bm25_stats
from app.audit.decorator import audit_action
from app.multi_tenant.middleware import get_current_tenant_id

logger = structlog.get_logger()

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _record_dashboard_metrics(
    *,
    latency_ms: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cache_hit: bool = False,
    error: bool = False,
) -> None:
    """Fire-and-forget: 将查询指标写入 Dashboard 实时指标采集器 + Cost 服务。

    TTFT 近似为总延迟（首 token 与最后 token 差异在流式中无法精确测量），
    TPOT 近似为 latency / output_tokens。
    """
    # 1. Dashboard 实时指标（独立 try-except，失败不影响成本记录）
    try:
        from app.observability.metrics_collector import get_metrics_collector
        from app.multi_tenant.middleware import get_current_tenant_id

        collector = get_metrics_collector()
        tenant_id = get_current_tenant_id()
        tpot_ms = (latency_ms / max(tokens_out, 1)) if tokens_out > 0 else latency_ms
        fire_and_forget(
            collector.record_query_metrics(
                tenant_id=tenant_id,
                ttft_ms=latency_ms,
                tpot_ms=tpot_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=settings.llm_model,
                cache_hit=cache_hit,
                error=error,
            ),
            name="record_dashboard_metrics",
        )
    except Exception as exc:
        logger.debug("dashboard_metrics_record_skipped", error=str(exc))

    # 2. 成本数据（独立 try-except，不受 Dashboard 指标失败影响）
    if tokens_in > 0 or tokens_out > 0:
        try:
            from app.cost.service import get_cost_service
            from app.cost.models import TokenUsage
            from app.multi_tenant.middleware import get_current_tenant_id

            cost_service = get_cost_service()
            tenant_id = get_current_tenant_id()
            cost_usd = round(
                (tokens_in / 1000 * 0.00015) + (tokens_out / 1000 * 0.0006),
                6,
            )
            fire_and_forget(
                cost_service.record_usage(TokenUsage(
                    tenant_id=tenant_id,
                    model=settings.llm_model,
                    input_tokens=tokens_in,
                    output_tokens=tokens_out,
                    cost_usd=cost_usd,
                )),
                name="record_cost_usage",
            )
        except Exception as exc:
            logger.debug("cost_record_skipped", error=str(exc))


def _validate_filename(filename: str) -> str:
    """Validate filename against path traversal attacks.

    Defense chain (OWASP File Upload Cheat Sheet):
    1. basename strips path separators
    2. Character whitelist check
    3. Length limit
    4. No leading dots (hidden files) or double dots
    """
    if not filename or len(filename) > 255:
        raise AureonException(status_code=400, detail="Invalid filename length")

    # Step 1: basename (strip any path)
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        raise AureonException(status_code=400, detail="Filename must not contain path separators")

    # Step 2: no leading dots or double dots
    if safe_name.startswith(".") or ".." in safe_name:
        raise AureonException(status_code=400, detail="Invalid filename")

    # Step 3: character whitelist (alphanumeric + hyphens + underscores + dots + CJK + spaces)
    import re
    if not re.match(r"^[a-zA-Z0-9\-_.\u4e00-\u9fa5 ]+$", safe_name):
        raise AureonException(status_code=400, detail="Filename contains invalid characters")

    return safe_name


def _safe_storage_path(filename: str) -> str:
    """Generate safe storage path with resolve() + prefix check.

    Per FASTAPI-FILES-001: must not pass user-controlled paths
    to filesystem without strict validation and safe base directories.
    """
    safe_name = _validate_filename(filename)
    from pathlib import Path
    uploads_resolved = Path(UPLOADS_DIR).resolve()
    target = (uploads_resolved / safe_name).resolve()
    if not str(target).startswith(str(uploads_resolved) + os.sep):
        raise AureonException(status_code=400, detail="Path traversal detected")
    return str(target)

# Module constants for data paths
BASE_DATA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
ARTICLES_DIR = os.path.join(BASE_DATA_DIR, "data", "articles")
UPLOADS_DIR = os.path.join(ARTICLES_DIR, "uploads")


async def _ensure_index_ready() -> bool:
    """Check if RAG index is ready.

    Returns True if index has data, False if empty/stale.
    Does NOT trigger rebuild (to avoid OOM on Railway).
    Use POST /api/rag/index to manually rebuild.
    """
    from app.rag.vector_store import get_collection_stats

    doc_count, _ = get_collection_stats()
    if doc_count > 0:
        return True

    logger.warning("RAG index is empty — queries will lack RAG context. "
                   "Call POST /api/rag/index to build.")
    return False


@router.post("/query", response_model=RAGQueryResponse)
@limiter.limit("2/second")
async def rag_query_endpoint(req: RAGQueryRequest, request: Request):
    """RAG query: retrieve context + generate answer (with Redis cache)."""
    from app.agent.llm import create_llm
    from app.config import settings

    # Check if LLM API key is configured
    if not settings.llm_api_key and not settings.fallback_api_key:
        raise LLMServiceError(
            detail="LLM API key not configured. Please set LLM_API_KEY or FALLBACK_API_KEY environment variable."
        )

    # Log index status (non-blocking)
    await _ensure_index_ready()

    llm = create_llm(model=req.model, streaming=False)

    def _llm_call(messages):
        try:
            response = llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error("LLM invoke failed: %s", e)
            raise LLMServiceError(detail=f"LLM service error: {str(e)[:100]}")

    start_time = time.time()
    try:
        result = await rag_query_with_cache(
            req.query, _llm_call, top_k=req.top_k, use_mmr=req.use_mmr,
            filter_lang=req.language,
        )
    except AureonException:
        latency_ms = int((time.time() - start_time) * 1000)
        fire_and_forget(record_query(req.query, 0, latency_ms), name="record_query_error")
        raise
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        fire_and_forget(record_query(req.query, 0, latency_ms), name="record_query_error")
        logger.error("rag_query_with_cache failed: %s", e)
        raise AureonException(status_code=500, detail=f"Query processing error: {str(e)[:100]}")
    latency_ms = int((time.time() - start_time) * 1000)
    # Record query for Dashboard stats (fire-and-forget)
    input_tokens = len(req.query) + 500
    output_tokens = len(result.answer) // 2 if hasattr(result, 'answer') else 0
    fire_and_forget(record_query(req.query, len(result.sources), latency_ms,
                                  input_tokens=input_tokens, output_tokens=output_tokens),
                    name="record_query")
    _record_dashboard_metrics(latency_ms=latency_ms, tokens_out=output_tokens)
    return result


@router.post("/query/async", response_model=RAGQueryResponse)
@limiter.limit("2/second")
async def rag_query_async_endpoint(req: RAGQueryRequest, request: Request):
    """Async RAG query with parallel BM25 + vector retrieval."""
    import uuid
    from app.agent.llm import create_llm

    if not settings.llm_api_key and not settings.fallback_api_key:
        raise LLMServiceError(
            detail="LLM API key not configured. Please set LLM_API_KEY or FALLBACK_API_KEY environment variable."
        )

    # Generate request_id for tracing
    request_id = str(uuid.uuid4())[:8]

    llm = create_llm(model=req.model, streaming=False)

    async def llm_call(messages):
        return (await llm.ainvoke(messages)).content

    start_time = time.time()
    try:
        result = await rag_query_async(
            query=req.query,
            llm_call_fn=llm_call,
            top_k=req.top_k or 3,
            lang=None,  # 让 rag_query_async 自动检测语言
            filter_lang=req.language,
            request_id=request_id,
        )
    except AureonException:
        raise
    except Exception as e:
        logger.error("rag_query_async failed: %s", e)
        raise AureonException(status_code=500, detail=f"Query processing error: {str(e)[:100]}")

    latency_ms = int((time.time() - start_time) * 1000)
    input_tokens = len(req.query) + 500
    output_tokens = len(result.answer) // 2 if hasattr(result, 'answer') else 0
    fire_and_forget(record_query(req.query, len(result.sources), latency_ms,
                                  input_tokens=input_tokens, output_tokens=output_tokens),
                    name="record_query_async")
    _record_dashboard_metrics(latency_ms=latency_ms, tokens_out=output_tokens)
    return result


@router.post("/query/stream")
@limiter.limit("2/second")
async def rag_query_stream_endpoint(req: RAGQueryRequest, request: Request):
    """Streaming RAG: buffered SSE + Redis cache layer."""
    from app.agent.llm import create_llm
    from app.cache.redis_client import get_cached, set_cached
    from app.config import settings

    # Check if LLM API key is configured
    if not settings.llm_api_key and not settings.fallback_api_key:
        raise LLMServiceError(
            detail="LLM API key not configured. Please set LLM_API_KEY or FALLBACK_API_KEY environment variable."
        )

    # Log index status (non-blocking)
    await _ensure_index_ready()

    llm = create_llm(model=req.model)

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
        import uuid
        start_time = time.time()
        sources_count = 0
        input_tokens = 0
        output_tokens = 0
        # Generate request_id for tracing
        request_id = str(uuid.uuid4())[:8]

        # 1. Try Redis cache hit (JSON format with sources)
        cached = await get_cached(req.query)
        if cached is not None:
            # Cache hit - record stats
            try:
                redis = get_redis_or_none()
                if redis:
                    await redis.incr("aureon:stats:cache_hits")
            except Exception as e:
                logger.debug("cache_hit_stats_increment_failed", error=str(e))

            try:
                cached_data = json.loads(cached)
                answer_text = cached_data.get("answer", cached)
                cached_sources = cached_data.get("sources", [])
            except (json.JSONDecodeError, TypeError):
                answer_text = cached
                cached_sources = []
            yield sse_event({'type': 'request_id', 'request_id': request_id})
            yield sse_event({'type': 'sources', 'sources': cached_sources})
            yield sse_event({'type': 'text', 'content': answer_text})
            yield sse_event({'type': 'cache_hit'})
            latency_ms = int((time.time() - start_time) * 1000)
            fire_and_forget(record_query(req.query, len(cached_sources), latency_ms), name="record_query_stream_cached")
            _record_dashboard_metrics(latency_ms=latency_ms, cache_hit=True)
            return

        # Cache miss - record stats
        try:
            redis = get_redis_or_none()
            if redis:
                await redis.incr("aureon:stats:cache_misses")
        except Exception as e:
            logger.debug("cache_miss_stats_increment_failed", error=str(e))

        # 2. Stream with buffering, auto-cache full answer on completion
        full_text = ""
        sources_data = []

        # Emit request_id event for tracing
        yield sse_event({'type': 'request_id', 'request_id': request_id})

        try:
            raw_gen = rag_query_astream(
                req.query, llm, top_k=req.top_k, use_mmr=req.use_mmr,
                filter_lang=req.language,
            )
            async for event in _buffer_events(raw_gen):
                if event.get("type") == "text":
                    full_text += event["content"]
                    output_tokens = len(full_text) // 2
                elif event.get("type") == "sources":
                    sources_count = len(event.get("sources", []))
                    sources_data = event.get("sources", [])
                yield sse_event(event)
        except Exception as e:
            yield sse_event({'type': 'error', 'content': str(e)})
        else:
            # Send done event only if stream completed normally (not on disconnect)
            yield sse_event({'type': 'done'})
        finally:
            # 3. Cache as JSON (answer + sources) for cross-endpoint compatibility
            from app.rag.vector_store import _kw_indexes as _bm25_indexes
            if full_text and len(_bm25_indexes.get("default", {}).get("docs", [])) > 0:
                cache_payload = json.dumps({"answer": full_text, "sources": sources_data}, ensure_ascii=False)
                fire_and_forget(set_cached(req.query, cache_payload), name="set_cached")
            # 4. Record query for Dashboard stats
            latency_ms = int((time.time() - start_time) * 1000)
            input_tokens = len(req.query) + 500
            fire_and_forget(record_query(
                req.query, sources_count, latency_ms,
                input_tokens=input_tokens, output_tokens=output_tokens
            ), name="record_query_stream")
            _record_dashboard_metrics(
                latency_ms=latency_ms,
                tokens_in=input_tokens,
                tokens_out=output_tokens,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/index", response_model=RAGIndexResponse)
@limiter.limit("1/second")
@audit_action("index", "index")
async def rag_index_endpoint(request: Request, user=Depends(require_role(UserRole.EDITOR))):
    """Re-index all articles into Qdrant + clear caches + rebuild BM25.

    Requires EDITOR role or higher.
    When Contextual Retrieval is enabled (default), each chunk gets an
    LLM-generated context prefix before embedding.
    """
    from app.agent.llm import create_llm

    # Get tenant_id from current context
    tenant_id = get_current_tenant_id()

    llm = create_llm(temperature=0.0, streaming=False)
    def llm_call_fn(msgs):
        return llm.invoke(msgs).content

    result = await run_index_pipeline(ARTICLES_DIR, llm_call_fn=llm_call_fn, enable_contextual=True)

    # Add tenant_id to result metadata if available
    if result.get("metadata"):
        result["metadata"]["tenant_id"] = tenant_id
    elif result.get("status") == "success":
        result["metadata"] = {"tenant_id": tenant_id}

    # Clear all caches so fresh results are served
    from app.cache.redis_client import clear_cache_by_prefix, _mem_cache
    _mem_cache.clear()
    await clear_cache_by_prefix("llm_cache:")

    # Force BM25 rebuild from Qdrant
    from app.rag.vector_store import _build_kw_index
    _build_kw_index(force=True)

    return result


@router.get("/index/status")
async def rag_index_status():
    """Check index health: file count vs indexed count, staleness."""
    from app.rag.vector_store import check_index_stale, get_collection_stats
    from app.config import settings

    status = check_index_stale(ARTICLES_DIR)
    doc_count, chunk_count = get_collection_stats()

    return {
        "index_ready": status["stale"] is False,
        "stale": status["stale"],
        "reason": status["reason"],
        "articles_on_disk": status["fs_count"],
        "docs_indexed": doc_count,
        "chunks_indexed": chunk_count,
        "missing_files": status["missing_files"],
        "auto_index_enabled": settings.auto_index_enabled,
    }


@router.post("/upload", response_model=RAGUploadResponse)
@audit_action("upload", "document")
async def rag_upload_endpoint(
    file: UploadFile = File(...),
    language: str = Form(None),
    title: str = Form(None),
    api_key: str = Form(None),
    request: Request = None,
    user=Depends(require_role(UserRole.EDITOR)),
):
    """Upload a document (.md, .txt, .pdf, .docx, .xlsx) and incrementally index it.

    Args:
        file: 上传的文件
        language: 文档语言（"zh" 或 "en"），可选
        title: 文档标题，可选
        api_key: API Key（用于博客同步认证），可选
    """
    # Get tenant_id from current context
    tenant_id = get_current_tenant_id()

    # 验证 blog_sync API Key（仅对未通过 header 认证的外部请求生效）
    # 已通过 JWT 或 X-API-Key header 认证的用户（如演示账号登录）跳过此检查
    expected_key = settings.blog_sync_api_key
    has_header_auth = bool(
        request.headers.get("Authorization", "").startswith("Bearer ")
        or request.headers.get("X-API-Key", "")
    )
    if expected_key and not has_header_auth and api_key != expected_key:
        raise AuthenticationError("Invalid API key")


    # Validate filename
    if not file.filename:
        raise AureonException(status_code=400, detail="No filename")

    # Security: prevent path traversal
    _validate_filename(file.filename)

    # Sanitize filename
    safe_filename = os.path.basename(file.filename)

    # Validate extension
    allowed = {".md", ".txt", ".pdf", ".docx", ".xlsx"}
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in allowed:
        raise AureonException(
            status_code=400,
            detail=f"Unsupported format: {ext}, only {', '.join(allowed)}",
        )

    # Save to uploads directory
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    dest = os.path.join(UPLOADS_DIR, safe_filename)

    MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise AureonException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024}MB)")
        with open(dest, "wb") as f:
            f.write(content)
    except AureonException:
        raise
    except Exception as e:
        raise AureonException(status_code=500, detail=f"File save failed: {str(e)}")

    # Incremental index
    result = run_incremental_index(dest)

    # Update metadata with provided language and title
    if language in ("zh", "en") and result.get("metadata"):
        result["metadata"]["language"] = language
    if title and result.get("metadata"):
        result["metadata"]["title"] = title

    # Add tenant_id to metadata
    if result.get("metadata"):
        result["metadata"]["tenant_id"] = tenant_id
    elif result.get("status") == "success":
        # If metadata doesn't exist but upload was successful, create it
        result["metadata"] = {"tenant_id": tenant_id}

    if result["status"] == "error":
        raise AureonException(
            status_code=500, detail=result.get("message", "Index failed")
        )

    return result


@router.get("/uploads")
async def rag_list_uploads(_user: dict = require_role(UserRole.VIEWER)):
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


@router.delete("/upload/{filename}", response_model=StatusResponse)
async def rag_delete_upload(filename: str, _user: dict = require_role(UserRole.EDITOR)):
    """Delete an uploaded file and its chunks from the index."""
    # Security: prevent path traversal
    _validate_filename(filename)

    filepath = os.path.join(UPLOADS_DIR, filename)

    # 1. Remove from Qdrant index
    from app.rag.vector_store import delete_from_index

    delete_from_index(filename)

    # 2. Delete physical file
    if os.path.isfile(filepath):
        os.remove(filepath)
        logger.info("Deleted uploaded file", path=filepath)
    else:
        logger.warning("File not found on disk (already deleted)", path=filepath)

    return StatusResponse(status="deleted", session_id=filename)


@router.post("/evaluate")
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


@router.post("/experiment")
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


@router.get("/health")
async def rag_health():
    """RAG system health + live service status."""

    bm25 = get_bm25_stats()

    # Embedding provider chain status
    embed_providers = []
    if settings.dashscope_api_key:
        embed_providers.append("dashscope-512d")
    if settings.siliconflow_api_key:
        embed_providers.append("siliconflow")
    if settings.embedding_api_key or settings.llm_api_key:
        embed_providers.append("zhipu-1024d")

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
        "bm25_avgdl": bm25.get("avgdl", 0),
        "bm25_min_idf": bm25.get("min_idf_threshold", 0),
        "bm25_min_raw": bm25.get("min_raw_score", 0),
        "bm25_idf_samples": bm25.get("sample_idf", {}),
        "embedding_providers": embed_providers,
        "hybrid_search_enabled": True,
        "guardrails_enabled": True,
        "langsmith_enabled": bool(
            settings.langchain_api_key
        ),
    }


@router.get("/benchmark")
async def rag_benchmark():
    """Latest RAG evaluation benchmark results."""
    benchmark_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "benchmark_results.json"
    )
    if not os.path.isfile(benchmark_path):
        return {"metrics": [], "services": {}, "timestamp": None}
    try:
        with open(benchmark_path, encoding="utf-8") as f:
            return json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return {"metrics": [], "services": {}, "timestamp": None}


@router.post("/cache/clear")
async def rag_cache_clear(_user: dict = require_role(UserRole.ADMIN)):
    """Clear all RAG query caches (Redis exact + semantic + in-memory)."""
    from app.cache.redis_client import clear_cache_by_prefix, _mem_cache
    _mem_cache.clear()
    cleared_exact = await clear_cache_by_prefix("llm_cache:")
    cleared_semantic = await clear_cache_by_prefix("semantic:")
    return {"status": "ok", "cleared_exact": cleared_exact, "cleared_semantic": cleared_semantic}


@router.get("/suggestions")
async def get_suggestions():
    """Return suggested queries based on knowledge base topics."""
    suggestions = [
        {"query": "RAG 系统的检索管线是怎么设计的？", "category": "RAG"},
        {"query": "BM25 和向量检索各有什么优劣？", "category": "检索"},
        {"query": "LangGraph 和 LangChain LCEL 有什么区别？", "category": "框架"},
        {"query": "如何优化 RAG 系统的检索延迟？", "category": "性能"},
        {"query": "企业 AI 知识库部署有哪些注意事项？", "category": "部署"},
    ]
    return {"suggestions": suggestions}
