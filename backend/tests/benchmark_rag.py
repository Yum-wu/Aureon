"""Enterprise-grade RAG Performance Benchmark.

Metrics based on industry standards:
- RAGAS, BEIR, MTEB evaluation frameworks
- Enterprise targets: Recall@5 > 85%, Latency < 3s, QPS > 5

Run: cd backend && python -m tests.benchmark_rag
"""

import time
import os
import sys
import statistics
import concurrent.futures
import tracemalloc
from typing import List, Dict, Any

# Ensure we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Test Data ──
# Ground truth: query → expected keywords that should appear in retrieved documents
TEST_CASES = [
    {
        "query": "What is RAG retrieval augmented generation",
        "expected": ["RAG", "Retrieval-Augmented Generation"],
        "category": "core_concept",
    },
    {
        "query": "ChromaDB vector storage database",
        "expected": ["chroma", "vector"],
        "category": "tech_stack",
    },
    {
        "query": "Embedding model comparison",
        "expected": ["embedding", "model"],
        "category": "embedding",
    },
    {
        "query": "LangChain agent framework",
        "expected": ["LangChain", "agent"],
        "category": "framework",
    },
    {
        "query": "FastAPI backend Python",
        "expected": ["FastAPI", "Python"],
        "category": "deployment",
    },
    {
        "query": "Redis caching",
        "expected": ["Redis", "cache"],
        "category": "caching",
    },
    {
        "query": "Docker container deployment",
        "expected": ["Docker", "container"],
        "category": "devops",
    },
    {
        "query": "React hooks performance",
        "expected": ["React", "hooks"],
        "category": "frontend",
    },
    {
        "query": "Tailwind CSS responsive",
        "expected": ["Tailwind", "CSS"],
        "category": "frontend",
    },
    {
        "query": "LlamaIndex RAG framework",
        "expected": ["LlamaIndex", "RAG"],
        "category": "framework",
    },
]

TOP_K_VALUES = [3, 5, 10]


