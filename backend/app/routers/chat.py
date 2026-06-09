"""Chat router — extracted from main.py.

Routes:
  POST /stream           — basic chat streaming (SSE)
  POST /enhanced/stream  — enhanced chat with RAG integration (SSE)
  GET  /sessions              — list active sessions
  DELETE /sessions/{session_id} — delete a session
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
from app.common import SSE_HEADERS, sse_event
from app.rag.guardrails import detect_prompt_injection, sanitize_input
from app.audit.decorator import audit_action
from app.exceptions import AureonException

logger = structlog.get_logger()

# ── Agent cache (LRU-bounded) ──
import collections

_MAX_AGENTS = 32
_agents: collections.OrderedDict[str, Any] = collections.OrderedDict()
_agent_lock = asyncio.Lock()

router = APIRouter()


async def _get_agent(lang: str = "zh", model: str = None):
    """Get or create a chat agent for the given language and model (LRU-bounded)."""
    global _agents
    cache_key = f"{lang}:{model or 'default'}"
    if cache_key in _agents:
        _agents.move_to_end(cache_key)
        return _agents[cache_key]
    async with _agent_lock:
        if cache_key in _agents:
            _agents.move_to_end(cache_key)
            return _agents[cache_key]
        llm = create_llm(model=model)
        _agents[cache_key] = create_chat_agent(llm, lang=lang)
        # Evict oldest if over limit
        while len(_agents) > _MAX_AGENTS:
            _agents.popitem(last=False)
    return _agents[cache_key]


@router.post("/stream")
@audit_action("query", "session")
async def chat_stream(req: ChatRequest, request: Request):
    # Prompt injection check (< 1ms, regex-based)
    injection = detect_prompt_injection(req.message)
    if injection["detected"]:
        logger.warning("Prompt injection detected", pattern=injection["pattern"], risk=injection["risk_level"])
        if injection["risk_level"] == "high":
            raise AureonException(status_code=400, detail="Potentially harmful input detected.")

    # Sanitize input
    sanitized_message = sanitize_input(req.message)

    lang = detect_language(sanitized_message)
    agent = await _get_agent(lang, model=req.model)
    return StreamingResponse(
        stream_agent_with_memory(
            agent,
            sanitized_message,
            req.session_id or "",
            memory_manager=memory_manager,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/enhanced/stream")
@audit_action("query", "session")
async def chat_enhanced_stream(req: ChatRequest, request: Request):
    """Enhanced chat with automatic RAG integration via LangGraph intent routing."""
    from app.langgraph.streaming import stream_workflow

    # Prompt injection check (< 1ms, regex-based)
    injection = detect_prompt_injection(req.message)
    if injection["detected"]:
        logger.warning("Prompt injection detected", pattern=injection["pattern"], risk=injection["risk_level"])
        if injection["risk_level"] == "high":
            raise AureonException(status_code=400, detail="Potentially harmful input detected.")

    sanitized_message = sanitize_input(req.message)

    llm = create_llm(model=req.model)

    async def event_stream():
        try:
            async for event in stream_workflow(
                query=sanitized_message,
                llm=llm,
                session_id=req.session_id or "",
            ):
                yield sse_event(event)
        except Exception as e:
            logger.error("enhanced_stream_error: %s", e)
            yield sse_event({'type': 'error', 'content': 'An error occurred while processing your request'})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions():
    sessions = memory_manager.get_active_sessions()
    return SessionListResponse(sessions=sessions, count=len(sessions))


@router.delete("/sessions/{session_id}", response_model=StatusResponse)
async def delete_session(session_id: str):
    memory_manager.finalize_scenario(session_id, summary="用户手动清除会话")
    memory_manager.clear_session(session_id)
    return StatusResponse(status="deleted", session_id=session_id)
