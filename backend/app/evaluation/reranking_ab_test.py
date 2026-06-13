"""
A/B Testing Framework for Re-ranking Strategies.

Compares different re-ranking approaches:
- No re-ranking (baseline)
- Single BGE reranker
- Ensemble reranking

Measures:
- Context Precision
- Recall@K
- MRR (Mean Reciprocal Rank)
- Latency (p50, p90, p99)
"""

import time
import asyncio
import inspect
import numpy as np
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class ABTestResult:
    """Result from A/B test comparison."""

    strategy: str
    context_precision: float
    recall_at_3: float
    mrr: float
    latency_p50_ms: float
    latency_p90_ms: float
    latency_p99_ms: float
    total_queries: int


class RerankingABTest:
    """A/B test framework for re-ranking strategies.

    Compares:
    - No re-ranking (baseline)
    - Single BGE reranker
    - Ensemble reranking

    Measures:
    - Context Precision
    - Recall@K
    - MRR (Mean Reciprocal Rank)
    - Latency (p50, p90, p99)
    """

    def __init__(
        self,
        test_queries: List[Dict[str, Any]],
        ground_truth: List[List[str]],
    ):
        """Initialize A/B test.

        Args:
            test_queries: List of query dicts with 'query' and 'expected_docs'
            ground_truth: List of expected document IDs for each query
        """
        if len(test_queries) != len(ground_truth):
            raise ValueError(
                f"test_queries ({len(test_queries)}) and ground_truth ({len(ground_truth)}) "
                "must have the same length"
            )

        self.test_queries = test_queries
        self.ground_truth = ground_truth
        self._results_cache: Dict[str, List[Dict[str, Any]]] = {}

        logger.info(
            "RerankingABTest initialized: %d queries, %d ground_truth entries",
            len(test_queries),
            len(ground_truth),
        )

    async def compare_strategies(
        self,
        strategies: Dict[str, Callable],
        top_k: int = 3,
    ) -> List[ABTestResult]:
        """Compare multiple re-ranking strategies.

        Args:
            strategies: Dict of strategy_name -> retrieve_function
            top_k: Number of results to return

        Returns:
            List of ABTestResult for each strategy
        """
        results: List[ABTestResult] = []

        for strategy_name, strategy_fn in strategies.items():
            logger.info("Running A/B test for strategy: %s", strategy_name)

            # Execute strategy for all queries and measure latency
            strategy_results = []
            latencies = []

            for query_dict in self.test_queries:
                query = query_dict["query"]

                # Measure latency
                start_time = time.perf_counter()

                try:
                    # Check if strategy is async
                    if inspect.iscoroutinefunction(strategy_fn):
                        query_results = await strategy_fn(query, top_k=top_k)
                    else:
                        query_results = await asyncio.to_thread(
                            strategy_fn, query, top_k=top_k
                        )

                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    strategy_results.append(
                        {
                            "strategy": strategy_name,
                            "query": query,
                            "results": query_results,
                            "latency_ms": elapsed_ms,
                            "result_count": len(query_results),
                        }
                    )
                    latencies.append(elapsed_ms)

                except Exception as e:
                    logger.error(
                        "Strategy %s failed for query '%s': %s",
                        strategy_name,
                        query[:50],
                        str(e),
                    )
                    strategy_results.append(
                        {
                            "strategy": strategy_name,
                            "query": query,
                            "results": [],
                            "latency_ms": 0.0,
                            "result_count": 0,
                        }
                    )

            # Calculate metrics
            metrics = self._calculate_metrics(strategy_results, self.ground_truth)

            ab_result = ABTestResult(
                strategy=strategy_name,
                context_precision=metrics["context_precision"],
                recall_at_3=metrics["recall_at_3"],
                mrr=metrics["mrr"],
                latency_p50_ms=metrics["latency_p50_ms"],
                latency_p90_ms=metrics["latency_p90_ms"],
                latency_p99_ms=metrics["latency_p99_ms"],
                total_queries=metrics["total_queries"],
            )
            results.append(ab_result)

            # Cache results for potential analysis
            self._results_cache[strategy_name] = strategy_results

            logger.info(
                "Strategy %s completed: precision=%.3f, recall@3=%.3f, mrr=%.3f, p50=%.1fms",
                strategy_name,
                ab_result.context_precision,
                ab_result.recall_at_3,
                ab_result.mrr,
                ab_result.latency_p50_ms,
            )

        return results

    def _calculate_metrics(
        self,
        results: List[Dict[str, Any]],
        ground_truth: List[List[str]],
    ) -> Dict[str, float]:
        """Calculate evaluation metrics from results.

        Metrics computed:
        - Context Precision: fraction of retrieved docs that are relevant
        - Recall@K: fraction of relevant docs that are retrieved
        - MRR: Mean Reciprocal Rank of first relevant result

        Args:
            results: List of result dicts with 'results', 'latency_ms', etc.
            ground_truth: List of expected document IDs for each query

        Returns:
            Dict with metric values
        """
        precisions: List[float] = []
        recalls: List[float] = []
        mrrs: List[float] = []
        latencies: List[float] = []

        for result, expected in zip(results, ground_truth):
            retrieved_ids = [
                r.get("metadata", {}).get("slug", "")
                for r in result.get("results", [])
                if r.get("metadata", {}).get("slug")
            ]

            # Context Precision: fraction of retrieved docs that are relevant
            if retrieved_ids:
                relevant_retrieved = len(set(retrieved_ids) & set(expected))
                precision = relevant_retrieved / len(retrieved_ids)
            else:
                precision = 0.0
            precisions.append(precision)

            # Recall@K: fraction of relevant docs that are retrieved
            if expected:
                recall = len(set(retrieved_ids) & set(expected)) / len(expected)
            else:
                recall = 0.0
            recalls.append(recall)

            # MRR: reciprocal rank of first relevant result
            mrr = 0.0
            for i, doc_id in enumerate(retrieved_ids):
                if doc_id in expected:
                    mrr = 1.0 / (i + 1)
                    break
            mrrs.append(mrr)

            latencies.append(result.get("latency_ms", 0.0))

        # Calculate percentile latencies
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)

        if n == 0:
            return {
                "context_precision": 0.0,
                "recall_at_3": 0.0,
                "mrr": 0.0,
                "latency_p50_ms": 0.0,
                "latency_p90_ms": 0.0,
                "latency_p99_ms": 0.0,
                "total_queries": 0,
            }

        lat_arr = np.array(latencies_sorted)
        return {
            "context_precision": sum(precisions) / len(precisions) if precisions else 0.0,
            "recall_at_3": sum(recalls) / len(recalls) if recalls else 0.0,
            "mrr": sum(mrrs) / len(mrrs) if mrrs else 0.0,
            "latency_p50_ms": float(np.percentile(lat_arr, 50)) if n > 0 else 0.0,
            "latency_p90_ms": float(np.percentile(lat_arr, 90)) if n > 0 else 0.0,
            "latency_p99_ms": float(np.percentile(lat_arr, 99)) if n > 0 else 0.0,
            "total_queries": len(results),
        }

    def generate_report(self, results: List[ABTestResult]) -> str:
        """Generate human-readable comparison report.

        Args:
            results: List of ABTestResult from compare_strategies

        Returns:
            Formatted string report
        """
        if not results:
            return "No results to report."

        lines = []
        lines.append("=" * 70)
        lines.append("A/B TEST REPORT: Re-ranking Strategy Comparison")
        lines.append("=" * 70)
        lines.append("")

        # Summary table
        lines.append("STRATEGY SUMMARY")
        lines.append("-" * 70)
        header = f"{'Strategy':<20} {'Precision':>10} {'Recall@3':>10} {'MRR':>10} {'P50 Lat':>10}"
        lines.append(header)
        lines.append("-" * 70)

        for result in results:
            line = (
                f"{result.strategy:<20} "
                f"{result.context_precision:>10.3f} "
                f"{result.recall_at_3:>10.3f} "
                f"{result.mrr:>10.3f} "
                f"{result.latency_p50_ms:>9.1f}ms"
            )
            lines.append(line)

        lines.append("-" * 70)
        lines.append("")

        # Detailed latency breakdown
        lines.append("LATENCY BREAKDOWN (ms)")
        lines.append("-" * 70)
        header = f"{'Strategy':<20} {'P50':>8} {'P90':>8} {'P99':>8}"
        lines.append(header)
        lines.append("-" * 70)

        for result in results:
            line = (
                f"{result.strategy:<20} "
                f"{result.latency_p50_ms:>7.1f} "
                f"{result.latency_p90_ms:>7.1f} "
                f"{result.latency_p99_ms:>7.1f}"
            )
            lines.append(line)

        lines.append("-" * 70)
        lines.append("")

        # Winner analysis
        if len(results) > 1:
            best_precision = max(results, key=lambda r: r.context_precision)
            best_recall = max(results, key=lambda r: r.recall_at_3)
            best_mrr = max(results, key=lambda r: r.mrr)
            best_latency = min(results, key=lambda r: r.latency_p50_ms)

            lines.append("WINNER ANALYSIS")
            lines.append("-" * 70)
            lines.append(f"  Best Precision:      {best_precision.strategy} ({best_precision.context_precision:.3f})")
            lines.append(f"  Best Recall@3:       {best_recall.strategy} ({best_recall.recall_at_3:.3f})")
            lines.append(f"  Best MRR:            {best_mrr.strategy} ({best_mrr.mrr:.3f})")
            lines.append(f"  Lowest Latency:      {best_latency.strategy} ({best_latency.latency_p50_ms:.1f}ms)")
            lines.append("-" * 70)
            lines.append("")

        lines.append(f"Total queries tested: {results[0].total_queries if results else 0}")
        lines.append("=" * 70)

        report = "\n".join(lines)

        logger.info("A/B test report generated (%d strategies)", len(results))
        return report

    def get_strategy_results(self, strategy_name: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached results for a specific strategy.

        Args:
            strategy_name: Name of the strategy

        Returns:
            List of result dicts or None if not found
        """
        return self._results_cache.get(strategy_name)

    def clear_cache(self) -> None:
        """Clear cached results."""
        self._results_cache.clear()
        logger.debug("A/B test results cache cleared")


async def run_ab_test():
    """Run A/B test with sample data.

    Example usage showing how to compare different retrieval strategies.
    """
    from app.rag.qa_chain import hybrid_retrieve, multi_query_retrieve

    # Sample test queries with ground truth
    test_queries = [
        {"query": "什么是RAG？", "expected_docs": ["rag-intro"]},
        {"query": "BM25和向量检索的区别", "expected_docs": ["bm25", "vector-search"]},
    ]

    ground_truth = [
        ["rag-intro"],
        ["bm25", "vector-search"],
    ]

    # Define strategies
    def no_rerank(query: str, top_k: int = 3):
        """Baseline: no re-ranking."""
        return hybrid_retrieve(query, top_k=top_k)

    def single_bge(query: str, top_k: int = 3):
        """Single BGE reranker."""
        return multi_query_retrieve(query, top_k=top_k)

    strategies = {
        "no_rerank": no_rerank,
        "single_bge": single_bge,
    }

    # Run A/B test
    ab_test = RerankingABTest(test_queries, ground_truth)
    results = await ab_test.compare_strategies(strategies, top_k=3)

    # Generate report
    report = ab_test.generate_report(results)
    logger.info("reranking_ab.report", report=report)

    return results


if __name__ == "__main__":
    asyncio.run(run_ab_test())
