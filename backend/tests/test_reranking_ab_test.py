"""Tests for A/B Testing Framework for Re-ranking Strategies."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.evaluation.reranking_ab_test import RerankingABTest, ABTestResult


class TestRerankingABTestInitialization:
    """Test A/B test initialization."""

    def test_initialization(self):
        """Test basic A/B test initialization."""
        test_queries = [
            {"query": "什么是RAG？", "expected_docs": ["rag-1"]},
            {"query": "BM25原理", "expected_docs": ["bm25-1"]},
        ]
        ground_truth = [["rag-1"], ["bm25-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)
        assert ab_test.test_queries == test_queries
        assert ab_test.ground_truth == ground_truth
        assert ab_test._results_cache == {}

    def test_initialization_mismatched_lengths(self):
        """Test initialization fails with mismatched lengths."""
        test_queries = [
            {"query": "query1", "expected_docs": ["doc-1"]},
            {"query": "query2", "expected_docs": ["doc-2"]},
        ]
        ground_truth = [["doc-1"]]  # Different length

        with pytest.raises(ValueError, match="must have the same length"):
            RerankingABTest(test_queries, ground_truth)

    def test_initialization_empty(self):
        """Test initialization with empty lists."""
        test_queries = []
        ground_truth = []

        ab_test = RerankingABTest(test_queries, ground_truth)
        assert len(ab_test.test_queries) == 0
        assert len(ab_test.ground_truth) == 0


class TestMetricsCalculation:
    """Test metric calculation."""

    def test_metrics_calculation_perfect_retrieval(self):
        """Test metrics with perfect retrieval."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        # Mock results - perfect retrieval
        results = [
            {
                "strategy": "test",
                "query": "test",
                "results": [{"metadata": {"slug": "doc-1"}, "text": "..."}],
                "latency_ms": 10.0,
                "result_count": 1,
            },
        ]

        metrics = ab_test._calculate_metrics(results, ground_truth)

        assert "context_precision" in metrics
        assert "recall_at_3" in metrics
        assert "mrr" in metrics
        assert "latency_p50_ms" in metrics
        assert "latency_p90_ms" in metrics
        assert "latency_p99_ms" in metrics
        assert "total_queries" in metrics

        # Perfect retrieval -> precision = 1.0, recall = 1.0, MRR = 1.0
        assert metrics["context_precision"] == pytest.approx(1.0)
        assert metrics["recall_at_3"] == pytest.approx(1.0)
        assert metrics["mrr"] == pytest.approx(1.0)
        assert metrics["total_queries"] == 1

    def test_metrics_calculation_partial_retrieval(self):
        """Test metrics with partial retrieval."""
        test_queries = [
            {"query": "query1", "expected_docs": ["doc-1", "doc-2"]},
            {"query": "query2", "expected_docs": ["doc-3"]},
        ]
        ground_truth = [["doc-1", "doc-2"], ["doc-3"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        # Query 1: retrieved doc-1 and doc-3 (one relevant, one irrelevant)
        # Query 2: retrieved doc-3 (relevant)
        results = [
            {
                "strategy": "test",
                "query": "query1",
                "results": [
                    {"metadata": {"slug": "doc-1"}, "text": "..."},
                    {"metadata": {"slug": "doc-3"}, "text": "..."},
                ],
                "latency_ms": 15.0,
                "result_count": 2,
            },
            {
                "strategy": "test",
                "query": "query2",
                "results": [{"metadata": {"slug": "doc-3"}, "text": "..."}],
                "latency_ms": 8.0,
                "result_count": 1,
            },
        ]

        metrics = ab_test._calculate_metrics(results, ground_truth)

        # Query 1: precision = 1/2 = 0.5, recall = 1/2 = 0.5, MRR = 1/1 = 1.0
        # Query 2: precision = 1/1 = 1.0, recall = 1/1 = 1.0, MRR = 1/1 = 1.0
        # Average: precision = 0.75, recall = 0.75, MRR = 1.0
        assert metrics["context_precision"] == pytest.approx(0.75)
        assert metrics["recall_at_3"] == pytest.approx(0.75)
        assert metrics["mrr"] == pytest.approx(1.0)

    def test_metrics_calculation_no_retrieval(self):
        """Test metrics with no retrieval results."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        # No results returned
        results = [
            {
                "strategy": "test",
                "query": "test",
                "results": [],
                "latency_ms": 5.0,
                "result_count": 0,
            },
        ]

        metrics = ab_test._calculate_metrics(results, ground_truth)

        assert metrics["context_precision"] == pytest.approx(0.0)
        assert metrics["recall_at_3"] == pytest.approx(0.0)
        assert metrics["mrr"] == pytest.approx(0.0)
        assert metrics["total_queries"] == 1

    def test_metrics_calculation_mrr_ranking(self):
        """Test MRR calculation with different rankings."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        # Relevant doc at position 2 -> MRR = 1/2 = 0.5
        results = [
            {
                "strategy": "test",
                "query": "test",
                "results": [
                    {"metadata": {"slug": "doc-2"}, "text": "..."},  # Not relevant
                    {"metadata": {"slug": "doc-1"}, "text": "..."},  # Relevant
                ],
                "latency_ms": 12.0,
                "result_count": 2,
            },
        ]

        metrics = ab_test._calculate_metrics(results, ground_truth)
        assert metrics["mrr"] == pytest.approx(0.5)

    def test_metrics_latency_percentiles(self):
        """Test latency percentile calculation."""
        test_queries = [{"query": f"query{i}", "expected_docs": ["doc"]} for i in range(10)]
        ground_truth = [["doc"]] * 10

        ab_test = RerankingABTest(test_queries, ground_truth)

        # Create results with different latencies
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        results = [
            {
                "strategy": "test",
                "query": f"query{i}",
                "results": [{"metadata": {"slug": "doc"}, "text": "..."}],
                "latency_ms": lat,
                "result_count": 1,
            }
            for i, lat in enumerate(latencies)
        ]

        metrics = ab_test._calculate_metrics(results, ground_truth)

        # Percentiles from sorted list [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        # np.percentile uses linear interpolation by default
        assert metrics["latency_p50_ms"] == pytest.approx(55.0)   # median of 50 and 60
        assert metrics["latency_p90_ms"] == pytest.approx(91.0)   # linear interp at 90%
        assert metrics["latency_p99_ms"] == pytest.approx(99.1)   # linear interp at 99%


class TestStrategyComparison:
    """Test strategy comparison."""

    @pytest.mark.asyncio
    async def test_compare_strategies(self):
        """Test comparing multiple strategies."""
        test_queries = [
            {"query": "test1", "expected_docs": ["doc-1"]},
            {"query": "test2", "expected_docs": ["doc-2"]},
        ]
        ground_truth = [["doc-1"], ["doc-2"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        # Mock strategy functions
        async def mock_strategy_a(query: str, top_k: int = 3):
            return [{"metadata": {"slug": "doc-1"}, "text": "..."}]

        async def mock_strategy_b(query: str, top_k: int = 3):
            return [{"metadata": {"slug": "doc-2"}, "text": "..."}]

        strategies = {
            "strategy_a": mock_strategy_a,
            "strategy_b": mock_strategy_b,
        }

        results = await ab_test.compare_strategies(strategies, top_k=3)

        assert len(results) == 2
        assert isinstance(results[0], ABTestResult)
        assert isinstance(results[1], ABTestResult)
        assert results[0].strategy == "strategy_a"
        assert results[1].strategy == "strategy_b"

    @pytest.mark.asyncio
    async def test_compare_strategies_with_errors(self):
        """Test strategy comparison with errors."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        # Mock strategy that raises an error
        async def failing_strategy(query: str, top_k: int = 3):
            raise RuntimeError("Strategy failed")

        async def working_strategy(query: str, top_k: int = 3):
            return [{"metadata": {"slug": "doc-1"}, "text": "..."}]

        strategies = {
            "failing": failing_strategy,
            "working": working_strategy,
        }

        results = await ab_test.compare_strategies(strategies, top_k=3)

        assert len(results) == 2
        # Both should have results, even if one failed
        assert results[0].total_queries == 1
        assert results[1].total_queries == 1

    @pytest.mark.asyncio
    async def test_compare_strategies_caches_results(self):
        """Test that strategy results are cached."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        async def mock_strategy(query: str, top_k: int = 3):
            return [{"metadata": {"slug": "doc-1"}, "text": "..."}]

        strategies = {"test_strategy": mock_strategy}
        await ab_test.compare_strategies(strategies, top_k=3)

        # Results should be cached
        cached = ab_test.get_strategy_results("test_strategy")
        assert cached is not None
        assert len(cached) == 1


class TestReportGeneration:
    """Test report generation."""

    def test_generate_report(self):
        """Test report generation."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        results = [
            ABTestResult(
                strategy="no_rerank",
                context_precision=0.85,
                recall_at_3=0.90,
                mrr=0.75,
                latency_p50_ms=15.0,
                latency_p90_ms=25.0,
                latency_p99_ms=45.0,
                total_queries=10,
            ),
            ABTestResult(
                strategy="single_bge",
                context_precision=0.92,
                recall_at_3=0.95,
                mrr=0.88,
                latency_p50_ms=22.0,
                latency_p90_ms=35.0,
                latency_p99_ms=60.0,
                total_queries=10,
            ),
        ]

        report = ab_test.generate_report(results)

        assert "A/B TEST REPORT" in report
        assert "no_rerank" in report
        assert "single_bge" in report
        assert "WINNER ANALYSIS" in report
        assert "Best Precision" in report
        assert "Best Recall@3" in report

    def test_generate_report_empty_results(self):
        """Test report with empty results."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        report = ab_test.generate_report([])
        assert "No results to report" in report


class TestCacheManagement:
    """Test cache management."""

    def test_clear_cache(self):
        """Test clearing the cache."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        # Manually add to cache
        ab_test._results_cache["test"] = [{"some": "data"}]
        assert ab_test.get_strategy_results("test") is not None

        # Clear cache
        ab_test.clear_cache()
        assert ab_test.get_strategy_results("test") is None

    def test_get_strategy_results_not_found(self):
        """Test getting results for non-existent strategy."""
        test_queries = [{"query": "test", "expected_docs": ["doc-1"]}]
        ground_truth = [["doc-1"]]

        ab_test = RerankingABTest(test_queries, ground_truth)

        result = ab_test.get_strategy_results("nonexistent")
        assert result is None
