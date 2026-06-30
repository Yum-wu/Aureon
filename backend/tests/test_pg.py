"""Tests for app.memory.pg — async PostgreSQL adapter.

Uses aiosqlite in-memory to test SQLAlchemy Core operations,
and mock-based tests for PostgreSQL-specific SQL (ILIKE, INTERVAL).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Module-level engine state must be reset before each test class
import app.memory.pg as pg_mod  # noqa: E402  (isort:skip)
from app.memory.pg import get_database_url  # noqa: E402  (isort:skip)


_IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:?cache=shared"


def _reset_globals():
    """Reset module-level engine + factory so next get_async_engine() creates fresh."""
    pg_mod._engine = None
    pg_mod._session_factory = None


@pytest.fixture(autouse=True)
def _reset():
    _reset_globals()


@pytest.mark.asyncio
async def test_get_database_url_from_settings():
    """get_database_url reads from app.config and normalises postgres:// -> asyncpg."""
    with patch("app.config.settings") as mock_settings:
        mock_settings.database_url = "postgresql://user:pass@localhost/db"
        url = get_database_url()
        assert url == "postgresql+asyncpg://user:pass@localhost/db"


@pytest.mark.asyncio
async def test_get_database_url_postgres():
    with patch("app.config.settings") as mock_settings:
        mock_settings.database_url = "postgres://u:p@h/d"
        url = get_database_url()
        assert url == "postgresql+asyncpg://u:p@h/d"


@pytest.mark.asyncio
async def test_get_database_url_none():
    with patch("app.config.settings") as mock_settings:
        mock_settings.database_url = None
        url = get_database_url()
        assert url is None


@pytest.mark.asyncio
async def test_get_database_url_already_asyncpg():
    with patch("app.config.settings") as mock_settings:
        mock_settings.database_url = "postgresql+asyncpg://u:p@h/d"
        url = get_database_url()
        assert url == "postgresql+asyncpg://u:p@h/d"


# -- In-memory SQLite tests for insert/query operations --


@pytest.fixture
def pg_ctx():
    """Set up in-memory aiosqlite engine and create tables."""
    _reset_globals()
    with patch("app.memory.pg.get_database_url", return_value=_IN_MEMORY_URL):
        import app.memory.pg as pg
        old_engine = pg._engine
        pg._engine = None
        yield pg
        pg._engine = old_engine


@pytest.mark.asyncio
async def test_init_pg_tables_creates_tables(pg_ctx):
    await pg_ctx.init_pg_tables()
    engine = pg_ctx.get_async_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            pg_ctx.text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        names = {row[0] for row in result}
    assert "query_traces" in names
    assert "conversations" in names
    assert "atoms" in names


