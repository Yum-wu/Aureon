"""Support router — offline message collection."""
import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.database.connection import get_db_pool
from app.rate_limit import limiter

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/support", tags=["Support"])


class OfflineMessage(BaseModel):
    name: str
    email: str
    message: str
    page_url: str | None = None


@router.post("/offline-message")
@limiter.limit("5/minute")
async def submit_offline_message(msg: OfflineMessage, request: Request):
    """Record an offline support message from a disconnected user."""
    pool = get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS support_messages (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    message TEXT NOT NULL,
                    page_url TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    resolved BOOLEAN DEFAULT FALSE
                )"""
            )
            now = datetime.now(timezone.utc)
            await conn.execute(
                "INSERT INTO support_messages (name, email, message, page_url, created_at) VALUES ($1, $2, $3, $4, $5)",
                msg.name, msg.email, msg.message, msg.page_url, now,
            )
        logger.info("support.offline_message_saved", email=msg.email)
        return {"status": "ok", "message": "Message saved"}
    except Exception:
        logger.exception("support.offline_message_error")
        raise HTTPException(status_code=500, detail="Failed to save message")
