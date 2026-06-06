import sqlite3
import threading
from pathlib import Path

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
    """
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        return conn

    with _init_lock:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _thread_local.conn = conn
        return conn


# -- Schema Versioning --
# Lightweight migration mechanism for raw SQLite (no Alembic/SQLAlchemy needed).
# Each migration is a function that receives a connection and bumps the version.
_SCHEMA_VERSION = 1  # Current target version

_SCHEMA_MIGRATIONS = {
    # version: migration_function
    # Example:
    # 2: lambda conn: conn.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT"),
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
        CREATE INDEX IF NOT EXISTS idx_atom_session ON atoms(session_id);
    """)
    _run_migrations(conn)
    conn.commit()
