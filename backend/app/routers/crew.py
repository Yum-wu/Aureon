# -*- coding: utf-8 -*-
"""Crew router - article generation via 3-agent crew.

Routes:
  POST /generate        - synchronous article generation
  POST /generate/stream - streaming article generation (SSE)
  GET   /health         - health check
"""

import asyncio
import os
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from app.config import settings
from app.common import SSE_HEADERS

logger = structlog.get_logger()

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class CrewGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500)


@router.post("/generate")
@limiter.limit("3/minute")
async def crew_generate(req: CrewGenerateRequest, request: Request):
    """Generate article via 3-agent crew (synchronous)."""
    try:
        from app.crew.crew_setup import generate_article
    except ImportError:
        raise HTTPException(status_code=503, detail="CrewAI module not available")

    try:
        # litellm (used by crewai 0.80+) needs standard OpenAI env vars
        os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
        os.environ.setdefault("OPENAI_BASE_URL", settings.llm_base_url)
        os.environ.setdefault("OPENAI_MODEL_NAME", f"openai/{settings.llm_model}")

        from app.utils.lang_detect import detect_language

        lang = detect_language(req.topic)

        start = time.time()
        result = generate_article(topic=req.topic, lang=lang)
        duration_ms = int((time.time() - start) * 1000)
        return {
            "topic": result["topic"],
            "final_output": result["final_output"],
            "duration_ms": duration_ms,
            "agents": result["agents"],
        }
    except Exception as e:
        logger.error("crew_generate_failed", error=str(e)[:200])
        raise HTTPException(status_code=500, detail="Article generation failed")


@router.post("/generate/stream")
@limiter.limit("3/minute")
async def crew_generate_stream(req: CrewGenerateRequest, request: Request):
    """Generate article with real-time agent progress via SSE."""
    try:
        from app.crew.crew_setup import generate_article
        from app.crew.main_events import EventCollector
    except ImportError as e:
        return StreamingResponse(
            iter([f'data: {{"type": "error", "message": "CrewAI not installed: {str(e)}"}}\n\n']),
            media_type="text/event-stream",
            status_code=503,
        )

    # litellm (used by crewai 0.80+) needs standard OpenAI env vars
    os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
    os.environ.setdefault("OPENAI_BASE_URL", settings.llm_base_url)
    os.environ.setdefault("OPENAI_MODEL_NAME", f"openai/{settings.llm_model}")

    from app.utils.lang_detect import detect_language

    lang = detect_language(req.topic)

    collector = EventCollector()

    async def run_crew():
        try:
            result = await asyncio.to_thread(
                generate_article, req.topic, collector.emit, lang
            )
            collector.emit("result", {
                "final_output": result["final_output"],
                "duration_ms": result["duration_ms"],
            })
        except Exception as e:
            collector.emit("error", {"message": str(e)})
        finally:
            collector.close()

    task = asyncio.create_task(run_crew())

    async def event_stream():
        try:
            async for chunk in collector.stream():
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/health")
async def crew_health():
    return {
        "status": "ok",
        "service": "crew-generator",
        "llm_configured": bool(settings.llm_api_key),
    }
