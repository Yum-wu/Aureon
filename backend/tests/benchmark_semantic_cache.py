"""
Semantic Cache Benchmark

Measures cache performance across multiple dimensions:
- Cache hit rate for exact vs semantic queries
- Latency comparison (exact cache vs semantic cache vs LLM fallback)
- Memory usage tracking
- Similarity threshold sensitivity analysis

Usage:
    cd backend
    python -m tests.benchmark_semantic_cache
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Test Data ─────────────────────────────────────────────────────────────────

TEST_CASES: List[Tuple[str, str, bool]] = [
    # (query, expected_similar_to, expected_hit)
    ("什么是RAG？", "RAG是什么？", True),
    ("如何优化检索性能？", "检索性能优化方法", True),
    ("BM25算法原理", "BM25的工作原理", True),
    ("完全不同的问题", "什么是RAG？", False),
]

WARMUP_QUERIES: List[Tuple[str, str]] = [
    # (query, response)
    ("什么是RAG？", "RAG（Retrieval-Augmented Generation）是一种结合检索和生成的AI技术。"),
    ("如何优化检索性能？", "可以通过调整BM25参数、使用向量索引、优化分块策略来提升检索性能。"),
    ("BM25算法原理", "BM25是一种基于概率的信息检索算法，通过词频、逆文档频率和文档长度来计算相关性分数。"),
]

MODEL = "deepseek"
TEMPERATURE = 0.0
MAX_TOKENS = 500
TTL = 3600


@dataclass
class BenchmarkResult:
    """Structured result from a single benchmark run."""

    name: str
    data: Dict = field(default_factory=dict)
    duration_ms: float = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_header():
    print("=" * 64)
    print("Semantic Cache Benchmark")
    print("=" * 64)


def _print_section(title: str):
    print()
    print(title)


def _check_redis() -> bool:
    """Return True if Redis is reachable."""
    try:
        import redis.asyncio as aioredis
        from app.config import settings

        r = aioredis.from_url(
            settings.redis_url or "redis://localhost:6379/0",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

        async def _ping():
            try:
                await r.ping()
                await r.close()
                return True
            except Exception:
                try:
                    await r.close()
                except Exception:
                    pass
                return False

        return asyncio.run(_ping())
    except Exception:
        return False


# ── Benchmark Functions ───────────────────────────────────────────────────────

async def benchmark_cache_hit_rate() -> BenchmarkResult:
    """Warm up the cache and measure hit rate across similar query pairs.

    Populates cache with WARMUP_QUERIES, then queries each test case
    and checks whether the cache returns a hit when expected.
    """
    from app.cache.semantic_cache import SemanticLLMCache

    start = time.monotonic()
    cache = SemanticLLMCache(
        similarity_threshold=0.92,
        default_ttl=TTL,
        max_cache_size=10000,
    )

    # 1. Warm up
    _print_section("1. Warming up cache...")
    for query, response in WARMUP_QUERIES:
        await cache.set(
            query=query,
            response=response,
            model=MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        print(f"   Cached: {query}")

    # 2. Test hits
    _print_section("2. Testing cache hits...")
    hits = 0
    total = len(TEST_CASES)
    test_results: List[Dict] = []

    for query, _expected_similar_to, expected_hit in TEST_CASES:
        t0 = time.monotonic()

        # Try exact first
        exact = await cache.get_exact(
            query, MODEL, TEMPERATURE, MAX_TOKENS
        )
        if exact is not None:
            got_hit = True
            latency_ms = (time.monotonic() - t0) * 1000
        else:
            # Try semantic
            sem = await cache.get_semantic(
                query, MODEL, TEMPERATURE, MAX_TOKENS
            )
            if sem is not None:
                got_hit = True
                latency_ms = (time.monotonic() - t0) * 1000
            else:
                got_hit = False
                latency_ms = (time.monotonic() - t0) * 1000

        if got_hit:
            hits += 1

        status = "OK" if got_hit == expected_hit else "MISMATCH"
        print(
            f"   Query: {query}\n"
            f"      Expected hit: {expected_hit}, Got: {got_hit} "
            f"({latency_ms:.2f}ms) [{status}]"
        )
        test_results.append(
            {
                "query": query,
                "expected_hit": expected_hit,
                "got_hit": got_hit,
                "match": got_hit == expected_hit,
                "latency_ms": latency_ms,
            }
        )

    hit_rate = hits / total * 100 if total > 0 else 0.0
    print(f"\n   Hit rate: {hit_rate:.1f}%")

    await cache.close()

    return BenchmarkResult(
        name="cache_hit_rate",
        data={
            "hit_rate": hit_rate,
            "hits": hits,
            "total": total,
            "tests": test_results,
        },
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def benchmark_latency() -> BenchmarkResult:
    """Compare latency across the three cache layers.

    Measures:
    - Exact cache hit latency (in-memory)
    - Semantic cache hit latency (embedding computation + cosine)
    - Estimated LLM call latency (baseline, no real call)
    """
    from app.cache.semantic_cache import SemanticLLMCache

    start = time.monotonic()
    cache = SemanticLLMCache(
        similarity_threshold=0.92,
        default_ttl=TTL,
        max_cache_size=10000,
    )

    _print_section("3. Latency comparison...")

    # Seed cache with a known entry
    seed_query = "什么是RAG？"
    seed_response = "RAG是一种结合检索和生成的AI技术。"
    await cache.set(
        query=seed_query,
        response=seed_response,
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    # ── Exact cache latency ───────────────────────────────────────────────
    exact_latencies: List[float] = []
    for _ in range(50):
        t0 = time.monotonic()
        await cache.get_exact(
            seed_query, MODEL, TEMPERATURE, MAX_TOKENS
        )
        exact_latencies.append((time.monotonic() - t0) * 1000)
    exact_avg = sum(exact_latencies) / len(exact_latencies)
    exact_p50 = sorted(exact_latencies)[len(exact_latencies) // 2]

    # ── Semantic cache latency ────────────────────────────────────────────
    # Use a slightly different query to force semantic lookup
    semantic_latencies: List[float] = []
    similar_query = "RAG是什么？"
    for _ in range(50):
        t0 = time.monotonic()
        await cache.get_semantic(
            similar_query, MODEL, TEMPERATURE, MAX_TOKENS
        )
        semantic_latencies.append((time.monotonic() - t0) * 1000)
    semantic_avg = sum(semantic_latencies) / len(semantic_latencies)
    semantic_p50 = sorted(semantic_latencies)[len(semantic_latencies) // 2]

    # ── LLM estimate ──────────────────────────────────────────────────────
    llm_estimate_ms = 300.0  # Typical DeepSeek latency

    print(f"   Exact cache:    {exact_avg:.2f}ms (p50: {exact_p50:.2f}ms)")
    print(f"   Semantic cache: {semantic_avg:.2f}ms (p50: {semantic_p50:.2f}ms)")
    print(f"   LLM call:       {llm_estimate_ms:.2f}ms (estimated)")
    print()
    if exact_avg > 0:
        speedup_sem = llm_estimate_ms / semantic_avg if semantic_avg > 0 else 0
        speedup_exact = llm_estimate_ms / exact_avg if exact_avg > 0 else 0
        print(f"   Speedup vs LLM: exact {speedup_exact:.0f}x, semantic {speedup_sem:.0f}x")

    await cache.close()

    return BenchmarkResult(
        name="latency",
        data={
            "exact_avg_ms": exact_avg,
            "exact_p50_ms": exact_p50,
            "semantic_avg_ms": semantic_avg,
            "semantic_p50_ms": semantic_p50,
            "llm_estimate_ms": llm_estimate_ms,
            "speedup_exact": (
                llm_estimate_ms / exact_avg if exact_avg > 0 else 0
            ),
            "speedup_semantic": (
                llm_estimate_ms / semantic_avg if semantic_avg > 0 else 0
            ),
        },
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def benchmark_memory() -> BenchmarkResult:
    """Track memory usage of in-memory cache structures."""
    from app.cache.semantic_cache import SemanticLLMCache

    start = time.monotonic()
    cache = SemanticLLMCache(
        similarity_threshold=0.92,
        default_ttl=TTL,
        max_cache_size=10000,
    )

    _print_section("4. Memory usage...")

    # Baseline
    stats_before = await cache.get_stats()
    entries_before = stats_before.get("in_memory_exact_size", 0)
    semantic_before = stats_before.get("in_memory_semantic_size", 0)

    # Seed entries
    for i, (query, response) in enumerate(WARMUP_QUERIES):
        await cache.set(
            query=query,
            response=response,
            model=MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

    stats_after = await cache.get_stats()
    entries_exact = stats_after.get("in_memory_exact_size", 0)
    entries_semantic = stats_after.get("in_memory_semantic_size", 0)

    # Rough memory estimation:
    # Exact cache: each entry stores query key (~64 bytes) + response string (~500 bytes) + overhead
    # Semantic cache: each entry stores embedding (1024 * 8 bytes) + response + overhead
    exact_bytes = entries_exact * 600  # ~600 bytes per exact entry
    semantic_bytes = entries_semantic * (1024 * 8 + 600)  # embedding + response
    total_bytes = exact_bytes + semantic_bytes
    total_mb = total_bytes / (1024 * 1024)

    print(f"   Cache entries:  {entries_exact} exact, {entries_semantic} semantic")
    print(f"   Exact cache:    ~{exact_bytes / 1024:.2f} KB ({entries_exact} entries)")
    print(f"   Semantic cache: ~{semantic_bytes / 1024:.2f} KB ({entries_semantic} entries)")
    print(f"   Total estimate: ~{total_mb:.3f} MB")

    # Show per-entry cost
    if entries_exact > 0:
        per_entry_exact = exact_bytes / entries_exact
        print(f"   Per exact entry:    ~{per_entry_exact:.0f} bytes")
    if entries_semantic > 0:
        per_entry_sem = semantic_bytes / entries_semantic
        print(f"   Per semantic entry: ~{per_entry_sem:.0f} bytes")

    await cache.close()

    return BenchmarkResult(
        name="memory",
        data={
            "entries_exact": entries_exact,
            "entries_semantic": entries_semantic,
            "exact_bytes_est": exact_bytes,
            "semantic_bytes_est": semantic_bytes,
            "total_bytes_est": total_bytes,
            "total_mb_est": total_mb,
        },
        duration_ms=(time.monotonic() - start) * 1000,
    )


async def benchmark_threshold_sensitivity() -> BenchmarkResult:
    """Test how different similarity thresholds affect hit rate.

    Lower thresholds allow more semantic matches (more hits, lower precision).
    Higher thresholds require closer matches (fewer hits, higher precision).
    """
    from app.cache.semantic_cache import SemanticLLMCache

    start = time.monotonic()
    _print_section("5. Threshold sensitivity analysis...")

    thresholds = [0.85, 0.90, 0.92, 0.95]
    # Pairs to test: (query_to_cache, query_to_match)
    threshold_test_pairs = [
        ("什么是RAG？", "RAG是什么？"),
        ("如何优化检索性能？", "检索性能优化方法"),
        ("BM25算法原理", "BM25的工作原理"),
        ("向量数据库的使用", "向量数据库应用"),
        ("什么是Transformer？", "Transformer架构介绍"),
    ]

    results_by_threshold: Dict[float, Dict] = {}

    for threshold in thresholds:
        cache = SemanticLLMCache(
            similarity_threshold=threshold,
            default_ttl=TTL,
            max_cache_size=10000,
        )

        # Seed cache
        for query, response in threshold_test_pairs:
            await cache.set(
                query=query,
                response=f"Response for: {query}",
                model=MODEL,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )

        # Test matches with the second query in each pair
        hits = 0
        similarities: List[float] = []
        for query_a, query_b in threshold_test_pairs:
            # query_b should match query_a if below threshold
            sem = await cache.get_semantic(
                query_b, MODEL, TEMPERATURE, MAX_TOKENS
            )
            if sem is not None:
                _response, score = sem
                hits += 1
                similarities.append(score)

        hit_rate = hits / len(threshold_test_pairs) * 100
        avg_sim = sum(similarities) / len(similarities) if similarities else 0.0

        results_by_threshold[threshold] = {
            "hit_rate": hit_rate,
            "hits": hits,
            "total": len(threshold_test_pairs),
            "avg_similarity": avg_sim,
        }

        print(
            f"   Threshold {threshold:.2f}: "
            f"{hits}/{len(threshold_test_pairs)} hits "
            f"({hit_rate:.0f}%), avg similarity: {avg_sim:.4f}"
        )

        await cache.close()

    # Recommendation
    print()
    best_threshold = max(
        results_by_threshold.items(),
        key=lambda x: x[1]["hit_rate"],
    )
    print(
        f"   Best threshold: {best_threshold[0]:.2f} "
        f"({best_threshold[1]['hit_rate']:.0f}% hit rate)"
    )

    return BenchmarkResult(
        name="threshold_sensitivity",
        data={
            "thresholds": {
                str(k): v for k, v in results_by_threshold.items()
            },
            "best_threshold": best_threshold[0],
            "best_hit_rate": best_threshold[1]["hit_rate"],
        },
        duration_ms=(time.monotonic() - start) * 1000,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

async def run_benchmarks() -> List[BenchmarkResult]:
    """Run all benchmarks sequentially and return structured results."""
    _print_header()

    # Redis availability check
    redis_ok = _check_redis()
    if redis_ok:
        print("\n   Redis: Connected")
    else:
        print("\n   Redis: Unavailable (using in-memory fallback)")

    print()

    results: List[BenchmarkResult] = []

    results.append(await benchmark_cache_hit_rate())
    results.append(await benchmark_latency())
    results.append(await benchmark_memory())
    results.append(await benchmark_threshold_sensitivity())

    # Summary
    _print_section("Summary")
    total_ms = sum(r.duration_ms for r in results)
    print(f"   Total benchmark time: {total_ms:.1f}ms")
    print(f"   Tests completed: {len(results)}")

    for r in results:
        if r.name == "cache_hit_rate":
            print(f"   Hit rate: {r.data.get('hit_rate', 0):.1f}%")
        elif r.name == "latency":
            print(
                f"   Exact vs Semantic: "
                f"{r.data.get('exact_avg_ms', 0):.2f}ms vs "
                f"{r.data.get('semantic_avg_ms', 0):.2f}ms"
            )
        elif r.name == "threshold_sensitivity":
            print(
                f"   Recommended threshold: "
                f"{r.data.get('best_threshold', 0.92):.2f}"
            )

    print()
    print("=" * 64)
    print("Benchmark complete!")
    print("=" * 64)

    return results


def main():
    """Entry point for running benchmarks as a script."""
    results = asyncio.run(run_benchmarks())
    return results


if __name__ == "__main__":
    main()
