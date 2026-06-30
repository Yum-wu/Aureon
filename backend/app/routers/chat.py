"""Chat router — extracted from main.py.

Routes:
  POST /stream           — basic chat streaming (SSE)
  POST /enhanced/stream  — enhanced chat with RAG integration (SSE)
  GET  /sessions              — list active sessions
  DELETE /sessions/{session_id} — delete a session
"""

import asyncio
import collections
import json
import time
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
from app.common import SSE_HEADERS, sse_event, resilient_fire_and_forget
from app.rag.guardrails import detect_prompt_injection, sanitize_input
from app.audit.decorator import audit_action
from app.exceptions import AureonException

logger = structlog.get_logger()

# ── Agent cache (LRU-bounded) ──

_MAX_AGENTS = 32
_agents: collections.OrderedDict[str, Any] = collections.OrderedDict()
_agent_lock = asyncio.Lock()

router = APIRouter()


async def _record_stream_analytics(
    query: str,
    model: str,
    stream_gen,
) -> Any:
    """Wrap SSE stream to record analytics + cost data after completion."""
    start_time = time.time()
    full_text_len = 0
    sources_count = 0

    try:
        async for raw_event in stream_gen:
            # Lightweight analytics — only parse sources events (low frequency)
            if raw_event.startswith("data: ") and '"type": "sources"' in raw_event:
                try:
                    payload = json.loads(raw_event[6:].rstrip())
                    sources_count = len(payload.get("sources", []))
                except (json.JSONDecodeError, AttributeError):
                    pass
            elif raw_event.startswith("data: "):
                # Count output bytes without JSON parsing
                full_text_len += len(raw_event) - 6
            yield raw_event
    except Exception:
        raise
    finally:
        latency_ms = int((time.time() - start_time) * 1000)

        # Token estimation based on character count
        # Chinese: ~1 token/char, English: ~4 chars/token
        # Average: ~2 chars per token for mixed content
        output_tokens = max(full_text_len // 2, 1) if full_text_len else 0
        input_tokens = len(query) + 500

        # 1. Record query stats (Analytics page data source)
        try:
            from app.api.rag_stats import record_query
            resilient_fire_and_forget(
                record_query(query, sources_count, latency_ms,
                             input_tokens=input_tokens,
                             output_tokens=output_tokens),
                name="chat_record_query",
            )
        except Exception as exc:
            logger.debug("chat_analytics_record_skipped", error=str(exc))

        # 2. Record Dashboard realtime metrics
        try:
            from app.observability.metrics_collector import get_metrics_collector
            from app.multi_tenant.middleware import get_current_tenant_id
            from app.config import settings as _settings

            collector = get_metrics_collector()
            tenant_id = get_current_tenant_id()
            resilient_fire_and_forget(
                collector.record_query_metrics(
                    tenant_id=tenant_id,
                    ttft_ms=latency_ms,
                    tpot_ms=latency_ms / max(output_tokens, 1),
                    tokens_in=input_tokens,
                    tokens_out=output_tokens,
                    model=model or _settings.llm_model,
                    cache_hit=False,
                    error=False,
                ),
                name="chat_dashboard_metrics",
            )
        except Exception as exc:
            logger.debug("chat_dashboard_metrics_skipped", error=str(exc))

        # 3. Record cost usage (Cost Governance data source)
        try:
            from app.cost.service import get_cost_service
            from app.cost.models import TokenUsage
            from app.multi_tenant.middleware import get_current_tenant_id
            from app.config import settings as _settings

            cost_service = get_cost_service()
            tenant_id = get_current_tenant_id()
            cost_per_1k_in = 0.00015
            cost_per_1k_out = 0.0006
            cost_usd = round(
                (input_tokens / 1000 * cost_per_1k_in)
                + (output_tokens / 1000 * cost_per_1k_out),
                6,
            )
            resilient_fire_and_forget(
                cost_service.record_usage(TokenUsage(
                    tenant_id=tenant_id,
                    model=model or _settings.llm_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                )),
                name="chat_cost_record",
            )
        except Exception as exc:
            logger.debug("chat_cost_record_skipped", error=str(exc))


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

    raw_stream = stream_agent_with_memory(
        agent,
        sanitized_message,
        req.session_id or "",
        memory_manager=memory_manager,
    )
    return StreamingResponse(
        _record_stream_analytics(req.message or "", req.model or "", raw_stream),
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
        _record_stream_analytics(req.message or "", req.model or "", event_stream()),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions():
    sessions = memory_manager.get_active_sessions()
    return SessionListResponse(sessions=sessions, count=len(sessions))


@router.delete("/sessions/{session_id}", response_model=StatusResponse)
async def delete_session(session_id: str):
    await asyncio.to_thread(memory_manager.finalize_scenario, session_id, "用户手动清除会话")
    memory_manager.clear_session(session_id)
    return StatusResponse(status="deleted", session_id=session_id)
