# -*- coding: utf-8 -*-
"""Concurrent RAG Benchmark - asyncio-based parallel evaluation.

Measures throughput, latency distribution, and quality under concurrent load.
Supports configurable concurrency levels and document scale testing.

Run: cd backend && python -m tests.benchmark_concurrent
"""
import asyncio
import time
import statistics
import json
from pathlib import Path
from typing import List, Dict, Any
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def evaluate_qa_async(qa: Dict, semaphore: asyncio.Semaphore) -> Dict:
    """Evaluate single QA pair with concurrency control."""
    async with semaphore:
        from app.rag.qa_chain import hybrid_retrieve_async

        query = qa["question"]
        expected_source = qa["source_article"]
        is_negative = expected_source == "none"

        start = time.perf_counter()
        chunks = await hybrid_retrieve_async(query, top_k=3)
        latency_ms = (time.perf_counter() - start) * 1000

        retrieved_sources = [c.get("metadata", {}).get("slug", "") for c in chunks]

        if is_negative:
            hit = len(chunks) == 0
        else:
            hit = expected_source in retrieved_sources

        return {
            "id": qa["id"],
            "query": query[:50],
            "hit": hit,
            "latency_ms": latency_ms,
            "is_negative": is_negative,
            "retrieved": retrieved_sources[:3],
        }


async def run_concurrent_evaluation(
    qa_pairs: List[Dict],
    concurrency: int = 10,
) -> Dict:
    """Run evaluation with specified concurrency level."""
    semaphore = asyncio.Semaphore(concurrency)

    start = time.perf_counter()
    tasks = [evaluate_qa_async(qa, semaphore) for qa in qa_pairs]
    results = await asyncio.gather(*tasks)
    total_time = (time.perf_counter() - start) * 1000

    # Aggregate results
    hits = sum(1 for r in results if r["hit"])
    latencies = [r["latency_ms"] for r in results]
    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    positive_results = [r for r in results if not r["is_negative"]]
    positive_hits = sum(1 for r in positive_results if r["hit"])

    return {
        "concurrency": concurrency,
        "total_queries": len(results),
        "total_time_ms": round(total_time, 1),
        "qps": round(len(results) / (total_time / 1000), 1),
        "recall": round(positive_hits / len(positive_results) * 100, 1) if positive_results else 0,
        "hit_rate": round(hits / len(results) * 100, 1),
        "latency": {
            "mean_ms": round(statistics.mean(latencies), 1),
            "p50_ms": round(sorted_lats[n // 2], 1),
            "p90_ms": round(sorted_lats[int(n * 0.9) - 1], 1),
            "p99_ms": round(sorted_lats[min(int(n * 0.99), n - 1)], 1),
            "min_ms": round(sorted_lats[0], 1),
            "max_ms": round(sorted_lats[-1], 1),
        },
    }


async def run_scale_test():
    """Test performance across different document scales."""
    from app.rag.vector_store import get_collection_stats

    doc_count, chunk_count = get_collection_stats()

    print("\n" + "=" * 70)
    print("  Document Scale Test")
    print("=" * 70)
    print(f"\n  Current: {doc_count} docs, {chunk_count} chunks")

    # Run benchmark at current scale
    from app.rag.test_data import TEST_QA_PAIRS
    result = await run_concurrent_evaluation(TEST_QA_PAIRS, concurrency=10)

    print(f"\n  Results at {doc_count} docs:")
    print(f"    QPS:          {result['qps']}")
    print(f"    Recall:       {result['recall']}%")
    print(f"    P50 latency:  {result['latency']['p50_ms']:.1f}ms")
    print(f"    P99 latency:  {result['latency']['p99_ms']:.1f}ms")

    # Check against thresholds
    thresholds = {
        "recall": 90,
        "p99_latency_ms": 500,
        "min_qps": 5,
    }

    passed = True
    if result["recall"] < thresholds["recall"]:
        print(f"\n  [FAIL] Recall {result['recall']}% < {thresholds['recall']}%")
        passed = False
    if result["latency"]["p99_ms"] > thresholds["p99_latency_ms"]:
        print(f"\n  [FAIL] P99 {result['latency']['p99_ms']}ms > {thresholds['p99_latency_ms']}ms")
        passed = False
    if result["qps"] < thresholds["min_qps"]:
        print(f"\n  [FAIL] QPS {result['qps']} < {thresholds['min_qps']}")
        passed = False

    if passed:
        print(f"\n  [PASS] All thresholds met at {doc_count} docs")

    return passed


async def run_full_concurrent_benchmark():
    """Run complete concurrent benchmark across multiple concurrency levels."""
    from app.rag.test_data import TEST_QA_PAIRS

    print("=" * 70)
    print("  AUREON RAG - Concurrent Benchmark")
    print("=" * 70)

    qa_pairs = TEST_QA_PAIRS
    print(f"\n  QA pairs: {len(qa_pairs)}")

    # Warm up
    print("\n  Warming up index...")
    from app.rag.vector_store import _build_kw_index
    _build_kw_index(force=True)

    concurrency_levels = [1, 5, 10, 20]
    all_results = []

    for conc in concurrency_levels:
        print(f"\n> Concurrency: {conc}")
        result = await run_concurrent_evaluation(qa_pairs, concurrency=conc)
        all_results.append(result)

        print(f"  Total time:   {result['total_time_ms']:.0f}ms")
        print(f"  QPS:          {result['qps']}")
        print(f"  Recall:       {result['recall']}%")
        print(f"  Hit rate:     {result['hit_rate']}%")
        print(f"  Latency P50:  {result['latency']['p50_ms']:.1f}ms")
        print(f"  Latency P99:  {result['latency']['p99_ms']:.1f}ms")

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "qa_pairs": len(qa_pairs),
        "results": all_results,
    }

    out_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_concurrent.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved: {out_path}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    if "--scale" in sys.argv:
        asyncio.run(run_scale_test())
    else:
        asyncio.run(run_full_concurrent_benchmark())
