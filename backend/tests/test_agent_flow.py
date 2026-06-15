"""
Tests for agent flow: factory, tool registration, conversation streaming.

Covers:
- create_chat_agent() factory (mock LLM)
- Tool registration (ALL_TOOLS list)
- stream_agent() SSE output
- stream_agent_with_memory() memory recording
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.agent.agent import (
    create_chat_agent,
)
from app.agent.executor import (
    stream_agent,
    stream_agent_with_memory,
    sse_event,
)


# ── Helper: mock agent graph ──

def _make_mock_agent_graph(events=None):
    """Create a mock agent graph with astream_events."""
    graph = MagicMock()

    async def _fake_astream(input_data, version="v2", **kwargs):
        for evt in (events or []):
            yield evt

    graph.astream_events = _fake_astream
    return graph


def _text_event(content="Hello"):
    return {
        "event": "on_chat_model_stream",
        "data": {"chunk": MagicMock(content=content)},
    }


def _tool_start_event(name="calculator", inp={"expression": "1+1"}):
    return {
        "event": "on_tool_start",
        "name": name,
        "data": {"input": inp},
    }


def _tool_end_event(name="calculator", output="2"):
    return {
        "event": "on_tool_end",
        "name": name,
        "data": {"output": output},
    }


# ── _sse helper tests ──

class TestSSEHelper:
    def test_sse_format(self):
        """sse_event returns 'data: JSON\n\n' format."""
        result = sse_event({"type": "text", "content": "hi"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")

    def test_sse_json_parseable(self):
        """sse_event output is valid JSON after stripping prefix."""
        result = sse_event({"type": "done", "content": None})
        json_str = result[len("data: "):].strip()
        data = json.loads(json_str)
        assert data["type"] == "done"
        assert data["content"] is None

    def test_sse_unicode(self):
        """sse_event handles Chinese characters."""
        result = sse_event({"type": "text", "content": "你好世界"})
        assert "你好世界" in result


# ── create_chat_agent tests ──

class TestCreateChatAgent:
    @patch("app.agent.agent.create_agent")
    @patch("app.agent.agent.ALL_TOOLS", [])
    def test_factory_calls_create_agent(self, mock_create_agent):
        """create_chat_agent calls langchain create_agent."""
        mock_llm = MagicMock()
        mock_create_agent.return_value = MagicMock()

        result = create_chat_agent(mock_llm)

        mock_create_agent.assert_called_once()
        assert result is not None

    @patch("app.agent.agent.create_agent")
    @patch("app.agent.agent.ALL_TOOLS", [])
    def test_factory_passes_llm_and_tools(self, mock_create_agent):
        """Factory passes LLM and tools to create_agent."""
        mock_llm = MagicMock()
        mock_tools = [MagicMock(), MagicMock()]
        mock_create_agent.return_value = MagicMock()

        create_chat_agent(mock_llm, tools=mock_tools)

        call_kwargs = mock_create_agent.call_args
        assert call_kwargs[1]["model"] is mock_llm
        assert call_kwargs[1]["tools"] is mock_tools

    @patch("app.agent.agent.create_agent")
    @patch("app.agent.agent.ALL_TOOLS", [])
    def test_factory_custom_system_prompt(self, mock_create_agent):
        """Custom system_prompt overrides default."""
        mock_llm = MagicMock()
        custom_prompt = "Custom system prompt"
        mock_create_agent.return_value = MagicMock()

        create_chat_agent(mock_llm, system_prompt=custom_prompt)

        call_kwargs = mock_create_agent.call_args
        assert custom_prompt in call_kwargs[1]["system_prompt"]

    @patch("app.agent.agent.create_agent")
    @patch("app.agent.agent.ALL_TOOLS", [])
    def test_factory_zh_uses_default_prompt(self, mock_create_agent):
        """lang='zh' uses DEFAULT_SYSTEM_PROMPT."""
        mock_llm = MagicMock()
        mock_create_agent.return_value = MagicMock()

        create_chat_agent(mock_llm, lang="zh")

        call_kwargs = mock_create_agent.call_args
        prompt = call_kwargs[1]["system_prompt"]
        assert "你是一个有帮助的 AI 助手" in prompt

    @patch("app.agent.agent.create_agent")
    @patch("app.agent.agent.ALL_TOOLS", [])
    def test_factory_en_uses_en_prompt(self, mock_create_agent):
        """lang='en' uses DEFAULT_SYSTEM_PROMPT_EN."""
        mock_llm = MagicMock()
        mock_create_agent.return_value = MagicMock()

        create_chat_agent(mock_llm, lang="en")

        call_kwargs = mock_create_agent.call_args
        prompt = call_kwargs[1]["system_prompt"]
        assert "You are a helpful AI assistant" in prompt

    @patch("app.agent.agent.create_agent")
    @patch("app.agent.agent.ALL_TOOLS", ["tool_a", "tool_b"])
    def test_factory_default_tools(self, mock_create_agent):
        """When tools=None, uses ALL_TOOLS."""
        mock_llm = MagicMock()
        mock_create_agent.return_value = MagicMock()

        create_chat_agent(mock_llm)

        call_kwargs = mock_create_agent.call_args
        assert call_kwargs[1]["tools"] == ["tool_a", "tool_b"]


# ── stream_agent tests ──

class TestStreamAgent:
    @pytest.mark.asyncio
    async def test_emits_session_event(self):
        """First event is always a session event."""
        graph = _make_mock_agent_graph(events=[])

        events = []
        async for evt in stream_agent(graph, "hi"):
            events.append(evt)

        first = events[0]
        assert first["type"] == "session"
        assert "session_id" in first["content"]

    @pytest.mark.asyncio
    async def test_emits_done_event(self):
        """Last event is always a done event."""
        graph = _make_mock_agent_graph(events=[])

        events = []
        async for evt in stream_agent(graph, "hi"):
            events.append(evt)

        last = events[-1]
        assert last["type"] == "done"

    @pytest.mark.asyncio
    async def test_streams_text_chunks(self):
        """Text chunks from LLM are emitted as text events."""
        graph = _make_mock_agent_graph(events=[
            _text_event("Hello "),
            _text_event("world"),
        ])

        events = []
        async for evt in stream_agent(graph, "hi"):
            events.append(evt)

        text_events = [e for e in events if e.get("type") == "text"]
        assert len(text_events) == 2
        assert text_events[0]["content"] == "Hello "
        assert text_events[1]["content"] == "world"

    @pytest.mark.asyncio
    async def test_streams_tool_events(self):
        """Tool start/end events are emitted."""
        graph = _make_mock_agent_graph(events=[
            _tool_start_event("calculator"),
            _tool_end_event("calculator", "42"),
            _text_event("The answer is 42"),
        ])

        events = []
        async for evt in stream_agent(graph, "what is 6*7"):
            events.append(evt)

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_end" in types

    @pytest.mark.asyncio
    async def test_custom_session_id(self):
        """Providing session_id skips auto-generation."""
        graph = _make_mock_agent_graph(events=[])

        events = []
        async for evt in stream_agent(graph, "hi", session_id="my-session"):
            events.append(evt)

        first = events[0]
        assert first["content"]["session_id"] == "my-session"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Exceptions produce error event."""
        graph = MagicMock()

        async def _boom(input_data, version="v2", **kwargs):
            raise RuntimeError("Graph exploded")
            yield  # make it a generator

        graph.astream_events = _boom

        events = []
        async for evt in stream_agent(graph, "crash"):
            events.append(evt)

        types = [e["type"] for e in events]
        assert "error" in types

    @pytest.mark.asyncio
    async def test_memory_context_injected(self):
        """memory_context is prepended as SystemMessage."""
        graph = _make_mock_agent_graph(events=[])

        collected_input = {}

        async def _capture(input_data, version="v2", **kwargs):
            collected_input.update(input_data)
            return
            yield

        graph.astream_events = _capture

        async for _ in stream_agent(graph, "hi", memory_context="Previous context"):
            pass

        messages = collected_input.get("messages", [])
        system_msgs = [m for m in messages if hasattr(m, "content") and "Previous context" in m.content]
        assert len(system_msgs) >= 1

    @pytest.mark.asyncio
    async def test_chat_history_included(self):
        """chat_history messages are prepended before user message."""
        from langchain_core.messages import HumanMessage

        graph = _make_mock_agent_graph(events=[])
        collected_input = {}

        async def _capture(input_data, version="v2", **kwargs):
            collected_input.update(input_data)
            return
            yield

        graph.astream_events = _capture

        history = [HumanMessage(content="previous message")]
        async for _ in stream_agent(graph, "new message", chat_history=history):
            pass

        messages = collected_input.get("messages", [])
        contents = [m.content for m in messages]
        assert "previous message" in contents
        assert "new message" in contents


