# -*- coding: utf-8 -*-
"""
Unified storage backend abstraction for the Aureon memory system.

Provides a protocol (interface) with SQLite and PostgreSQL implementations,
allowing L0 (conversations) and L1 (atoms) to operate against either backend
transparently.  The active backend is selected at startup based on the
``DATABASE_URL`` environment variable.

Usage::

    from app.memory.storage import get_backend

    backend = get_backend()
    backend.record_message(session_id, "user", "hello")
    msgs = backend.get_conversation(session_id, limit=10)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


# -- Protocol --

@runtime_checkable
class StorageBackend(Protocol):
    """Abstract storage interface for memory layers L0/L1."""

    def init(self) -> None:
        """Initialise tables / schema.  Idempotent."""
        ...

    def close(self) -> None:
        """Release connections on shutdown."""
        ...

    # L0 - Conversations
    def record_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        tool_name: str | None = None,
        tool_args: str | None = None,
    ) -> None:
        ...

    def get_conversation(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        ...

    def get_message_by_id(self, conv_id: int) -> Optional[Dict[str, Any]]:
        ...

    def cleanup_oldest(
        self, session_id: str, max_messages: int = 200
    ) -> None:
        ...

    # L1 - Atoms
    def save_atom(
        self,
        session_id: str,
        subject: str,
        predicate: str,
        obj: str,
        source_ref: int | None = None,
        confidence: float = 0.5,
    ) -> None:
        ...

    def search_atoms(
        self, session_id: str, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        ...

    def get_atoms_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        ...


# -- SQLite backend --

class SQLiteStorageBackend:
    """Wraps the existing synchronous SQLite layer (``app.memory.db``)."""

    def __init__(self) -> None:
        from app.memory import db as _db
        self._db = _db

    # lifecycle
    def init(self) -> None:
        self._db.init_db()
        logger.info("storage_backend_init", backend="sqlite")

    def close(self) -> None:
        self._db.close_db()

    # L0
    def record_message(self, session_id, role, content, tokens=0,
                       tool_name=None, tool_args=None):
        from app.memory.l0_conversation import record_message as _record
        _record(session_id, role, content, tokens, tool_name, tool_args)

    def get_conversation(self, session_id, limit=50):
        from app.memory.l0_conversation import get_conversation as _get
        return _get(session_id, limit)

    def get_message_by_id(self, conv_id):
        from app.memory.l0_conversation import get_message_by_id as _get
        return _get(conv_id)

    def cleanup_oldest(self, session_id, max_messages=200):
        from app.memory.l0_conversation import cleanup_oldest as _clean
        _clean(session_id, max_messages)

    # L1
    def save_atom(self, session_id, subject, predicate, obj,
                  source_ref=None, confidence=0.5):
        from app.memory.l1_atom import save_atom as _save
        _save(session_id, subject, predicate, obj, source_ref, confidence)

    def search_atoms(self, session_id, query, limit=10):
        from app.memory.l1_atom import search_atoms as _search
        return _search(session_id, query, limit)

    def get_atoms_by_session(self, session_id):
        from app.memory.l1_atom import get_atoms_by_session as _get
        return _get(session_id)


# -- PostgreSQL backend --

class PGStorageBackend:
    """Async PostgreSQL backend via SQLAlchemy (``app.memory.pg``).

    Because the pg adapter is fully async but the StorageBackend protocol
    is synchronous (used from ``asyncio.to_thread`` callers), this backend
    runs async operations in a dedicated event loop on a worker thread.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._loop: Optional[Any] = None
        self._thread: Optional[Any] = None

    # -- internal helpers --

    def _ensure_loop(self) -> Any:
        """Start a background event loop on a daemon thread (lazy)."""
        if self._loop is not None:
            return self._loop
        import asyncio
        import threading

        self._loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True, name="pg-storage")
        self._thread.start()
        return self._loop

    def _run_async(self, coro: Any) -> Any:
        import asyncio
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)

    # lifecycle
    def init(self) -> None:
        from app.memory.pg import init_pg_tables
        self._run_async(init_pg_tables())
        logger.info("storage_backend_init", backend="postgresql")

    def close(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

    # L0 - async pg operations wrapped for sync callers
    def record_message(self, session_id, role, content, tokens=0,
                       tool_name=None, tool_args=None):
        from app.memory.pg import insert_conversation
        self._run_async(insert_conversation({
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata_json": {"tokens": tokens, "tool_name": tool_name, "tool_args": tool_args},
        }))

    def get_conversation(self, session_id, limit=50):
        from app.memory.pg import get_async_engine, conversations
        from sqlalchemy import select

        async def _fetch():
            engine = get_async_engine()
            async with engine.connect() as conn:
                stmt = (
                    select(conversations)
                    .where(conversations.c.session_id == session_id)
                    .order_by(conversations.c.created_at.desc())
                    .limit(limit)
                )
                result = await conn.execute(stmt)
                rows = [dict(r._mapping) for r in result]
                return list(reversed(rows))

        return self._run_async(_fetch())

    def get_message_by_id(self, conv_id):
        from app.memory.pg import get_async_engine, conversations
        from sqlalchemy import select

        async def _fetch():
            engine = get_async_engine()
            async with engine.connect() as conn:
                stmt = select(conversations).where(conversations.c.id == conv_id)
                result = await conn.execute(stmt)
                row = result.first()
                return dict(row._mapping) if row else None

        return self._run_async(_fetch())

    def cleanup_oldest(self, session_id, max_messages=200):
        from app.memory.pg import get_async_engine, conversations
        from sqlalchemy import select, func, delete

        async def _clean():
            engine = get_async_engine()
            async with engine.begin() as conn:
                count_result = await conn.execute(
                    select(func.count()).select_from(conversations).where(
                        conversations.c.session_id == session_id
                    )
                )
                count = count_result.scalar() or 0
                if count > max_messages:
                    excess = count - max_messages + 50
                    sub = (
                        select(conversations.c.id)
                        .where(conversations.c.session_id == session_id)
                        .order_by(conversations.c.created_at.asc())
                        .limit(excess)
                    )
                    await conn.execute(
                        delete(conversations).where(conversations.c.id.in_(sub))
                    )

        self._run_async(_clean())

    # L1 - atoms (falls back to SQLite since pg.py lacks atoms table)
    def save_atom(self, session_id, subject, predicate, obj,
                  source_ref=None, confidence=0.5):
        logger.debug("pg_atom_fallback_to_sqlite", subject=subject)
        from app.memory.l1_atom import save_atom as _save
        _save(session_id, subject, predicate, obj, source_ref, confidence)

    def search_atoms(self, session_id, query, limit=10):
        from app.memory.l1_atom import search_atoms as _search
        return _search(session_id, query, limit)

    def get_atoms_by_session(self, session_id):
        from app.memory.l1_atom import get_atoms_by_session as _get
        return _get(session_id)


# -- Singleton accessor --

_backend: Optional[StorageBackend] = None


def get_backend() -> StorageBackend:
    """Return the active storage backend (created lazily).

    Selection logic:
    - ``DATABASE_URL`` set -> ``PGStorageBackend``
    - Otherwise -> ``SQLiteStorageBackend`` (default)
    """
    global _backend
    if _backend is not None:
        return _backend

    from app.config import settings
    database_url = settings.database_url

    if database_url:
        _backend = PGStorageBackend(database_url)
        logger.info("storage_backend_selected", backend="postgresql")
    else:
        _backend = SQLiteStorageBackend()
        logger.info("storage_backend_selected", backend="sqlite")

    return _backend


def set_backend(backend: StorageBackend) -> None:
    """Override the active backend (for testing)."""
    global _backend
    _backend = backend


def reset_backend() -> None:
    """Reset to uninitialised state (for testing)."""
    global _backend
    _backend = None
