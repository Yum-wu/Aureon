import structlog
from pathlib import Path
from datetime import datetime
from app.config import settings

logger = structlog.get_logger()

REFS_DIR = Path(__file__).resolve().parent.parent.parent / "offloads" / "refs"

# Reject any session_id that would let the file path escape REFS_DIR.
# Characters that are always unsafe in a path component: separators, NUL.
# The resolved-path check below is the actual safety net.
_UNSAFE_SESSION_ID_CHARS = set("/\\\0")


def offload_if_needed(tool_name: str, content: str, session_id: str) -> str:
    """Check if content exceeds threshold, offload if so.

    Returns summary line with result_ref if offloaded, or original content.
    """
    if len(content) <= settings.offload_max_chars:
        return content

    # Path-traversal guard: session_id is used directly in the filename.
    if not session_id or any(c in _UNSAFE_SESSION_ID_CHARS for c in session_id):
        logger.warning("Offload skipped: unsafe session_id")
        return content
    if not tool_name or any(c in _UNSAFE_SESSION_ID_CHARS for c in tool_name):
        logger.warning("Offload skipped: unsafe tool_name")
        return content

    REFS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    filename = f"{session_id}_{tool_name}_{ts}.md"
    filepath = (REFS_DIR / filename).resolve()
    if not str(filepath).startswith(str(REFS_DIR)):
        logger.warning("Offload skipped: path traversal blocked for %s", session_id)
        return content

    try:
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Offloaded {tool_name} output ({len(content)} chars) -> {filename}")
    except Exception as e:
        logger.error(f"Offload write failed for {filename}: {e}")
        return content

    # Build summary line
    preview = content[:200].replace("\n", " ")
    return (
        f"[Tool:{tool_name} 完整输出已保存] "
        f"{preview}... "
        f"result_ref: {filename}"
    )


def read_ref(ref_path: str) -> str:
    """Read an offloaded file with path traversal protection."""
    target = (REFS_DIR / ref_path).resolve()
    if not str(target).startswith(str(REFS_DIR)):
        logger.warning(f"Path traversal blocked: {ref_path}")
        return "Error: invalid file reference"
    if not target.exists():
        return f"Error: file not found: {ref_path}"
    try:
        return target.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Read ref failed: {e}")
        return f"Error: {e}"
