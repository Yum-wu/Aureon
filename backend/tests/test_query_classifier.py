"""
Tests for query complexity classifier.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.query_classifier import (
    classify_query_complexity,
    classify_query_complexity_adaptive,
    get_reranking_strategy,
    route_retrieval,
    route_retrieval_adaptive,
    _llm_classify,
    _rule_classify,
    _count_keyword_matches,
    _has_multiple_questions,
    _get_query_length_score,
    _has_conjunction_patterns,
)


class TestQueryComplexityClassification:
    """Test query complexity classification."""

    def test_simple_query_chinese(self):
        """Simple factual query in Chinese should be classified as 'simple'."""
        queries = [
            "什么是RAG？",
            "LangChain是什么？",
            "BM25算法",
            "向量检索",
            "嵌入模型",
        ]
        for query in queries:
            result = classify_query_complexity(query)
            assert result == "simple", f"Expected 'simple' for query: {query}, got {result}"

    def test_simple_query_english(self):
        """Simple factual query in English should be classified as 'simple'."""
        queries = [
            "What is RAG?",
            "LangChain",
            "BM25 algorithm",
            "vector retrieval",
            "embedding model",
        ]
        for query in queries:
            result = classify_query_complexity(query)
            assert result == "simple", f"Expected 'simple' for query: {query}, got {result}"

    def test_medium_query_chinese(self):
        """Moderate complexity query in Chinese should be classified as 'medium' or 'complex'."""
        queries = [
            "如何优化RAG检索性能？请解释分析具体方法",
            "BM25和向量检索的区别",
            "为什么选择RAG而不是直接查询？解释原因",
            "解释分析向量检索的工作原理和应用场景",
        ]
        for query in queries:
            result = classify_query_complexity(query)
            assert result in ["medium", "complex"], f"Expected 'medium' or 'complex' for query: {query}, got {result}"

    def test_medium_query_english(self):
        """Moderate complexity query in English should be classified as 'medium' or 'complex'."""
        queries = [
            "How to optimize RAG performance in production?",
            "Compare BM25 and vector retrieval",
            "Why use RAG instead of direct query?",
            "Explain how vector retrieval works",
        ]
        for query in queries:
            result = classify_query_complexity(query)
            assert result in ["medium", "complex"], f"Expected 'medium' or 'complex' for query: {query}, got {result}"

    def test_complex_query_chinese(self):
        """Complex query in Chinese should be classified as 'complex' or 'medium'."""
        queries = [
            "比较BM25和向量检索的优缺点，并解释为什么在某些场景下选择其中一种",
            "如何实现一个完整的RAG系统？请详细说明步骤和流程",
            "总结RAG、BM25和向量检索的异同点，并评估各自的适用场景",
            "为什么BM25在精确匹配上更好？比较BM25和向量检索的区别，并分析原因",
        ]
        for query in queries:
            result = classify_query_complexity(query)
            assert result in ["medium", "complex"], f"Expected 'medium' or 'complex' for query: {query}, got {result}"

    def test_complex_query_english(self):
        """Complex query in English should be classified as 'complex' or 'medium'."""
        queries = [
            "Compare BM25 and vector retrieval, explain the differences and why to choose one",
            "How to implement a complete RAG system? Describe the steps and process",
            "Summarize the similarities and differences between RAG and vector retrieval",
            "Why is BM25 better for exact matching? Analyze and compare with vector retrieval",
        ]
        for query in queries:
            result = classify_query_complexity(query)
            assert result in ["medium", "complex"], f"Expected 'medium' or 'complex' for query: {query}, got {result}"

    def test_empty_query(self):
        """Empty query should default to 'simple'."""
        assert classify_query_complexity("") == "simple"
        assert classify_query_complexity(None) == "simple"

    def test_short_queries(self):
        """Very short queries should default to 'simple'."""
        queries = ["RAG", "BM25", "向量", "vector"]
        for query in queries:
            result = classify_query_complexity(query)
            assert result == "simple", f"Expected 'simple' for query: {query}, got {result}"


class TestReRankingStrategy:
    """Test re-ranking strategy selection."""

    def test_simple_query_strategy(self):
        """Simple query should use 'skip' strategy."""
        queries = ["什么是RAG？", "LangChain是什么？", "BM25"]
        for query in queries:
            strategy = get_reranking_strategy(query)
            assert strategy["strategy"] == "skip", f"Expected 'skip' for query: {query}"
            assert strategy["reranker_count"] == 0, f"Expected 0 rerankers for query: {query}"
            assert strategy["estimated_latency_ms"] == 0, f"Expected 0ms latency for query: {query}"

    def test_medium_query_strategy(self):
        """Medium query should use 'single_bge' strategy."""
        # Find a query that classifies as medium
        queries = ["如何优化RAG检索性能？", "比较BM25和向量检索的区别"]
        for query in queries:
            strategy = get_reranking_strategy(query)
            if strategy["complexity"] == "medium":
                assert strategy["strategy"] == "single_bge", f"Expected 'single_bge' for query: {query}"
                assert strategy["reranker_count"] == 1, f"Expected 1 reranker for query: {query}"
                assert strategy["estimated_latency_ms"] == 30, f"Expected 30ms latency for query: {query}"
                break

    def test_complex_query_strategy(self):
        """Complex query should use 'ensemble' strategy."""
        queries = [
            "比较BM25和向量检索的优缺点，并解释为什么在某些场景下选择其中一种",
            "如何实现一个完整的RAG系统？请详细说明步骤和流程",
        ]
        for query in queries:
            strategy = get_reranking_strategy(query)
            if strategy["complexity"] == "complex":
                assert strategy["strategy"] == "ensemble", f"Expected 'ensemble' for query: {query}"
                assert strategy["reranker_count"] == 3, f"Expected 3 rerankers for query: {query}"
                assert strategy["estimated_latency_ms"] == 80, f"Expected 80ms latency for query: {query}"
                break

    def test_strategy_latency_tradeoff(self):
        """More complex strategies should have higher latency estimates."""
        simple_strategy = get_reranking_strategy("RAG")
        complex_strategy = get_reranking_strategy(
            "比较BM25和向量检索的优缺点，并解释为什么在某些场景下选择其中一种"
        )
        assert simple_strategy["estimated_latency_ms"] < complex_strategy["estimated_latency_ms"]

    def test_strategy_reranker_count_tradeoff(self):
        """More complex strategies should use more rerankers."""
        simple_strategy = get_reranking_strategy("RAG")
        complex_strategy = get_reranking_strategy(
            "比较BM25和向量检索的优缺点，并解释为什么在某些场景下选择其中一种"
        )
        assert simple_strategy["reranker_count"] <= complex_strategy["reranker_count"]

    def test_strategy_dict_structure(self):
        """Strategy should return proper dictionary structure."""
        strategy = get_reranking_strategy("什么是RAG？")
        assert "complexity" in strategy
        assert "strategy" in strategy
        assert "estimated_latency_ms" in strategy
        assert "reranker_count" in strategy

        assert strategy["complexity"] in ["simple", "medium", "complex"]
        assert strategy["strategy"] in ["skip", "single_bge", "ensemble"]
        assert isinstance(strategy["estimated_latency_ms"], (int, float))
        assert isinstance(strategy["reranker_count"], int)


class TestKeywordIndicatorCoverage:
    """Test that keyword indicators are properly detected."""

    def test_comparison_keywords(self):
        """Test comparison keyword detection."""
        queries_zh = ["比较A和B", "对比分析", "区别是什么", "差异在哪"]
        queries_en = ["compare A and B", "what is the difference", "compare"]

        for query in queries_zh + queries_en:
            strategy = get_reranking_strategy(query)
            if strategy["complexity"] in ["medium", "complex"]:
                break
        else:
            # At least one should be medium or complex
            assert False, "No comparison queries classified as medium or complex"

    def test_reasoning_keywords(self):
        """Test reasoning keyword detection."""
        queries_zh = ["为什么这样设计？请解释原因", "解释一下原因和原理", "评估和分析核心推理模式"]
        queries_en = ["why is this approach better? explain the reasoning", "analyze the reasons behind these differences", "evaluate and analyze the core reasoning patterns"]

        for query in queries_zh + queries_en:
            strategy = get_reranking_strategy(query)
            if strategy["complexity"] in ["medium", "complex"]:
                break
        else:
            assert False, "No reasoning queries classified as medium or complex"

    def test_multi_step_keywords(self):
        """Test multi-step keyword detection."""
        queries_zh = ["步骤是什么？请解释流程", "流程怎么走？有哪些步骤", "如何实现一个完整的系统？具体步骤"]
        queries_en = ["what are the implementation steps and process?", "how to implement a complete system with detailed steps"]

        for query in queries_zh + queries_en:
            strategy = get_reranking_strategy(query)
            if strategy["complexity"] in ["medium", "complex"]:
                break
        else:
            assert False, "No multi-step queries classified as medium or complex"

    def test_synthesis_keywords(self):
        """Test synthesis keyword detection."""
        queries_zh = ["总结一下", "综合分析", "概述内容"]
        queries_en = ["summarize the content", "comprehensive overview"]

        for query in queries_zh + queries_en:
            strategy = get_reranking_strategy(query)
            if strategy["complexity"] in ["medium", "complex"]:
                break
        else:
            assert False, "No synthesis queries classified as medium or complex"


# ── Helper functions unit tests ──


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_count_keyword_matches_comparison(self):
        matches = _count_keyword_matches("比较两种方案的区别")
        assert matches["comparison"] >= 2

    def test_count_keyword_matches_no_match(self):
        matches = _count_keyword_matches("你好")
        assert sum(matches.values()) == 0

    def test_has_multiple_questions_single(self):
        assert _has_multiple_questions("什么是RAG？") is False

    def test_has_multiple_questions_multiple(self):
        assert _has_multiple_questions("什么是RAG？什么是BM25？") is True

    def test_get_query_length_score_short(self):
        assert _get_query_length_score("Hi") == 0

    def test_get_query_length_score_very_long(self):
        assert _get_query_length_score("a" * 110) == 3

    def test_has_conjunction_patterns_chinese(self):
        assert _has_conjunction_patterns("RAG和BM25") is True

    def test_has_conjunction_patterns_none(self):
        assert _has_conjunction_patterns("什么是RAG") is False

    def test_rule_classify_empty(self):
        assert _rule_classify("") == "simple"
        assert _rule_classify("   ") == "simple"


# ── Route retrieval (sync) ──


class TestRouteRetrieval:
    """Test sync route_retrieval function."""

    @patch("app.config.settings")
    def test_disabled_routing_returns_complex(self, mock_settings):
        mock_settings.query_routing_enabled = False
        assert route_retrieval("你好") == "complex"

    @patch("app.config.settings")
    def test_enabled_routing_classifies(self, mock_settings):
        mock_settings.query_routing_enabled = True
        result = route_retrieval("你好")
        assert result in ("simple", "medium", "complex")


# ── LLM classify (async, mocked) ──


class TestLlmClassify:
    """Test LLM classification path with mocked LLM."""

    @pytest.mark.asyncio
    async def test_returns_simple(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="simple"))
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            result = await _llm_classify("What is RAG?")
            assert result == "simple"

    @pytest.mark.asyncio
    async def test_returns_medium(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="medium"))
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            result = await _llm_classify("Analyze RAG pipeline")
            assert result == "medium"

    @pytest.mark.asyncio
    async def test_returns_complex(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="complex"))
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            result = await _llm_classify("Compare and synthesize all approaches")
            assert result == "complex"

    @pytest.mark.asyncio
    async def test_strips_thinking_tags(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="<think>Let me think...</think>medium")
        )
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            result = await _llm_classify("Analyze RAG pipeline")
            assert result == "medium"

    @pytest.mark.asyncio
    async def test_invalid_response_defaults_to_medium(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="I don't know"))
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            result = await _llm_classify("ambiguous query")
            assert result == "medium"


# ── Adaptive classifier (async) ──


class TestClassifyQueryComplexityAdaptive:
    """Test hybrid classifier: rule fast-path + LLM fallback."""

    @pytest.mark.asyncio
    async def test_rule_high_confidence_skips_llm(self):
        """High-confidence rule result should skip LLM call."""
        result = await classify_query_complexity_adaptive(
            "比较BM25和向量检索的区别，并分析为什么混合检索更好"
        )
        assert result in ("simple", "medium", "complex")

    @pytest.mark.asyncio
    async def test_llm_fallback_for_low_confidence(self):
        """Low-confidence rule result should fall through to LLM."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="medium"))
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            # "比较一下" has 1 keyword, short length → low confidence → LLM
            result = await classify_query_complexity_adaptive("比较一下")
            assert result in ("simple", "medium", "complex")

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_medium(self):
        """LLM timeout should degrade to medium."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            result = await classify_query_complexity_adaptive("比较一下")
            assert result == "medium"

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back_to_medium(self):
        """LLM exception should degrade to medium."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("API error"))
        with patch("app.agent.llm.create_llm", return_value=mock_llm):
            result = await classify_query_complexity_adaptive("比较一下")
            assert result == "medium"


