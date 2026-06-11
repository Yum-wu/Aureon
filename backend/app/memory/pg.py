"""
PostgreSQL async adapter for Aureon memory system.

Falls back to SQLite (via aiosqlite) if ``DATABASE_URL`` is not configured.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger(__name__)

metadata = MetaData()

# -- Table models --------------------------------------------------------

query_traces = Table(
    "query_traces",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("request_id", String(64), unique=True, nullable=False),
    Column("session_id", String(128), nullable=True),
    Column("user_id", String(128), nullable=True),
    Column("workspace_id", String(128), nullable=True),
    Column("query", Text, nullable=False),
    Column("latency_ms", Float, default=0.0),
    Column("cache_hit", Boolean, default=False),
    Column("retrieval_latency_ms", Float, default=0.0),
    Column("rerank_latency_ms", Float, default=0.0),
    Column("llm_latency_ms", Float, default=0.0),
    Column("total_chunks", Integer, default=0),
    Column("reranked_chunks", Integer, default=0),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(128), nullable=False),
    Column("user_id", String(128), nullable=True),
    Column("role", String(32), nullable=False),
    Column("content", Text, nullable=False),
    Column("metadata_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

# -- Engine management ---------------------------------------------------

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[sessionmaker] = None  # type: ignore[type-arg]


def get_database_url() -> Optional[str]:
    """Read ``DATABASE_URL`` from the environment.

    Supports both ``postgresql://`` and ``postgresql+asyncpg://`` schemes.
    Returns ``None`` when the variable is not set, which triggers a fallback
    to the async SQLite driver.
    """
    from app.config import settings
    url = settings.database_url
    if not url:
        return None
    # Normalise to asyncpg driver if a plain postgresql:// was given
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def get_async_engine() -> AsyncEngine:
    """Return (and lazily create) the global async engine.

    If ``DATABASE_URL`` is absent the engine is created with aiosqlite
    pointing at the same ``offloads/memory.db`` path used by the synchronous
    SQLite layer, so the two coexist without conflicts.
    """
    global _engine
    if _engine is not None:
        return _engine

    database_url = get_database_url()
    if database_url:
        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
        )
        logger.info("pg_engine_created", backend="postgresql")
    else:
        # Fallback: async SQLite
        db_path = os.path.join("offloads", "memory.db")
        _engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
        )
        logger.info("pg_engine_created", backend="aiosqlite", path=db_path)

    return _engine


def get_async_session_factory() -> sessionmaker:  # type: ignore[type-arg]
    """Return a sessionmaker bound to the async engine."""
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# -- Table initialisation ------------------------------------------------


async def init_pg_tables() -> None:
    """Create all tracked tables if they do not already exist.

    Safe to call multiple times -- ``CREATE TABLE IF NOT EXISTS`` is idempotent.
    When falling back to aiosqlite and the tables already exist from the sync
    SQLite layer, schema mismatches are logged and swallowed.
    """
    engine = get_async_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        logger.info("pg_tables_initialised")
    except Exception as exc:
        # Tables may already exist with a different schema (e.g. created by
        # the sync SQLite layer).  This is non-fatal for the async adapter.
        logger.warning(
            "pg_tables_init_partial",
            detail=str(exc),
        )


# -- Insert helpers ------------------------------------------------------


async def insert_query_trace(trace_data: dict[str, Any]) -> None:
    """Asynchronously insert a row into ``query_traces``.

    Parameters
    ----------
    trace_data:
        Dictionary with at least ``request_id`` and ``query`` keys.  Missing
        optional fields default to sensible values.
    """
    engine = get_async_engine()
    stmt = query_traces.insert().values(
        request_id=trace_data.get("request_id", ""),
        session_id=trace_data.get("session_id"),
        user_id=trace_data.get("user_id"),
        workspace_id=trace_data.get("workspace_id"),
        query=trace_data.get("query", ""),
        latency_ms=trace_data.get("latency_ms", 0.0),
        cache_hit=trace_data.get("cache_hit", False),
        retrieval_latency_ms=trace_data.get("retrieval_latency_ms", 0.0),
        rerank_latency_ms=trace_data.get("rerank_latency_ms", 0.0),
        llm_latency_ms=trace_data.get("llm_latency_ms", 0.0),
        total_chunks=trace_data.get("total_chunks", 0),
        reranked_chunks=trace_data.get("reranked_chunks", 0),
        created_at=datetime.now(timezone.utc),
    )
    async with engine.begin() as conn:
        await conn.execute(stmt)
    logger.debug("pg_query_trace_inserted", request_id=trace_data.get("request_id"))


async def insert_conversation(conv_data: dict[str, Any]) -> None:
    """Asynchronously insert a row into ``conversations``.

    Parameters
    ----------
    conv_data:
        Dictionary with ``session_id``, ``role``, and ``content`` keys.
    """
    engine = get_async_engine()
    stmt = conversations.insert().values(
        session_id=conv_data.get("session_id", ""),
        user_id=conv_data.get("user_id"),
        role=conv_data.get("role", "assistant"),
        content=conv_data.get("content", ""),
        metadata_json=(
            json.dumps(conv_data["metadata_json"])
            if conv_data.get("metadata_json") is not None
            else None
        ),
        created_at=datetime.now(timezone.utc),
    )
    async with engine.begin() as conn:
        await conn.execute(stmt)
    logger.debug("pg_conversation_inserted", session_id=conv_data.get("session_id"))
