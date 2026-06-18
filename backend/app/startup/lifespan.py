"""Application lifespan — startup and shutdown logic.

Extracted from main.py to separate lifecycle management from HTTP routing.
"""

import os
import threading
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.config import settings
from app.memory.db import init_db, close_db
from app.memory.manager import manager as memory_manager
from app.memory.storage import get_backend
from app.cache.redis_client import close_redis, close_sync_redis
from app.startup.warmup import warmup_bm25

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    # ── Security: block dev mode on production platforms ──
    if os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        if settings.auth.environment == "dev":
            raise RuntimeError(
                "FATAL: AUTH__ENVIRONMENT=dev is forbidden in production. "
                "Set AUTH__ENVIRONMENT=production and configure API_AUTH_KEY."
            )
        if not settings.api_auth_key:
            raise RuntimeError(
                "FATAL: API_AUTH_KEY must be set in production."
            )

    # ── Startup ──
    if not settings.llm_api_key and not settings.fallback_api_key:
        logger.warning("LLM_API_KEY not set; Agent creation will fail")
    # Disable LangSmith to prevent Railway platform auto-tracing 403
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    init_db()

    # Initialise unified storage backend (SQLite or PostgreSQL)
    backend = get_backend()
    backend.init()

    # ── Core modules (always initialized) ──
    from app.features import init_feature_flags_table
    from app.observability import init_query_traces_table
    from app.security import init_pii_detection_table, init_sso_providers_table
    from app.audit import init_audit_tables
    from app.memory.pg import init_pg_tables
    init_feature_flags_table()
    init_query_traces_table()
    init_pii_detection_table()
    init_sso_providers_table()
    init_audit_tables()
    await init_pg_tables()

    # ── Experimental modules (conditional on EXPERIMENTAL_MODULES env var) ──
    # Default: enabled for backward compatibility.
    # Set EXPERIMENTAL_MODULES=false to skip init and reduce startup overhead.
    _experimental = os.environ.get("EXPERIMENTAL_MODULES", "true").lower() != "false"
    if _experimental:
        try:
            from app.evaluation import init_evaluation_tables
            from app.cost import init_cost_tables
            from app.reliability import init_reliability_tables
            from app.knowledge import init_knowledge_tables
            from app.ai_platform import init_ai_platform_tables
            from app.integration import init_integration_tables
            init_evaluation_tables()
            init_cost_tables()
            init_reliability_tables()
            init_knowledge_tables()
            init_ai_platform_tables()
            init_integration_tables()
        except Exception as e:
            logger.warning("Experimental module init failed (non-fatal): %s", e)
    else:
        logger.info("Experimental modules disabled (EXPERIMENTAL_MODULES=false)")
    memory_manager.init_background_tasks()

    # Background BM25 + ChromaDB warmup + auto-rebuild (non-blocking)
    threading.Thread(target=warmup_bm25, daemon=True).start()

    # OpenTelemetry distributed tracing
    try:
        from app.observability.tracing import init_tracing
        init_tracing(app)
    except Exception as e:
        logger.warning("OpenTelemetry tracing init failed (non-fatal): %s", e)

    # Langfuse tracing (async check)
    try:
        from app.observability.langfuse_integration import init_langfuse
        await init_langfuse()
    except Exception as e:
        logger.warning("Langfuse init failed (non-fatal): %s", e)

    logger.info("Startup complete")

    yield  # Application runs here

    # ── Shutdown ──
    # Flush Langfuse traces
    try:
        from app.observability.langfuse_integration import shutdown_langfuse
        await shutdown_langfuse()
    except Exception as e:
        logger.warning("Langfuse shutdown failed (non-fatal): %s", e)
    memory_manager.flush_all_scenarios()
    backend.close()
    close_db()
    await close_redis()
    close_sync_redis()
