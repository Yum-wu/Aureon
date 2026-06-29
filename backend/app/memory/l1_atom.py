import structlog
from app.memory.db import get_db

logger = structlog.get_logger()

_fts_initialized = False


def _ensure_fts():
    """Create FTS5 virtual table + triggers (lazy, after atoms table exists)."""
    global _fts_initialized
    if _fts_initialized:
        return
    conn = get_db()
    try:
        conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS atoms_fts USING fts5(
                session_id, subject, predicate, object,
                content='atoms', content_rowid='id'
            );
            CREATE TRIGGER IF NOT EXISTS atoms_ai AFTER INSERT ON atoms BEGIN
                INSERT INTO atoms_fts(rowid, session_id, subject, predicate, object)
                VALUES (new.id, new.session_id, new.subject, new.predicate, new.object);
            END;
            CREATE TRIGGER IF NOT EXISTS atoms_ad AFTER DELETE ON atoms BEGIN
                INSERT INTO atoms_fts(atoms_fts, rowid, session_id, subject, predicate, object)
                VALUES ('delete', old.id, old.session_id, old.subject, old.predicate, old.object);
            END;
            CREATE TRIGGER IF NOT EXISTS atoms_au AFTER UPDATE ON atoms BEGIN
                INSERT INTO atoms_fts(atoms_fts, rowid, session_id, subject, predicate, object)
                VALUES ('delete', old.id, old.session_id, old.subject, old.predicate, old.object);
                INSERT INTO atoms_fts(rowid, session_id, subject, predicate, object)
                VALUES (new.id, new.session_id, new.subject, new.predicate, new.object);
            END;
        """)
        conn.commit()
        _fts_initialized = True
        logger.info("FTS5 indexes initialized for atoms")
    except Exception as e:
        logger.warning(f"FTS5 init failed (non-fatal, fallback to LIKE): {e}")


def save_atom(
    session_id: str,
    subject: str,
    predicate: str,
    obj: str,
    source_ref: int | None = None,
    confidence: float = 0.5,
):
    """Save a single atomic fact to L1 table with conflict detection.

    If an atom with the same session_id, subject, and predicate already
    exists, updates object and takes the max confidence.
    """
    _ensure_fts()
    conn = get_db()
    existing = conn.execute(
        "SELECT id, confidence FROM atoms WHERE session_id = ? AND subject = ? AND predicate = ?",
        (session_id, subject, predicate),
    ).fetchone()

    if existing:
        new_conf = max(existing["confidence"], confidence)
        conn.execute(
            "UPDATE atoms SET object = ?, confidence = ?, source_ref = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (obj, new_conf, source_ref, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO atoms (session_id, subject, predicate, object, source_ref, confidence, updated_at, last_accessed) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (session_id, subject, predicate, obj, source_ref, confidence),
        )
    conn.commit()
    logger.debug(f"L1 atom: {subject} {predicate} {obj}")


def touch_atom(atom_id: int):
    """Update last_accessed to now for the given atom."""
    conn = get_db()
    conn.execute(
        "UPDATE atoms SET last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
        (atom_id,),
    )
    conn.commit()


def decay_stale_atoms(days: int = 30, decay_factor: float = 0.9) -> int:
    """Decay confidence of atoms not accessed in N days.

    Returns the number of affected rows.
    """
    conn = get_db()
    conn.execute(
        "UPDATE atoms SET confidence = MAX(confidence * ?, 0.01), updated_at = CURRENT_TIMESTAMP "
        "WHERE last_accessed IS NOT NULL AND julianday('now') - julianday(last_accessed) > ?",
        (decay_factor, days),
    )
    conn.commit()
    affected = conn.total_changes
    logger.info(f"decayed {affected} stale atoms (days={days}, factor={decay_factor})")
    return affected


def search_atoms(session_id: str, query: str, limit: int = 10):
    """Search atoms by FTS5 full-text index."""
    _ensure_fts()
    conn = get_db()
    # Escape FTS5 special chars: wrap in double quotes for safe phrase matching
    safe = "".join(c if c.isalnum() or c in " _-" else " " for c in query).strip()
    if not safe:
        return []
    try:
        rows = conn.execute(
            "SELECT a.* FROM atoms a JOIN atoms_fts f ON a.id = f.rowid "
            "WHERE atoms_fts MATCH ? AND a.session_id = ? "
            "ORDER BY a.confidence DESC LIMIT ?",
            (f'"{safe}"', session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        # Fallback to LIKE if FTS fails — escape LIKE wildcards
        safe_like = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = conn.execute(
            "SELECT * FROM atoms WHERE session_id = ? "
            "AND (subject LIKE ? ESCAPE '\\' OR predicate LIKE ? ESCAPE '\\' OR object LIKE ? ESCAPE '\\') "
            "ORDER BY confidence DESC LIMIT ?",
            (session_id, f"%{safe_like}%", f"%{safe_like}%", f"%{safe_like}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_atoms_by_session(session_id: str):
    """Return all atoms for a session."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM atoms WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]
