"""Tests for app.rag.guardrails — hallucination check, citation extraction/verification."""

import pytest
from unittest.mock import MagicMock

from app.rag.guardrails import (
    check_hallucination,
    extract_citations,
    verify_citations,
)


# ── extract_citations ──


class TestExtractCitations:
    def test_no_citations(self):
        assert extract_citations("Just a plain answer with no sources.") == []

    def test_source_colon_format(self):
        text = "According to [Source: RAG Guide], the answer is 42."
        assert extract_citations(text) == ["RAG Guide"]

    def test_chinese_source_format(self):
        text = "参考 [来源: 知识库文档] 可知答案。"
        assert extract_citations(text) == ["知识库文档"]

    def test_multiple_citations(self):
        text = "See [Source: Doc A] and [Source: Doc B]."
        result = extract_citations(text)
        assert len(result) == 2
        assert "Doc A" in result
        assert "Doc B" in result

    def test_mixed_formats(self):
        text = "[Source: English Doc] and [引用自: Chinese Doc]"
        result = extract_citations(text)
        assert len(result) == 2

    def test_citation_with_spaces_trimmed(self):
        text = "[Source:  Spaced Doc  ]"
        result = extract_citations(text)
        assert result == ["Spaced Doc"]


# ── verify_citations ──


class TestVerifyCitations:
    def test_all_verified(self):
        citations = ["RAG Guide", "Deploy Docs"]
        sources = [
            {"title": "RAG Guide", "chunk": "..."},
            {"title": "Deploy Docs", "chunk": "..."},
        ]
        result = verify_citations(citations, sources)
        assert result["all_verified"] is True
        assert len(result["valid"]) == 2
        assert len(result["missing"]) == 0

    def test_some_missing(self):
        citations = ["RAG Guide", "Nonexistent"]
        sources = [{"title": "RAG Guide", "chunk": "..."}]
        result = verify_citations(citations, sources)
        assert result["all_verified"] is False
        assert "RAG Guide" in result["valid"]
        assert "Nonexistent" in result["missing"]

    def test_empty_citations(self):
        result = verify_citations([], [{"title": "Doc"}])
        assert result["all_verified"] is True
        assert result["valid"] == []
        assert result["missing"] == []

    def test_empty_sources(self):
        result = verify_citations(["Doc"], [])
        assert result["all_verified"] is False
        assert result["missing"] == ["Doc"]

    def test_partial_match(self):
        """Citation substring match against source title."""
        citations = ["RAG"]
        sources = [{"title": "RAG Guide for Beginners"}]
        result = verify_citations(citations, sources)
        assert "RAG" in result["valid"]


# ── check_hallucination ──


class TestCheckHallucination:
    def _make_mock_llm(self, content: str):
        llm = MagicMock()
        resp = MagicMock()
        resp.content = content
        llm.invoke.return_value = resp
        return llm

    def test_high_score_not_flagged(self):
        llm = self._make_mock_llm('{"score": 9, "flagged": false, "reason": "accurate"}')
        result = check_hallucination("answer", "context", llm, threshold=5)
        assert result["score"] == 9
        assert result["flagged"] is False

    def test_low_score_flagged(self):
        llm = self._make_mock_llm('{"score": 2, "flagged": true, "reason": "inaccurate"}')
        result = check_hallucination("bad answer", "context", llm, threshold=5)
        assert result["score"] == 2
        assert result["flagged"] is True

    def test_json_with_markdown_fence(self):
        llm = self._make_mock_llm('```json\n{"score": 7, "flagged": false, "reason": "ok"}\n```')
        result = check_hallucination("answer", "context", llm)
        assert result["score"] == 7

    def test_llm_exception_returns_safe_default(self):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("LLM down")
        result = check_hallucination("answer", "context", llm)
        assert result["score"] == -1
        assert result["flagged"] is False
        assert "LLM down" in result["reason"]

    def test_invalid_json_returns_safe_default(self):
        llm = self._make_mock_llm("not json at all")
        result = check_hallucination("answer", "context", llm)
        assert result["score"] == -1
        assert result["flagged"] is False