def measure_time(fn, *args, **kwargs):
    """Measure execution time of a function."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    return result, elapsed


def check_recall(retrieved: List[Dict], expected_keywords: List[str], k: int) -> bool:
    """Check if any of the top-K results contain expected keywords in text or metadata."""
    top_k = retrieved[:k]
    for doc in top_k:
        text = doc.get("text", "").lower()
        meta = doc.get("metadata", {})
        title = meta.get("title", "").lower()
        source = meta.get("source", "").lower()
        combined = text + " " + title + " " + source
        if any(kw.lower() in combined for kw in expected_keywords):
            return True
    return False


def run_benchmark():
    """Run complete enterprise RAG benchmark."""
    print("=" * 70)
    print("  AUREON RAG — Enterprise Performance Benchmark")
    print("=" * 70)

    # ── Phase 1: Import & Initialize ──
    print("\n> Phase 1: Initialization")
    tracemalloc.start()

    from app.rag.vector_store import (
        retrieve, retrieve_keyword, embed_texts_llm,
        get_collection_stats, get_bm25_stats, _build_kw_index
    )

    t0 = time.perf_counter()
    _build_kw_index(force=True)
    init_time = time.perf_counter() - t0

    doc_count, chunk_count = get_collection_stats()
    bm25 = get_bm25_stats()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"  Documents indexed:    {doc_count}")
    print(f"  Chunks:               {chunk_count}")
    print(f"  BM25 terms:           {bm25['terms']}")
    print(f"  BM25 warmup:          {init_time*1000:.0f}ms")
    print(f"  Memory (current):     {current / 1024 / 1024:.1f} MB")
    print(f"  Memory (peak):        {peak / 1024 / 1024:.1f} MB")

    # ── Phase 2: Embedding Latency ──
    print("\n> Phase 2: Embedding Latency (DashScope API)")
    sample_texts = ["What is retrieval augmented generation"] * 5
    embed_times = []
    for _ in range(3):
        _, t = measure_time(embed_texts_llm, sample_texts)
        embed_times.append(t)
    avg_embed = statistics.mean(embed_times) * 1000
    per_text = avg_embed / 5
    print(f"  Batch of 5 texts:     {avg_embed:.0f}ms (avg of 3 runs)")
    print(f"  Per text:             {per_text:.0f}ms")

    # ── Phase 3: Retrieval Latency ──
    print("\n> Phase 3: Retrieval Latency")
    retrieval_results = {"vector": [], "bm25": [], "hybrid": []}

    for tc in TEST_CASES:
        _, t = measure_time(retrieve, tc["query"], top_k=5)
        retrieval_results["vector"].append(t)

        _, t = measure_time(retrieve_keyword, tc["query"], top_k=5)
        retrieval_results["bm25"].append(t)

    print(f"  Vector search:        {statistics.mean(retrieval_results['vector'])*1000:.1f}ms avg, "
          f"{statistics.stdev(retrieval_results['vector'])*1000:.1f}ms std")
    print(f"  BM25 keyword search:  {statistics.mean(retrieval_results['bm25'])*1000:.1f}ms avg, "
          f"{statistics.stdev(retrieval_results['bm25'])*1000:.1f}ms std")

    # ── Phase 4: Retrieval Quality (Recall@K) ──
    print("\n> Phase 4: Retrieval Quality (Recall@K)")
    for k in TOP_K_VALUES:
        vector_hits = sum(
            1 for tc in TEST_CASES
            if check_recall(retrieve(tc["query"], top_k=k), tc["expected"], k)
        )
        bm25_hits = sum(
            1 for tc in TEST_CASES
            if check_recall(retrieve_keyword(tc["query"], top_k=k), tc["expected"], k)
        )
        vector_recall = vector_hits / len(TEST_CASES) * 100
        bm25_recall = bm25_hits / len(TEST_CASES) * 100
        target = "OK" if vector_recall >= 85 else "WARN"
        print(f"  Recall@{k} Vector:     {vector_recall:.0f}% {target}  "
              f"| BM25: {bm25_recall:.0f}%")

    # ── Phase 5: MRR (Mean Reciprocal Rank) ──
    print("\n> Phase 5: MRR (Mean Reciprocal Rank)")
    mrr_scores = []
    for tc in TEST_CASES:
        results = retrieve(tc["query"], top_k=10)
        for i, doc in enumerate(results):
            text = doc.get("text", "").lower()
            meta = doc.get("metadata", {})
            combined = text + " " + meta.get("title", "").lower() + " " + meta.get("source", "").lower()
            if any(kw.lower() in combined for kw in tc["expected"]):
                mrr_scores.append(1.0 / (i + 1))
                break
        else:
            mrr_scores.append(0.0)
    mrr = statistics.mean(mrr_scores)
    target = "OK" if mrr >= 0.7 else "WARN"
    print(f"  MRR:                  {mrr:.3f} {target}  (target: ≥0.700)")

    # ── Phase 6: Cache Performance ──
    print("\n> Phase 6: Cache Performance")
    unique_query = f"Enterprise RAG performance benchmark test {int(time.time())}"

    # Cold query (API call - unique, not cached)
    _, t_cold = measure_time(embed_texts_llm, [unique_query])

    # Warm query (same text, should hit cache)
    times_warm = []
    for _ in range(5):
        _, t = measure_time(embed_texts_llm, [unique_query])
        times_warm.append(t)
    avg_warm = statistics.mean(times_warm)

    speedup = t_cold / avg_warm if avg_warm > 0 else 0
    print(f"  Cold (API call):      {t_cold*1000:.0f}ms")
    print(f"  Warm (cache hit):     {avg_warm*1000:.1f}ms")
    print(f"  Speedup:              {speedup:.0f}x")

    # ── Phase 7: Throughput (Concurrent Queries) ──
    print("\n> Phase 7: Throughput (Concurrent Queries)")
    concurrency_levels = [1, 3, 5]
    for conc in concurrency_levels:
        query_list = [TEST_CASES[i % len(TEST_CASES)]["query"] for i in range(conc)]
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as pool:
            futures = [pool.submit(retrieve, q, top_k=3) for q in query_list]
            concurrent.futures.wait(futures)
        elapsed = time.perf_counter() - t0
        qps = conc / elapsed
        print(f"  {conc} concurrent:      {elapsed*1000:.0f}ms total, {qps:.1f} QPS")

    # ── Phase 8: End-to-End Latency Distribution ──
    print("\n> Phase 8: End-to-End Retrieval Latency Distribution")
    all_times = []
    for _ in range(10):
        for tc in TEST_CASES[:3]:
            _, t = measure_time(retrieve, tc["query"], top_k=5)
            all_times.append(t * 1000)
    all_times.sort()
    print(f"  Samples:              {len(all_times)}")
    print(f"  P50:                  {all_times[len(all_times)//2]:.0f}ms")
    print(f"  P90:                  {all_times[int(len(all_times)*0.9)]:.0f}ms")
    print(f"  P99:                  {all_times[int(len(all_times)*0.99)]:.0f}ms")
    print(f"  Min:                  {min(all_times):.0f}ms")
    print(f"  Max:                  {max(all_times):.0f}ms")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Metric':<30} {'Value':<15} {'Target':<15} {'Status'}")
    print(f"  {'-'*30} {'-'*15} {'-'*15} {'-'*10}")
    print(f"  {'Documents':<30} {doc_count:<15} {'>0':<15} {'OK'}")
    print(f"  {'Chunks':<30} {chunk_count:<15} {'>0':<15} {'OK'}")
    print(f"  {'Embedding Latency/text':<30} {per_text:.0f}ms{'':<10} {'<500ms':<15} {'OK' if per_text < 500 else 'WARN'}")
    print(f"  {'Vector Search Latency':<30} {statistics.mean(retrieval_results['vector'])*1000:.0f}ms{'':<10} {'<100ms':<15} {'OK' if statistics.mean(retrieval_results['vector']) < 0.1 else 'WARN'}")
    print(f"  {'BM25 Search Latency':<30} {statistics.mean(retrieval_results['bm25'])*1000:.1f}ms{'':<9} {'<10ms':<15} {'OK' if statistics.mean(retrieval_results['bm25']) < 0.01 else 'WARN'}")
    print(f"  {'Recall@5 (Vector)':<30} {vector_recall:.0f}%{'':<12} {'≥85%':<15} {'OK' if vector_recall >= 85 else 'WARN'}")
    print(f"  {'MRR':<30} {mrr:.3f}{'':<12} {'≥0.700':<15} {'OK' if mrr >= 0.7 else 'WARN'}")
    print(f"  {'Cache Speedup':<30} {speedup:.0f}x{'':<13} {'>5x':<15} {'OK' if speedup > 5 else 'WARN'}")
    print(f"  {'P50 Latency':<30} {all_times[len(all_times)//2]:.0f}ms{'':<10} {'<500ms':<15} {'OK' if all_times[len(all_times)//2] < 500 else 'WARN'}")
    print(f"  {'P99 Latency':<30} {all_times[int(len(all_times)*0.99)]:.0f}ms{'':<10} {'<1000ms':<14} {'OK' if all_times[int(len(all_times)*0.99)] < 1000 else 'WARN'}")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
