import structlog
import time
from pathlib import Path
from datetime import datetime
from app.memory import l1_atom
import re

logger = structlog.get_logger()


def _sanitize_session_id(session_id: str) -> str:
    """防止路径遍历攻击。只保留字母、数字、下划线、连字符。"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)


SCENARIOS_DIR = Path("offloads/scenarios").resolve()
MAX_SCENARIOS = 50

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
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"{_sanitize_session_id(session_id)}_{date_str}.md"
    filepath = SCENARIOS_DIR / filename

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
        except Exception as e:
            logger.debug("scenario_file_read_failed", path=str(fp), error=str(e))
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
        except Exception as e:
            logger.debug("scenario_file_delete_failed", path=str(fp), error=str(e))
    # Invalidate cache after cleanup
    global _scenario_cache, _scenario_cache_ts
    _scenario_cache = None
    _scenario_cache_ts = 0
