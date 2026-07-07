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


@router.post("/session")
@limiter.limit("10/minute")
async def create_support_session(request: Request):
    """Issue a short-lived scoped token for visitor support WebSocket."""
    from app.security.rbac import create_access_token

    now = datetime.now(timezone.utc)
    expires_in = 900
    token = create_access_token({
        "sub": "support-visitor",
        "role": "VIEWER",
        "scope": "support_ws",
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + expires_in,
    })
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


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
