"""Tests for app.rag.query_rewriter — rewrite_query, expand_queries,
is_cross_article_query, expand_queries_rules."""

import pytest
from unittest.mock import MagicMock

from app.rag.query_rewriter import (
    rewrite_query,
    expand_queries,
    is_cross_article_query,
    expand_queries_rules,
)


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


# ── is_cross_article_query ──


class TestIsCrossArticleQuery:
    # Chinese intent detection
    def test_chinese_compare(self):
        assert is_cross_article_query("这两篇文章有什么区别") is True

    def test_chinese_common(self):
        assert is_cross_article_query("这两篇的共同点是什么") is True

    def test_chinese_diff(self):
        assert is_cross_article_query("两篇文章的差异") is True

    def test_chinese_summary(self):
        assert is_cross_article_query("综合所有文章的内容") is True

    # English intent detection
    def test_english_compare(self):
        assert is_cross_article_query("compare these articles") is True

    def test_english_difference(self):
        assert is_cross_article_query("what are the differences between the documents") is True

    def test_english_common(self):
        assert is_cross_article_query("find commonalities across articles") is True

    def test_english_summary(self):
        assert is_cross_article_query("summarize all articles") is True

    # Simple queries should return False
    def test_simple_chinese_query(self):
        assert is_cross_article_query("什么是RAG检索增强生成") is False

    def test_simple_english_query(self):
        assert is_cross_article_query("how does the RAG pipeline work") is False

    # Empty query
    def test_empty_query(self):
        assert is_cross_article_query("") is False
        assert is_cross_article_query(None) is False

    # Case insensitive
    def test_english_case_insensitive(self):
        assert is_cross_article_query("COMPARE these two articles") is True


# ── expand_queries_rules ──


class TestExpandQueriesRules:
    def test_zh_split(self):
        result = expand_queries_rules("RAG和向量数据库的区别")
        assert len(result) >= 2
        assert "RAG和向量数据库的区别" in result

    def test_en_split(self):
        result = expand_queries_rules("RAG and vector databases comparison")
        assert len(result) >= 2
        assert "RAG and vector databases comparison" in result

    def test_en_vs_split(self):
        result = expand_queries_rules("LangChain vs LlamaIndex differences")
        assert len(result) >= 2
        assert "LangChain vs LlamaIndex differences" in result

    def test_generic_cross_article_expansion(self):
        result = expand_queries_rules("比较RAG和传统搜索")
        assert len(result) >= 2

    def test_returns_list_of_strings(self):
        result = expand_queries_rules("anything")
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)
        assert all(len(s) > 0 for s in result)

    def test_deduplication(self):
        result = expand_queries_rules("RAG RAG RAG")
        assert len(result) == len(set(result))