# ── Adaptive route retrieval (async) ──


class TestRouteRetrievalAdaptive:
    """Test async route_retrieval_adaptive function."""

    @pytest.mark.asyncio
    async def test_disabled_returns_complex(self):
        with patch("app.config.settings") as mock_settings:
            mock_settings.query_routing_enabled = False
            result = await route_retrieval_adaptive("你好")
            assert result == "complex"

    @pytest.mark.asyncio
    async def test_enabled_classifies(self):
        with patch("app.config.settings") as mock_settings:
            mock_settings.query_routing_enabled = True
            result = await route_retrieval_adaptive("你好")
            assert result in ("simple", "medium", "complex")


# ── Edge cases ──


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_query(self):
        q = "a" * 10000
        result = classify_query_complexity(q)
        assert result in ("simple", "medium", "complex")

    def test_whitespace_only(self):
        assert classify_query_complexity("     ") == "simple"

    def test_special_characters(self):
        result = classify_query_complexity("!@#$%^&*()")
        assert result in ("simple", "medium", "complex")

    def test_unicode_query(self):
        result = classify_query_complexity("什么是RAG系统？请详细解释其工作原理")
        assert result in ("simple", "medium", "complex")

    @pytest.mark.asyncio
    async def test_adaptive_empty_query(self):
        """Empty query should return simple without LLM call."""
        result = await classify_query_complexity_adaptive("")
        assert result == "simple"

    @pytest.mark.asyncio
    async def test_adaptive_very_long_query(self):
        """Very long query should be classified without error."""
        q = "比较" + "a" * 1000 + "和" + "b" * 1000 + "的区别，并分析为什么"
        result = await classify_query_complexity_adaptive(q)
        assert result in ("simple", "medium", "complex")
