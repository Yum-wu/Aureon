import asyncio
import uuid
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
import structlog

from app.common import sse_event
from app.observability.langfuse_integration import get_langfuse_handler

logger = structlog.get_logger()


async def stream_agent(
    agent_graph,
    user_message: str,
    session_id: str | None = None,
    chat_history: list | None = None,
    memory_context: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream agent response as structured event dicts.

    Yields dict objects with ``type`` and ``content`` keys.
    Callers are responsible for SSE serialization via ``sse_event()``.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    yield {"type": "session", "content": {"session_id": session_id}}

    chat_history = chat_history or []
    messages = list(chat_history)

    if memory_context:
        messages.append(SystemMessage(content=f"以下是之前的对话记忆：\n{memory_context}"))

    messages.append(HumanMessage(content=user_message))

    # 获取 Langfuse callback handler
    langfuse_handler = get_langfuse_handler()
    stream_config = {"callbacks": [langfuse_handler]} if langfuse_handler else None

    try:
        async for event in agent_graph.astream_events(
            {"messages": messages},
            version="v2",
            config=stream_config,
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield {"type": "text", "content": chunk.content}

            elif kind == "on_tool_start":
                name = event.get("name", "")
                tool_input = event["data"].get("input", {})
                yield {"type": "tool_start", "content": {"tool": name, "args": tool_input}}

            elif kind == "on_tool_end":
                name = event.get("name", "")
                output = event["data"].get("output", "")
                yield {"type": "tool_end", "content": {"tool": name, "result": str(output)}}

        yield {"type": "done", "content": None}

    except Exception as e:
        logger.error("Agent stream error: %s", e, exc_info=True)
        yield {"type": "error", "content": {"message": "An internal error occurred while processing your request."}}


async def stream_agent_with_memory(
    agent_graph,
    user_message: str,
    session_id: str = "",
    memory_manager = None,
) -> AsyncGenerator[str, None]:
    """Stream agent response with automatic post-stream memory recording.

    Wraps stream_agent() and intercepts structured event dicts to:
    1. Track session_id (may change if new)
    2. Collect full assistant response text
    3. On 'done' event: record user + assistant messages to L0,
       then trigger L1 atom extraction asynchronously.

    Yields SSE-formatted strings (serialization happens here).
    """
    sid = session_id
    full_response = ""

    memory_context = (
        await asyncio.to_thread(memory_manager.get_context, sid)
        if memory_manager else None
    )

    async for event in stream_agent(
        agent_graph, user_message, sid,
        memory_context=memory_context,
    ):
        # Serialize to SSE string for the HTTP layer
        yield sse_event(event)

        evt_type = event.get("type", "")

        if evt_type == "session":
            sid = event["content"]["session_id"]

        elif evt_type == "text":
            full_response += event.get("content", "")

        elif evt_type == "done" and sid and memory_manager:
            if not full_response.strip():
                logger.warning(f"Memory: empty assistant response for session {sid}")

            await asyncio.to_thread(memory_manager.record_message, sid, "user", user_message)
            await asyncio.to_thread(memory_manager.record_message, sid, "assistant", full_response)
            try:
                await memory_manager.extract_atoms(sid)
            except Exception as e:
                logger.warning(f"Atom extraction failed for session {sid}: {e}")