# ── stream_agent_with_memory tests ──

class TestStreamAgentWithMemory:
    @pytest.mark.asyncio
    async def test_records_messages_on_done(self):
        """After 'done' event, user and assistant messages are recorded."""
        graph = _make_mock_agent_graph(events=[
            _text_event("Response text"),
        ])

        mock_mm = MagicMock()
        mock_mm.get_context.return_value = ""
        mock_mm.extract_atoms = AsyncMock()

        events = []
        async for evt in stream_agent_with_memory(
            graph, "user msg", session_id="mem_sess", memory_manager=mock_mm
        ):
            events.append(evt)

        mock_mm.record_message.assert_any_call("mem_sess", "user", "user msg")
        mock_mm.record_message.assert_any_call("mem_sess", "assistant", "Response text")

    @pytest.mark.asyncio
    async def test_calls_extract_atoms(self):
        """Atom extraction is triggered after recording."""
        graph = _make_mock_agent_graph(events=[
            _text_event("Some response"),
        ])

        mock_mm = MagicMock()
        mock_mm.get_context.return_value = ""
        mock_mm.extract_atoms = AsyncMock()

        async for _ in stream_agent_with_memory(
            graph, "msg", session_id="atom_sess", memory_manager=mock_mm
        ):
            pass

        mock_mm.extract_atoms.assert_called_once_with("atom_sess")

    @pytest.mark.asyncio
    async def test_no_memory_manager_no_recording(self):
        """Without memory_manager, no recording occurs."""
        graph = _make_mock_agent_graph(events=[
            _text_event("Hello"),
        ])

        events = []
        async for evt in stream_agent_with_memory(
            graph, "hi", session_id="no_mm", memory_manager=None
        ):
            events.append(evt)

        # Should complete without error
        parsed = [json.loads(e[len("data: "):].strip()) for e in events]
        assert any(p["type"] == "done" for p in parsed)

    @pytest.mark.asyncio
    async def test_empty_response_warns(self):
        """Empty assistant response triggers warning log."""
        graph = _make_mock_agent_graph(events=[])

        mock_mm = MagicMock()
        mock_mm.get_context.return_value = ""
        mock_mm.extract_atoms = AsyncMock()

        with patch("app.agent.executor.logger") as mock_logger:
            async for _ in stream_agent_with_memory(
                graph, "msg", session_id="empty_sess", memory_manager=mock_mm
            ):
                pass

            # Warning should have been logged for empty response
            mock_logger.warning.assert_called()