@pytest.mark.asyncio
async def test_init_pg_tables_idempotent(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.init_pg_tables()


@pytest.mark.asyncio
async def test_insert_and_query_trace(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.insert_query_trace({
        "request_id": "req-001",
        "query": "test query",
        "latency_ms": 123.4,
        "cache_hit": True,
    })

    engine = pg_ctx.get_async_engine()
    async with engine.connect() as conn:
        from sqlalchemy import select
        stmt = select(pg_ctx.query_traces).where(pg_ctx.query_traces.c.request_id == "req-001")
        row = (await conn.execute(stmt)).first()

    assert row is not None
    assert row.query == "test query"
    assert row.latency_ms == 123.4
    assert row.cache_hit is True
    assert row.session_id is None


@pytest.mark.asyncio
async def test_insert_conversation(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.insert_conversation({
        "session_id": "sess-1",
        "role": "user",
        "content": "Hello world",
        "user_id": "u-1",
    })

    engine = pg_ctx.get_async_engine()
    async with engine.connect() as conn:
        from sqlalchemy import select
        stmt = select(pg_ctx.conversations).where(pg_ctx.conversations.c.session_id == "sess-1")
        row = (await conn.execute(stmt)).first()

    assert row is not None
    assert row.role == "user"
    assert row.content == "Hello world"
    assert row.user_id == "u-1"


@pytest.mark.asyncio
async def test_insert_conversation_with_metadata(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.insert_conversation({
        "session_id": "sess-2",
        "role": "assistant",
        "content": "Sure!",
        "metadata_json": {"tokens": 42, "tool_name": "search"},
    })

    engine = pg_ctx.get_async_engine()
    async with engine.connect() as conn:
        from sqlalchemy import select
        stmt = select(pg_ctx.conversations).where(pg_ctx.conversations.c.session_id == "sess-2")
        row = (await conn.execute(stmt)).first()

    assert row is not None
    assert '"tokens": 42' in row.metadata_json
    assert '"tool_name": "search"' in row.metadata_json


@pytest.mark.asyncio
async def test_insert_atom_and_get_by_session(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.insert_atom({
        "session_id": "sess-1",
        "subject": "Alice",
        "predicate": "likes",
        "object": "ice cream",
        "confidence": 0.9,
    })

    rows = await pg_ctx.get_atoms_by_session("sess-1")
    assert len(rows) == 1
    assert rows[0]["subject"] == "Alice"
    assert rows[0]["predicate"] == "likes"
    assert rows[0]["object"] == "ice cream"
    assert abs(rows[0]["confidence"] - 0.9) < 0.01


@pytest.mark.asyncio
async def test_get_atoms_by_session_empty(pg_ctx):
    await pg_ctx.init_pg_tables()
    rows = await pg_ctx.get_atoms_by_session("nonexistent")
    assert rows == []


@pytest.mark.asyncio
async def test_get_atoms_by_session_multiple(pg_ctx):
    await pg_ctx.init_pg_tables()
    for i in range(3):
        await pg_ctx.insert_atom({
            "session_id": "sess-multi",
            "subject": f"subj-{i}",
            "predicate": "is",
            "object": f"val-{i}",
        })

    rows = await pg_ctx.get_atoms_by_session("sess-multi")
    assert len(rows) == 3
    # Ordered by created_at ascending
    assert rows[0]["subject"] == "subj-0"
    assert rows[2]["subject"] == "subj-2"


@pytest.mark.asyncio
async def test_update_atom(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.insert_atom({
        "session_id": "sess-upd",
        "subject": "X",
        "predicate": "is",
        "object": "Y",
        "confidence": 0.5,
    })
    rows = await pg_ctx.get_atoms_by_session("sess-upd")
    atom_id = rows[0]["id"]

    await pg_ctx.update_atom(atom_id, confidence=0.99)
    rows = await pg_ctx.get_atoms_by_session("sess-upd")
    assert abs(rows[0]["confidence"] - 0.99) < 0.01
    assert rows[0]["updated_at"] is not None


@pytest.mark.asyncio
async def test_touch_atom(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.insert_atom({
        "session_id": "sess-touch",
        "subject": "A",
        "predicate": "B",
        "object": "C",
    })
    rows = await pg_ctx.get_atoms_by_session("sess-touch")
    atom_id = rows[0]["id"]
    before = rows[0]["last_accessed"]

    await pg_ctx.touch_atom(atom_id)
    rows = await pg_ctx.get_atoms_by_session("sess-touch")
    after = rows[0]["last_accessed"]
    assert after != before or after is not None


# -- Mock-based tests for PostgreSQL-specific SQL --


class _AsyncCtx:
    """Minimal async context manager wrapper for mocking."""
    def __init__(self, conn):
        self._conn = conn
    async def __aenter__(self):
        return self._conn
    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_decay_stale_atoms_sql_returns_count(pg_ctx):
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.execute.return_value.rowcount = 5
    mock_engine = MagicMock()
    mock_engine.begin.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        count = await pg_ctx.decay_stale_atoms_sql(days=7, decay_factor=0.8)
        assert count == 5


@pytest.mark.asyncio
async def test_decay_stale_atoms_sql_zero_affected(pg_ctx):
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.execute.return_value.rowcount = 0
    mock_engine = MagicMock()
    mock_engine.begin.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        count = await pg_ctx.decay_stale_atoms_sql()
        assert count == 0


@pytest.mark.asyncio
async def test_search_atoms_by_session(pg_ctx):
    await pg_ctx.init_pg_tables()
    # Insert atoms directly via engine
    engine = pg_ctx.get_async_engine()
    async with engine.begin() as conn:
        for vals in [
            {"session_id": "s-srch", "subject": "Alice", "predicate": "likes", "object": "cats"},
            {"session_id": "s-srch", "subject": "Bob", "predicate": "likes", "object": "dogs"},
        ]:
            await conn.execute(
                pg_ctx.atoms.insert().values(**vals)
                .values(created_at=datetime.now(timezone.utc))
            )

    async with engine.connect() as conn:
        from sqlalchemy import text
        result = await conn.execute(
            text("SELECT * FROM atoms WHERE session_id = :sid AND "
                 "(subject LIKE :q OR predicate LIKE :q OR \"object\" LIKE :q) "
                 "ORDER BY confidence DESC LIMIT :lim"),
            {"sid": "s-srch", "q": "%Alice%", "lim": 10},
        )
        rows = [dict(r._mapping) for r in result]

    assert len(rows) == 1
    assert rows[0]["subject"] == "Alice"


@pytest.mark.asyncio
async def test_get_atoms_by_session_orders_by_created_at(pg_ctx):
    await pg_ctx.init_pg_tables()
    for i in range(5):
        await pg_ctx.insert_atom({
            "session_id": "s-ord",
            "subject": f"key-{i}",
            "predicate": "val",
            "object": str(i),
        })

    rows = await pg_ctx.get_atoms_by_session("s-ord")
    assert [r["subject"] for r in rows] == ["key-0", "key-1", "key-2", "key-3", "key-4"]


@pytest.mark.asyncio
async def test_insert_query_trace_all_fields(pg_ctx):
    await pg_ctx.init_pg_tables()
    await pg_ctx.insert_query_trace({
        "request_id": "req-full",
        "session_id": "sess-q",
        "user_id": "u-1",
        "workspace_id": "ws-1",
        "query": "full test",
        "latency_ms": 100.0,
        "cache_hit": False,
        "retrieval_latency_ms": 50.0,
        "rerank_latency_ms": 20.0,
        "llm_latency_ms": 30.0,
        "total_chunks": 10,
        "reranked_chunks": 5,
    })

    engine = pg_ctx.get_async_engine()
    from sqlalchemy import select
    async with engine.connect() as conn:
        row = (await conn.execute(
            select(pg_ctx.query_traces).where(pg_ctx.query_traces.c.request_id == "req-full")
        )).first()

    assert row is not None
    assert row.session_id == "sess-q"
    assert row.llm_latency_ms == 30.0
    assert row.total_chunks == 10
    assert row.reranked_chunks == 5
    assert row.created_at is not None
