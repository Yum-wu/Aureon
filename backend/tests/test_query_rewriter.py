"""Tests for app.rag.query_rewriter — rewrite_query, expand_queries."""

import pytest
from unittest.mock import MagicMock

from app.rag.query_rewriter import rewrite_query, expand_queries


def _make_mock_llm(content: str):
    llm = MagicMock()
    resp = MagicMock()
    resp.content = content
    llm.invoke.return_value = resp
    return llm


# ── rewrite_query ──


class TestRewriteQuery:
    def test_normal_rewrite(self):
        llm = _make_mock_llm('{"rewritten": "RAG retrieval augmented generation", "variants": ["what is RAG", "retrieval augmented generation explained"]}')
        result = rewrite_query("啥是RAG", llm)
        assert result["rewritten"] == "RAG retrieval augmented generation"
        assert len(result["variants"]) == 2

    def test_json_with_markdown_fence(self):
        llm = _make_mock_llm('```json\n{"rewritten": "cleaned query", "variants": ["v1"]}\n```')
        result = rewrite_query("messy query", llm)
        assert result["rewritten"] == "cleaned query"

    def test_llm_exception_falls_back_to_original(self):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("LLM down")
        result = rewrite_query("original query", llm)
        assert result["rewritten"] == "original query"
        assert result["variants"] == ["original query"]

    def test_invalid_json_falls_back(self):
        llm = _make_mock_llm("garbage response")
        result = rewrite_query("test query", llm)
        assert result["rewritten"] == "test query"

    def test_missing_keys_falls_back(self):
        llm = _make_mock_llm("{}")
        result = rewrite_query("test query", llm)
        assert result["rewritten"] == "test query"
        assert result["variants"] == ["test query"]


# ── expand_queries ──


class TestExpandQueries:
    def test_returns_deduplicated_list(self):
        llm = _make_mock_llm('{"rewritten": "RAG system", "variants": ["RAG system", "retrieval augmented"]}')
        result = expand_queries("RAG", llm)
        assert result[0] == "RAG system"
        # "RAG system" appears twice but should be deduplicated
        assert len(result) == 2
        assert result.count("RAG system") == 1

    def test_includes_rewritten_as_first(self):
        llm = _make_mock_llm('{"rewritten": "main query", "variants": ["alt1", "alt2"]}')
        result = expand_queries("q", llm)
        assert result[0] == "main query"

    def test_llm_exception_returns_original(self):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("fail")
        result = expand_queries("original", llm)
        assert result == ["original"]
