# -*- coding: utf-8 -*-
"""Tests for app.rag.query_rewriter — is_cross_article_query, expand_queries_rules.

Note: rewrite_query and expand_queries were removed as dead code (LLM-based
versions never called in production). Only rule-based functions are tested.
"""


from app.rag.query_rewriter import (
    is_cross_article_query,
    expand_queries_rules,
)


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
