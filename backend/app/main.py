import asyncio
import logging
import os
import sys
import time
import uuid

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import structlog

from app.api.models import StatusResponse
from app.api.rag_stats import router as stats_router
from app.api.analytics import router as analytics_router
from app.features.router import router as feature_flags_router
from app.observability.router import router as observability_router
from app.security.router import router as security_router
from app.evaluation.router import router as evaluation_router
from app.exceptions import AureonException
from app.routers import chat as chat_router
from app.routers import rag as rag_router
from app.agent.llm import create_llm
from app.tools import ALL_TOOLS
from app.memory.db import init_db
from app.memory.manager import manager as memory_manager
from app.config import settings
from app.cache.redis_client import close_redis

# ── CrewAI (merged, lazy-imported in route handlers) ──
from pydantic import BaseModel, Field

# ── Structured logging (replaces stdlib logging) ──
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer()
        if sys.stdout.isatty()
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# ── Rate limiter ──
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Aureon API", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGINS", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ──
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Custom exception handler (structured JSON) ──
from fastapi.responses import JSONResponse


@app.exception_handler(AureonException)
async def aureon_exception_handler(request: Request, exc: AureonException):
    """Return structured JSON for all Aureon-specific exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_type,
            "detail": str(exc.detail),
        },
    )


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Inject request_id / session_id into structlog context per request."""
    request_id = str(uuid.uuid4())[:8]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.time()
    response = await call_next(request)
    elapsed = int((time.time() - start) * 1000)

    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        elapsed_ms=elapsed,
    )
    return response


@app.on_event("startup")
async def startup():
    if not settings.llm_api_key and not settings.fallback_api_key:
        logger.warning("LLM_API_KEY 未配置，Agent 调用将失败")
    if settings.langchain_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    init_db()
    from app.features import init_feature_flags_table
    from app.observability import init_query_traces_table
    from app.security import init_pii_detection_table, init_sso_providers_table
    from app.evaluation import init_evaluation_tables
    init_feature_flags_table()
    init_query_traces_table()
    init_pii_detection_table()
    init_sso_providers_table()
    init_evaluation_tables()
    memory_manager.init_background_tasks()


@app.on_event("shutdown")
async def shutdown():
    memory_manager.flush_all_scenarios()
    await close_redis()


@app.post("/api/langgraph/run")
async def langgraph_run(req: dict):
    """Run LangGraph workflow for complex tasks."""
    from app.langgraph.graph import run_workflow

    query = req.get("query", "")
    session_id = req.get("session_id", "")
    if not query:
        return {"error": "query required"}
    result = await run_workflow(query, session_id=session_id)
    return result


# ── CrewAI Routes ──


class CrewGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500)


@app.post("/api/crew/generate")
async def crew_generate(req: CrewGenerateRequest):
    """Generate article via 3-agent crew (synchronous)."""
    import time
    try:
        from app.crew.crew_setup import generate_article
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"CrewAI not installed: {str(e)}")

    try:
        # litellm (used by crewai 0.80+) needs standard OpenAI env vars
        os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
        os.environ.setdefault("OPENAI_BASE_URL", settings.llm_base_url)
        os.environ.setdefault("OPENAI_MODEL_NAME", f"openai/{settings.llm_model}")

        from app.utils.lang_detect import detect_language

        lang = detect_language(req.topic)

        start = time.time()
        result = generate_article(topic=req.topic, lang=lang)
        duration_ms = int((time.time() - start) * 1000)
        return {
            "topic": result["topic"],
            "final_output": result["final_output"],
            "duration_ms": duration_ms,
            "agents": result["agents"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.post("/api/crew/generate/stream")
async def crew_generate_stream(req: CrewGenerateRequest, request: Request):
    """Generate article with real-time agent progress via SSE."""
    try:
        from app.crew.crew_setup import generate_article
        from app.crew.main_events import EventCollector
    except ImportError as e:
        return StreamingResponse(
            iter([f'data: {{"type": "error", "message": "CrewAI not installed: {str(e)}"}}\n\n']),
            media_type="text/event-stream",
            status_code=503,
        )

    # litellm (used by crewai 0.80+) needs standard OpenAI env vars
    os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
    os.environ.setdefault("OPENAI_BASE_URL", settings.llm_base_url)
    os.environ.setdefault("OPENAI_MODEL_NAME", f"openai/{settings.llm_model}")

    from app.utils.lang_detect import detect_language

    lang = detect_language(req.topic)

    collector = EventCollector()

    async def run_crew():
        try:
            result = await asyncio.to_thread(
                generate_article, req.topic, collector.emit, lang
            )
            collector.emit("result", {
                "final_output": result["final_output"],
                "duration_ms": result["duration_ms"],
            })
        except Exception as e:
            collector.emit("error", {"message": str(e)})
        finally:
            collector.close()

    task = asyncio.create_task(run_crew())

    async def event_stream():
        try:
            async for chunk in collector.stream():
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/crew/health")
async def crew_health():
    return {
        "status": "ok",
        "service": "crew-generator",
        "llm_configured": bool(settings.llm_api_key),
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": settings.llm_model,
        "tools": [t.name for t in ALL_TOOLS],
    }


app.include_router(chat_router.router)
app.include_router(rag_router.router)
app.include_router(stats_router)
app.include_router(analytics_router)
app.include_router(feature_flags_router)
app.include_router(observability_router)
app.include_router(security_router)
app.include_router(evaluation_router)

# ── SPA 静态文件（必须在 API 路由之后） ──
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("Static directory not found", path=os.path.abspath(static_dir))
