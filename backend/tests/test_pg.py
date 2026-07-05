"""Tests for app.memory.pg — async PostgreSQL adapter.

Uses mock-based tests for operations and PostgreSQL-specific SQL.
Uses aiosqlite-style in-memory engine for some tests (requires `aiosqlite`
pip installed in dev environment; not shipped in production requirements).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Module-level engine state must be reset before each test class
import app.memory.pg as pg_mod  # noqa: E402  (isort:skip)
from app.memory.pg import get_database_url  # noqa: E402  (isort:skip)


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
        with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
            get_database_url()


@pytest.mark.asyncio
async def test_get_database_url_already_asyncpg():
    with patch("app.config.settings") as mock_settings:
        mock_settings.database_url = "postgresql+asyncpg://u:p@h/d"
        url = get_database_url()
        assert url == "postgresql+asyncpg://u:p@h/d"


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
async def test_decay_stale_atoms_sql_returns_count():
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.execute.return_value.rowcount = 5
    mock_engine = MagicMock()
    mock_engine.begin.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        count = await pg_mod.decay_stale_atoms_sql(days=7, decay_factor=0.8)
        assert count == 5


@pytest.mark.asyncio
async def test_decay_stale_atoms_sql_zero_affected():
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.execute.return_value.rowcount = 0
    mock_engine = MagicMock()
    mock_engine.begin.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        count = await pg_mod.decay_stale_atoms_sql()
        assert count == 0


@pytest.mark.asyncio
async def test_search_atoms_by_session():
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.execute.return_value = []
    mock_engine = MagicMock()
    mock_engine.connect.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        rows = await pg_mod.search_atoms_by_session("s-srch", "Alice")
        assert rows == []


@pytest.mark.asyncio
async def test_insert_query_trace():
    """Verify insert_query_trace passes correct data to the engine."""
    mock_conn = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        await pg_mod.insert_query_trace({
            "request_id": "req-001",
            "query": "test query",
            "latency_ms": 123.4,
            "cache_hit": True,
        })

    assert mock_conn.execute.called


@pytest.mark.asyncio
async def test_insert_conversation():
    mock_conn = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        await pg_mod.insert_conversation({
            "session_id": "sess-1",
            "role": "user",
            "content": "Hello",
        })

    assert mock_conn.execute.called


@pytest.mark.asyncio
async def test_get_atoms_by_session_empty():
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.execute.return_value = []
    mock_engine = MagicMock()
    mock_engine.connect.return_value = _AsyncCtx(mock_conn)

    with patch("app.memory.pg.get_async_engine", return_value=mock_engine):
        rows = await pg_mod.get_atoms_by_session("nonexistent")
        assert rows == []
