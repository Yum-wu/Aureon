"""Chat router — extracted from main.py.

Routes:
  POST /api/chat/stream           — basic chat streaming (SSE)
  POST /api/chat/enhanced/stream  — enhanced chat with RAG integration (SSE)
  GET  /api/sessions              — list active sessions
  DELETE /api/sessions/{session_id} — delete a session
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import structlog

from app.api.models import ChatRequest, SessionListResponse, StatusResponse
from app.agent.llm import create_llm
from app.agent.agent import create_chat_agent
from app.agent.executor import stream_agent_with_memory
from app.memory.manager import manager as memory_manager
from app.utils.lang_detect import detect_language

logger = structlog.get_logger()

# ── Agent cache ──
_agents: dict[str, Any] = {}
_agent_lock = asyncio.Lock()

router = APIRouter()


async def _get_agent(lang: str = "zh"):
    """Get or create a chat agent for the given language."""
    global _agents
    if lang not in _agents:
        async with _agent_lock:
            if lang not in _agents:
                llm = create_llm()
                _agents[lang] = create_chat_agent(llm, lang=lang)
    return _agents[lang]


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    lang = detect_language(req.message)
    agent = await _get_agent(lang)
    return StreamingResponse(
        stream_agent_with_memory(
            agent,
            req.message,
            req.session_id or "",
            memory_manager=memory_manager,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/chat/enhanced/stream")
async def chat_enhanced_stream(req: ChatRequest, request: Request):
    """Enhanced chat with automatic RAG integration via LangGraph intent routing."""
    from app.langgraph.streaming import stream_workflow

    llm = create_llm()

    async def event_stream():
        try:
            async for event in stream_workflow(
                query=req.message,
                llm=llm,
                session_id=req.session_id or "",
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions():
    sessions = memory_manager.get_active_sessions()
    return SessionListResponse(sessions=sessions, count=len(sessions))


@router.delete("/api/sessions/{session_id}", response_model=StatusResponse)
async def delete_session(session_id: str):
    memory_manager.finalize_scenario(session_id, summary="用户手动清除会话")
    memory_manager.clear_session(session_id)
    return StatusResponse(status="deleted", session_id=session_id)
