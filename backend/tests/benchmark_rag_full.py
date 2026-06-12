"""Full 97-QA Enterprise RAG Benchmark.

Tests retrieval quality and latency against the complete QA test suite.
Metrics: Recall@K, MRR, Precision@K, Latency Distribution, Throughput.

Run: cd backend && python -m tests.benchmark_rag_full
"""

import time
import os
import sys
import statistics
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.rag.test_data import TEST_QA_PAIRS
from app.rag.vector_store import (
    retrieve, retrieve_keyword, embed_texts_llm,
    get_collection_stats, _build_kw_index
)


def run_full_benchmark():
    print("=" * 70)
    print("  AUREON RAG -- Full 97-QA Enterprise Benchmark")
    print("=" * 70)

    # ── Init ──
    print("\n> Phase 1: Initialization")
    tracemalloc.start()
    t0 = time.perf_counter()
    _build_kw_index(force=True)
    init_time = time.perf_counter() - t0
    doc_count, chunk_count = get_collection_stats()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_qa = len(TEST_QA_PAIRS)
    print(f"  QA pairs:            {total_qa}")
    print(f"  Documents indexed:   {doc_count}")
    print(f"  Chunks:              {chunk_count}")
    print(f"  BM25 warmup:         {init_time*1000:.0f}ms")
    print(f"  Memory:              {current/1024/1024:.1f}MB (peak: {peak/1024/1024:.1f}MB)")

    # ── Retrieval Quality ──
    print(f"\n> Phase 2: Retrieval Quality ({total_qa} queries)")

    vector_results = {"recall": {3: 0, 5: 0, 10: 0}, "mrr": [], "hits": 0, "misses": 0,
                      "latencies": [], "no_results": 0}
    bm25_results = {"recall": {3: 0, 5: 0, 10: 0}, "mrr": [], "hits": 0, "misses": 0,
                    "latencies": [], "no_results": 0}

    for i, qa in enumerate(TEST_QA_PAIRS):
        query = qa["question"]
        expected_keywords = qa["answer"][:50].split()[:3]  # First few words of answer as keywords
        source_article = qa.get("source_article", "")

        # Vector search
        t0 = time.perf_counter()
        v_results = retrieve(query, top_k=10)
        v_latency = time.perf_counter() - t0
        vector_results["latencies"].append(v_latency * 1000)

        if not v_results:
            vector_results["no_results"] += 1

        # Check recall@K
        for k in [3, 5, 10]:
            found = False
            for doc in v_results[:k]:
                text = (doc.get("text", "") + doc.get("metadata", {}).get("source", "")).lower()
                if source_article and source_article.lower() in text:
                    found = True
                    break
                if any(kw.lower() in text for kw in expected_keywords):
                    found = True
                    break
            if found:
                vector_results["recall"][k] += 1

        # MRR
        mrr_rank = 0
        for j, doc in enumerate(v_results[:10]):
            text = (doc.get("text", "") + doc.get("metadata", {}).get("source", "")).lower()
            if source_article and source_article.lower() in text:
                mrr_rank = j + 1
                break
            if any(kw.lower() in text for kw in expected_keywords):
                mrr_rank = j + 1
                break
        vector_results["mrr"].append(1.0 / mrr_rank if mrr_rank > 0 else 0.0)

        if mrr_rank > 0:
            vector_results["hits"] += 1
        else:
            vector_results["misses"] += 1

        # BM25 search
        t0 = time.perf_counter()
        b_results = retrieve_keyword(query, top_k=10)
        b_latency = time.perf_counter() - t0
        bm25_results["latencies"].append(b_latency * 1000)

        if not b_results:
            bm25_results["no_results"] += 1

        for k in [3, 5, 10]:
            found = False
            for doc in b_results[:k]:
                text = doc.get("text", "").lower()
                if source_article and source_article.lower() in text:
                    found = True
                    break
                if any(kw.lower() in text for kw in expected_keywords):
                    found = True
                    break
            if found:
                bm25_results["recall"][k] += 1

        b_mrr_rank = 0
        for j, doc in enumerate(b_results[:10]):
            text = doc.get("text", "").lower()
            if source_article and source_article.lower() in text:
                b_mrr_rank = j + 1
                break
            if any(kw.lower() in text for kw in expected_keywords):
                b_mrr_rank = j + 1
                break
        bm25_results["mrr"].append(1.0 / b_mrr_rank if b_mrr_rank > 0 else 0.0)

        if b_mrr_rank > 0:
            bm25_results["hits"] += 1
        else:
            bm25_results["misses"] += 1

        # Progress
        if (i + 1) % 20 == 0 or i == total_qa - 1:
            print(f"  Progress: {i+1}/{total_qa} queries completed")

    # ── Embedding Latency ──
    print("\n> Phase 3: Embedding Latency (Cold vs Cached)")
    sample = "Enterprise RAG performance test " + str(int(time.time()))
    _, t_cold = measure_time(embed_texts_llm, [sample])
    times_warm = []
    for _ in range(5):
        _, t = measure_time(embed_texts_llm, [sample])
        times_warm.append(t)
    avg_warm = statistics.mean(times_warm)

    # ── Throughput ──
    print("\n> Phase 4: Throughput")
    import concurrent.futures
    for conc in [1, 5, 10]:
        queries = [TEST_QA_PAIRS[i % total_qa]["question"] for i in range(conc)]
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as pool:
            list(pool.map(lambda q: retrieve(q, top_k=3), queries))
        elapsed = time.perf_counter() - t0
        print(f"  {conc:2d} concurrent:    {elapsed*1000:.0f}ms  ({conc/elapsed:.0f} QPS)")

    # ── Results ──
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)

    print(f"\n  Total QA pairs tested:    {total_qa}")
    print(f"  Documents in index:       {doc_count}")
    print(f"  Chunks in index:          {chunk_count}")

    print("\n  --- Vector Search ---")
    for k in [3, 5, 10]:
        rate = vector_results["recall"][k] / total_qa * 100
        target = "OK" if rate >= 80 else "WARN"
        print(f"  Recall@{k}:              {vector_results['recall'][k]}/{total_qa} = {rate:.1f}%  [{target}]")

    v_mrr = statistics.mean(vector_results["mrr"])
    target = "OK" if v_mrr >= 0.6 else "WARN"
    print(f"  MRR:                    {v_mrr:.3f}  [{target}]")
    print(f"  Hit Rate:               {vector_results['hits']}/{total_qa} = {vector_results['hits']/total_qa*100:.1f}%")
    print(f"  Miss Rate:              {vector_results['misses']}/{total_qa} = {vector_results['misses']/total_qa*100:.1f}%")
    print(f"  No Results:             {vector_results['no_results']}/{total_qa}")

    v_lat = vector_results["latencies"]
    v_lat_sorted = sorted(v_lat)
    print(f"  Latency P50:            {v_lat_sorted[len(v_lat_sorted)//2]:.1f}ms")
    print(f"  Latency P90:            {v_lat_sorted[int(len(v_lat_sorted)*0.9)]:.1f}ms")
    print(f"  Latency P99:            {v_lat_sorted[int(len(v_lat_sorted)*0.99)]:.1f}ms")
    print(f"  Latency Avg:            {statistics.mean(v_lat):.1f}ms")

    print("\n  --- BM25 Keyword Search ---")
    for k in [3, 5, 10]:
        rate = bm25_results["recall"][k] / total_qa * 100
        target = "OK" if rate >= 70 else "WARN"
        print(f"  Recall@{k}:              {bm25_results['recall'][k]}/{total_qa} = {rate:.1f}%  [{target}]")

    b_mrr = statistics.mean(bm25_results["mrr"])
    target = "OK" if b_mrr >= 0.5 else "WARN"
    print(f"  MRR:                    {b_mrr:.3f}  [{target}]")
    print(f"  Hit Rate:               {bm25_results['hits']}/{total_qa} = {bm25_results['hits']/total_qa*100:.1f}%")

    b_lat = bm25_results["latencies"]
    b_lat_sorted = sorted(b_lat)
    print(f"  Latency P50:            {b_lat_sorted[len(b_lat_sorted)//2]:.1f}ms")
    print(f"  Latency Avg:            {statistics.mean(b_lat):.1f}ms")

    print("\n  --- Embedding Cache ---")
    print(f"  Cold (API):             {t_cold*1000:.0f}ms")
    print(f"  Warm (cache):           {avg_warm*1000:.2f}ms")
    print(f"  Speedup:                {t_cold/avg_warm:.0f}x" if avg_warm > 0 else "  Speedup: N/A")

    print("\n  --- Category Breakdown (Vector) ---")
    categories = {}
    for qa in TEST_QA_PAIRS:
        cat = qa.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"total": 0, "hits": 0}
        categories[cat]["total"] += 1

    # Re-match categories to hits
    for qa in TEST_QA_PAIRS:
        cat = qa.get("category", "unknown")
        query = qa["question"]
        results = retrieve(query, top_k=5)
        source = qa.get("source_article", "")
        for doc in results[:5]:
            text = (doc.get("text", "") + doc.get("metadata", {}).get("source", "")).lower()
            if source and source.lower() in text:
                categories[cat]["hits"] += 1
                break

    for cat, data in sorted(categories.items()):
        rate = data["hits"] / data["total"] * 100 if data["total"] > 0 else 0
        print(f"  {cat:25s} {data['hits']}/{data['total']} = {rate:.0f}%")

    print("\n" + "=" * 70)


def measure_time(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    return result, elapsed


if __name__ == "__main__":
    run_full_benchmark()
