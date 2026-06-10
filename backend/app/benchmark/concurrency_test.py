"""Concurrency test suite for 100 concurrent connections."""

import asyncio
import time
from typing import List, Dict, Any
import structlog

logger = structlog.get_logger()

# Concurrency test levels
CONCURRENCY_LEVELS = [1, 10, 25, 50, 75, 100]

# Performance thresholds
THRESHOLDS = {
    "min_qps_at_100": 50,
    "max_p99_at_100_ms": 3000,
    "min_success_rate": 0.95,
    "max_timeout_rate": 0.05,
    "max_429_rate": 0.01,
}


class ConcurrencyTestSuite:
    """Test system under high concurrency load."""

    def __init__(self):
        self.results: List[Dict[str, Any]] = []

    async def test_http_concurrent(
        self,
        client,
        queries: List[str],
        concurrency: int,
    ) -> Dict[str, Any]:
        """Run concurrent HTTP requests.

        Args:
            client: RailwayBenchmarkClient instance
            queries: List of query strings to use
            concurrency: Number of concurrent requests

        Returns:
            Dictionary with test results
        """
        semaphore = asyncio.Semaphore(concurrency)
        tasks = []

        # Create tasks with rotating queries
        for i in range(concurrency):
            query = queries[i % len(queries)]
            task = self._throttled_query(client, query, semaphore)
            tasks.append(task)

        # Execute all tasks
        start = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.perf_counter() - start

        # Analyze results
        successes = [r for r in results if not isinstance(r, Exception) and r.get("success")]
        failures = [r for r in results if isinstance(r, Exception) or not r.get("success")]

        # Count bottleneck types
        bottlenecks = []
        rate_limits = sum(1 for r in failures if "429" in str(r))
        timeouts = sum(1 for r in failures if "timeout" in str(r).lower())

        if rate_limits > 0:
            bottlenecks.append(f"rate_limit: {rate_limits}")
        if timeouts > 0:
            bottlenecks.append(f"timeout: {timeouts}")

        return {
            "concurrency": concurrency,
            "total_queries": len(results),
            "successes": len(successes),
            "failures": len(failures),
            "elapsed_seconds": round(elapsed, 2),
            "qps": round(concurrency / elapsed, 2) if elapsed > 0 else 0,
            "avg_latency_ms": round(
                sum(r.get("latency_ms", 0) for r in successes) / max(len(successes), 1),
                1,
            ),
            "p99_latency_ms": self._calculate_p99(successes),
            "bottlenecks": bottlenecks,
            "success_rate": len(successes) / len(results) if results else 0,
        }

    async def _throttled_query(self, client, query: str, semaphore: asyncio.Semaphore):
        """Execute query with concurrency control."""
        async with semaphore:
            try:
                start = time.perf_counter()
                results = await client.retrieve(query, top_k=5)
                latency = (time.perf_counter() - start) * 1000

                return {
                    "success": True,
                    "latency_ms": latency,
                    "results_count": len(results),
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "latency_ms": 0,
                }

    def _calculate_p99(self, results: List[Dict]) -> float:
        """Calculate P99 latency from results."""
        if not results:
            return 0.0

        latencies = sorted([r.get("latency_ms", 0) for r in results])
        idx = int(len(latencies) * 0.99)
        return round(latencies[min(idx, len(latencies) - 1)], 1)

    def validate_thresholds(self, result: Dict) -> Dict[str, bool]:
        """Validate results against thresholds."""
        passed = {}

        if result["concurrency"] == 100:
            passed["qps"] = result["qps"] >= THRESHOLDS["min_qps_at_100"]
            passed["p99_latency"] = result["p99_latency_ms"] <= THRESHOLDS["max_p99_at_100_ms"]
            passed["success_rate"] = result["success_rate"] >= THRESHOLDS["min_success_rate"]

        return passed
