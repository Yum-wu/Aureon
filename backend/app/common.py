"""Common utilities for enterprise modules.

Extracts repeated patterns across features/observability/security/evaluation/
cost/reliability/knowledge/ai_platform/integration modules.
"""
import hashlib
from datetime import datetime, timezone
from typing import TypeVar, Type, Sequence

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def utc_now_iso() -> str:
    """UTC timestamp in ISO format. Replaces deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).isoformat()


def mask_secret(value: str | None, show_chars: int = 4) -> str | None:
    """Mask sensitive string for API responses.

    Examples:
        mask_secret("sk-abcdefgh") -> "sk-a****"
        mask_secret(None) -> None
        mask_secret("abc") -> "****" (too short to show prefix)
    """
    if not value:
        return value
    if len(value) <= show_chars:
        return "****"
    return value[:show_chars] + "****"


def deterministic_hash(seed: str, modulo: int = 100) -> int:
    """Cross-process deterministic hash. Replaces builtin hash().

    Uses MD5 for speed; collision resistance not needed for feature flags.
    """
    return int(hashlib.md5(seed.encode()).hexdigest(), 16) % modulo


def rows_to_models(rows: Sequence, model_class: Type[T]) -> list[T]:
    """Convert sqlite3.Row objects to Pydantic models."""
    return [model_class(**dict(row)) for row in rows]


# ── FastAPI shared constants ──

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def require_llm_key():
    """FastAPI dependency: raise 503 if no LLM API key is configured."""
    from fastapi import HTTPException
    from app.config import settings

    if not settings.llm_api_key and not settings.fallback_api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM API key not configured. Set LLM_API_KEY or FALLBACK_API_KEY.",
        )
