"""Tests for app.langgraph — state, streaming, intent nodes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.langgraph.state import initial_state


# ── state.py ──


class TestAgentState:
    def test_initial_state_has_all_fields(self):
        state = initial_state("What is RAG?")
        assert state["query"] == "What is RAG?"
        assert state["intent"] == ""
        assert state["intent_confidence"] == 0.0
        assert state["rag_context"] == ""
        assert state["rag_sources"] == []
        assert state["agent_result"] == ""
        assert state["agent_tool_calls"] == []
        assert state["intermediate_results"] == []
        assert state["final_answer"] == ""
        assert state["error"] is None
        assert state["node_times"] == {}
        assert state["mcp_calls"] == []

    def test_initial_state_query_preserved(self):
        state = initial_state("  test query  ")
        assert state["query"] == "  test query  "


# ── streaming.py ──


class TestStreamWorkflow:
    @pytest.mark.asyncio
    @patch("app.langgraph.streaming.classify_intent", return_value=("chat", 0.9))
    @patch("app.langgraph.streaming.detect_language", return_value="en")
    async def test_chat_route(self, mock_detect, mock_intent):
        from app.langgraph.streaming import stream_workflow

        chunk1 = MagicMock()
        chunk1.content = "Hello"
        chunk2 = MagicMock()
        chunk2.content = " world"

        async def fake_astream(messages):
            for c in [chunk1, chunk2]:
                yield c

        mock_llm = MagicMock()
        mock_llm.astream = fake_astream

        events = []
        async for event in stream_workflow("hello world", mock_llm):
            events.append(event)

        types = [e["type"] for e in events]
        assert "intent" in types
        assert "route" in types
        assert "text" in types
        assert "done" in types

        route_event = next(e for e in events if e["type"] == "route")
        assert route_event["content"] == "chat"

    @pytest.mark.asyncio
    @patch("app.langgraph.streaming.classify_intent", return_value=("rag", 0.95))
    @patch("app.langgraph.streaming.detect_language", return_value="en")
    @patch("app.langgraph.streaming.retrieve_keyword", return_value=[])
    async def test_rag_no_results(self, mock_retrieve, mock_detect, mock_intent):
        from app.langgraph.streaming import stream_workflow

        events = []
        async for event in stream_workflow("test", AsyncMock()):
            events.append(event)

        types = [e["type"] for e in events]
        assert "sources" in types
        assert "text" in types
        # Should have the "no content found" message
        text_events = [e for e in events if e["type"] == "text"]
        assert any("No relevant content" in e["content"] for e in text_events)

    @pytest.mark.asyncio
    @patch("app.langgraph.streaming.classify_intent", return_value=("rag", 0.95))
    @patch("app.langgraph.streaming.detect_language", return_value="zh")
    @patch("app.langgraph.streaming.retrieve_keyword", return_value=[
        {"text": "RAG content", "metadata": {"title": "RAG Guide", "slug": "rag-guide"}, "score": 0.9}
    ])
    @patch("app.langgraph.streaming.format_context", return_value="formatted context")
    async def test_rag_with_results(self, mock_format, mock_retrieve, mock_detect, mock_intent):
        from app.langgraph.streaming import stream_workflow

        chunk = MagicMock()
        chunk.content = "RAG is..."

        async def fake_astream(messages):
            yield chunk

        mock_llm = MagicMock()
        mock_llm.astream = fake_astream

        events = []
        async for event in stream_workflow("what is RAG", mock_llm):
            events.append(event)

        sources_event = next(e for e in events if e["type"] == "sources")
        assert len(sources_event["sources"]) == 1
        assert sources_event["sources"][0]["title"] == "RAG Guide"

    @pytest.mark.asyncio
    @patch("app.langgraph.streaming.classify_intent", side_effect=RuntimeError("intent fail"))
    @patch("app.langgraph.streaming.detect_language", return_value="en")
    async def test_error_handling(self, mock_detect, mock_intent):
        from app.langgraph.streaming import stream_workflow

        events = []
        async for event in stream_workflow("test", AsyncMock()):
            events.append(event)

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        # Error message is sanitized — never expose internal details
        assert "error" in error_events[0]["content"].lower()
        # Should still emit done
        assert events[-1]["type"] == "done"


# ── nodes/intent.py ──


class TestClassifyIntent:
    def test_rag_intent(self):
        from app.langgraph.nodes.intent import classify_intent
        intent, confidence = classify_intent("什么是 RAG?")
        assert intent == "rag"
        assert confidence > 0.5

    def test_chat_intent_short(self):
        from app.langgraph.nodes.intent import classify_intent
        intent, confidence = classify_intent("hi")
        assert intent == "chat"
        assert confidence == 0.95

    def test_agent_intent(self):
        from app.langgraph.nodes.intent import classify_intent
        intent, confidence = classify_intent("计算 1+1 的结果")
        assert intent == "agent"
        assert confidence > 0.5

    def test_mixed_intent(self):
        from app.langgraph.nodes.intent import classify_intent
        intent, confidence = classify_intent("计算什么是 RAG 的区别")
        assert intent == "mixed"

    def test_default_chat(self):
        from app.langgraph.nodes.intent import classify_intent
        intent, confidence = classify_intent("tell me a joke about programming")
        assert intent == "chat"
        assert confidence == 0.6
