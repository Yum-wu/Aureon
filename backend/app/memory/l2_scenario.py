import structlog
import time
from pathlib import Path
from datetime import datetime
from app.memory import l1_atom

logger = structlog.get_logger()

SCENARIOS_DIR = Path("offloads/scenarios").resolve()
MAX_SCENARIOS = 50

# Reject any session_id that would let the file path escape SCENARIOS_DIR.
# Characters that are always unsafe in a path component: separators, NUL.
# The resolved-path check below is the actual safety net; this filter is a
# fast-path rejection of obviously malicious input.
_UNSAFE_SESSION_ID_CHARS = set("/\\\0")

# ── Cache for scenario file listing (invalidated after 60s) ──
_scenario_cache: list[tuple[Path, float]] | None = None
_scenario_cache_ts: float = 0
_SCENARIO_CACHE_TTL = 60


def _list_scenarios():
    """List scenario files sorted by mtime desc, with caching."""
    global _scenario_cache, _scenario_cache_ts
    now = time.time()
    if _scenario_cache is not None and now - _scenario_cache_ts < _SCENARIO_CACHE_TTL:
        return _scenario_cache
    if not SCENARIOS_DIR.exists():
        _scenario_cache = []
        _scenario_cache_ts = now
        return _scenario_cache
    files = [(p, p.stat().st_mtime) for p in SCENARIOS_DIR.glob("*.md")]
    files.sort(key=lambda x: x[1], reverse=True)
    _scenario_cache = files
    _scenario_cache_ts = now
    return _scenario_cache


def finalize_scenario(session_id: str, summary: str = ""):
    """Generate and save a L2 scenario markdown file."""
    # Path-traversal guard: session_id is used directly in the filename.
    if not session_id or any(c in _UNSAFE_SESSION_ID_CHARS for c in session_id):
        logger.warning("L2 scenario skipped: unsafe session_id")
        return
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"{session_id}_{date_str}.md"
    filepath = (SCENARIOS_DIR / filename).resolve()
    if not str(filepath).startswith(str(SCENARIOS_DIR)):
        logger.warning("L2 scenario skipped: path traversal blocked for %s", session_id)
        return

    atoms = l1_atom.get_atoms_by_session(session_id)
    atom_lines = "\n".join(
        f"- {a['subject']} {a['predicate']} {a['object']} (confidence: {a['confidence']})"
        for a in atoms[:20]
    )

    content = f"""# Scenario

**Session:** {session_id} | **Date:** {date_str}

## Summary
{summary or "会话已结束"}

## Key Facts (L1)
{atom_lines or "无"}
"""

    try:
        filepath.write_text(content, encoding="utf-8")
        logger.info("L2 scenario saved: %s", filename)
    except Exception as e:
        logger.error("L2 save failed: %s", e)

    _cleanup_old_scenarios()


def get_recent_scenarios(session_id: str = "", n: int = 3):
    """Return content of recent N scenario files."""
    files = _list_scenarios()
    results = []
    for fp, _ in files[:n]:
        try:
            results.append(fp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return results


def _cleanup_old_scenarios():
    """Keep only the most recent MAX_SCENARIOS files."""
    files = _list_scenarios()
    excess = len(files) - MAX_SCENARIOS
    if excess <= 0:
        return
    # files sorted newest-first; delete the oldest (tail)
    for fp, _ in files[-excess:]:
        try:
            fp.unlink()
            logger.debug(f"Removed old scenario: {fp.name}")
        except Exception:
            pass
    # Invalidate cache after cleanup
    global _scenario_cache, _scenario_cache_ts
    _scenario_cache = None
    _scenario_cache_ts = 0
