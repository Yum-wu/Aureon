"""Tests for app.langgraph.graph — route_intent, run_workflow, _build_result."""

import pytest
from unittest.mock import patch

from app.langgraph.graph import route_intent, _build_result
from app.langgraph.state import initial_state


# ── route_intent ──


class TestRouteIntent:
    def test_returns_intent_from_state(self):
        state = initial_state("test")
        state["intent"] = "rag"
        assert route_intent(state) == "rag"

    def test_returns_chat_default(self):
        state = initial_state("test")
        assert route_intent(state) == "chat"

    def test_mixed_intent(self):
        state = initial_state("test")
        state["intent"] = "mixed"
        assert route_intent(state) == "mixed"


# ── _build_result ──


class TestBuildResult:
    def test_basic_result(self):
        import time
        state = initial_state("test")
        state["final_answer"] = "answer"
        state["intent"] = "rag"
        state["intermediate_results"] = [{"node": "rag", "output": "context"}]
        state["node_times"] = {"rag": 100}

        result = _build_result(state, time.time() - 0.5)
        assert result["answer"] == "answer"
        assert result["route"] == "rag"
        assert "rag" in result["nodes_executed"]
        assert "total" in result["node_times_ms"]
        assert result["error"] is None

    def test_error_result(self):
        import time
        state = initial_state("test")
        state["error"] = "something broke"
        result = _build_result(state, time.time())
        assert result["error"] == "something broke"


# ── run_workflow ──


class TestRunWorkflow:
    @pytest.mark.asyncio
    @patch("app.langgraph.graph.create_llm_call_fn")
    @patch("app.langgraph.graph.run_intent_node", return_value=("chat", 0.9))
    @patch("app.langgraph.graph.run_generate_node", return_value="Hello!")
    async def test_chat_intent(self, mock_gen, mock_intent, mock_llm):
        from app.langgraph.graph import run_workflow
        mock_llm.return_value = lambda msgs: "response"

        result = await run_workflow("hi")
        assert result["answer"] == "Hello!"
        assert result["route"] == "chat"
        assert result["error"] is None

    @pytest.mark.asyncio
    @patch("app.langgraph.graph.create_llm_call_fn")
    @patch("app.langgraph.graph.run_intent_node", return_value=("rag", 0.95))
    @patch("app.langgraph.graph.run_rag_node", return_value=("RAG answer", [{"title": "Doc"}]))
    async def test_rag_intent(self, mock_rag, mock_intent, mock_llm):
        from app.langgraph.graph import run_workflow
        mock_llm.return_value = lambda msgs: "response"

        result = await run_workflow("what is RAG?")
        assert result["answer"] == "RAG answer"
        assert result["route"] == "rag"

    @pytest.mark.asyncio
    @patch("app.langgraph.graph.create_llm_call_fn")
    @patch("app.langgraph.graph.run_intent_node", return_value=("chat", 0.9))
    @patch("app.langgraph.graph.run_generate_node", side_effect=RuntimeError("LLM crash"))
    async def test_error_handling(self, mock_gen, mock_intent, mock_llm):
        from app.langgraph.graph import run_workflow
        mock_llm.return_value = lambda msgs: "response"

        result = await run_workflow("test")
        assert result["error"] is not None
        assert "LLM crash" in result["error"]
        assert "处理出错" in result["answer"]
