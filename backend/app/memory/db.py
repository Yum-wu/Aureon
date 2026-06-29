import sqlite3
import threading
import time
from pathlib import Path

import structlog

logger = structlog.get_logger()

DB_DIR = Path("offloads")
DB_PATH = DB_DIR / "memory.db"

# Thread-local storage for per-thread SQLite connections.
# Each thread gets its own connection, avoiding cross-thread sharing.
# WAL mode allows concurrent reads from multiple connections.
_thread_local = threading.local()
_init_lock = threading.Lock()


def get_db() -> sqlite3.Connection:
    """Get a thread-local SQLite connection.

    Each calling thread gets its own connection instance.
    WAL mode enables concurrent reads; busy_timeout handles write contention.
    Retries on 'database is locked' during WAL mode switch (multi-process startup).
    """
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        return conn

    with _init_lock:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Retry WAL mode — may fail if another process is initializing
        for attempt in range(5):
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 4:
                    time.sleep(0.5)
                else:
                    raise
        conn.execute("PRAGMA busy_timeout=5000")
        _thread_local.conn = conn
        return conn


def close_db():
    """Close the thread-local SQLite connection if open.

    Call during application shutdown to release resources.
    """
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception as e:
            logger.debug("sqlite_conn_close_failed", error=str(e))
        _thread_local.conn = None


# -- Schema Versioning --
# Lightweight migration mechanism for raw SQLite (no Alembic/SQLAlchemy needed).
# Each migration is a function that receives a connection and bumps the version.
_SCHEMA_VERSION = 2  # Current target version


def _migrate_v2(conn):
    """Add updated_at and last_accessed columns to atoms table.

    Idempotent: skips columns that already exist (fresh DB with CREATE TABLE),
    adds them for databases created before v2.
    """
    for col in ("updated_at", "last_accessed"):
        try:
            conn.execute(f"ALTER TABLE atoms ADD COLUMN {col} TIMESTAMP")
        except sqlite3.OperationalError:
            pass  # Column already exists — fresh DB includes it in CREATE TABLE
    conn.commit()


_SCHEMA_MIGRATIONS = {
    2: _migrate_v2,
}


def _get_current_version(conn) -> int:
    """Get current schema version from DB."""
    try:
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        return 0  # Table doesn't exist yet


def _run_migrations(conn):
    """Apply pending schema migrations."""
    current = _get_current_version(conn)
    if current >= _SCHEMA_VERSION:
        return

    for version in range(current + 1, _SCHEMA_VERSION + 1):
        migration_fn = _SCHEMA_MIGRATIONS.get(version)
        if migration_fn:
            migration_fn(conn)
        conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def init_db():
    """Create tables if they don't exist and run migrations."""
    conn = get_db()
    for attempt in range(5):
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tokens INTEGER DEFAULT 0,
                    tool_name TEXT,
                    tool_args TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS atoms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    source_ref INTEGER,
                    confidence REAL DEFAULT 0.5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    last_accessed TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
                CREATE INDEX IF NOT EXISTS idx_conv_session_created ON conversations(session_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_atom_session ON atoms(session_id);
            """)
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 4:
                time.sleep(0.5)
            else:
                raise
    _run_migrations(conn)
    conn.commit()
