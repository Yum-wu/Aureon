"""Aureon RAG Benchmark — Multi-metric evaluation.

Metrics:
  1. Recall@K — does the correct article appear in top-K results?
  2. Precision@K — of top-K results, how many are from the correct article?
  3. MRR — reciprocal rank of the first relevant result
  4. Negative detection — does the system correctly decline unanswerable queries?
  5. Retrieval latency (BM25, Vector, Hybrid)
  6. Per-difficulty breakdown (easy/medium/hard)
  7. Per-type breakdown (factual/reasoning/synthesis/cross_article/negative)

Usage: cd backend && python -m tests.run_benchmark
"""

import sys
import os
import time
import statistics
import json
import math
import argparse
import asyncio
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_qa_pairs():
    """Load all QA pairs from single source of truth."""
    from app.rag.test_data import TEST_QA_PAIRS
    return TEST_QA_PAIRS


def test_recall(retrieve_fn, qa_pairs, k=3):
    """Evaluate Recall@K, Precision@K, Recall@10, and nDCG@10.

    For negative queries (source_article='none'), recall is not applicable.
    Instead we check that the system returns few/no results.
    """
    positive_hits = 0
    positive_total = 0
    positive_misses = []

    negative_correct = 0
    negative_total = 0
    negative_wrong = []

    precisions = []
    rranks = []

    recall_10_hits = 0
    ndcg_scores = []

    for qa in qa_pairs:
        q = qa["question"]
        expected_source = qa["source_article"]
        is_negative = expected_source == "none"

        chunks = retrieve_fn(q, top_k=k)
        retrieved_sources = [c.get("metadata", {}).get("slug", "") for c in chunks]

        if is_negative:
            negative_total += 1
            # For negative queries, success = few results or results from unrelated articles
            if len(chunks) == 0:
                negative_correct += 1
            else:
                negative_wrong.append({
                    "id": qa["id"],
                    "question": q[:60],
                    "retrieved_count": len(chunks),
                    "retrieved_sources": retrieved_sources[:3],
                })
        else:
            positive_total += 1
            hit = expected_source in retrieved_sources
            if hit:
                positive_hits += 1
            else:
                positive_misses.append({
                    "id": qa["id"],
                    "question": q[:60],
                    "expected": expected_source,
                    "retrieved": retrieved_sources[:5],
                })

            # Precision@K (binary): does top-K contain the correct article?
            # Industry standard: 1 if expected source in results, 0 otherwise.
            # Previous chunk-level metric was misleading (BM25 returns multiple
            # chunks from the same article, inflating "correct_count / k").
            precisions.append(1.0 if expected_source in retrieved_sources else 0.0)

            # MRR: reciprocal rank of first correct result
            rr = 0
            for rank, s in enumerate(retrieved_sources, 1):
                if s == expected_source:
                    rr = 1.0 / rank
                    break
            rranks.append(rr)

            # Recall@10 and nDCG@10: fetch top-10 results
            chunks_10 = retrieve_fn(q, top_k=10)
            retrieved_sources_10 = [c.get("metadata", {}).get("slug", "") for c in chunks_10]
            if expected_source in retrieved_sources_10:
                recall_10_hits += 1
            # nDCG@10: binary relevance (1.0 if source matches)
            dcg = 0.0
            for i, source in enumerate(retrieved_sources_10[:10]):
                rel = 1.0 if source == expected_source else 0.0
                dcg += rel / math.log2(i + 2)
            ndcg_scores.append(dcg)  # idcg = 1.0 for single relevant doc

    recall = positive_hits / positive_total if positive_total > 0 else 0
    recall_10 = recall_10_hits / positive_total if positive_total > 0 else 0
    precision = statistics.mean(precisions) if precisions else 0
    mrr = statistics.mean(rranks) if rranks else 0
    ndcg_10 = statistics.mean(ndcg_scores) if ndcg_scores else 0
    neg_rate = negative_correct / negative_total if negative_total > 0 else 0

    return {
        "recall": recall,
        "recall_hits": positive_hits,
        "recall_total": positive_total,
        "recall_10": recall_10,
        "recall_10_hits": recall_10_hits,
        "ndcg_10": ndcg_10,
        "precision": precision,
        "mrr": mrr,
        "negative_detection_rate": neg_rate,
        "negative_correct": negative_correct,
        "negative_total": negative_total,
        "misses": positive_misses,
        "negative_wrong": negative_wrong,
    }


def test_pipeline_negative_detection(qa_pairs):
    """Test negative detection through the full RAG pipeline (with CRAG).

    Uses the real LLM to test whether CRAG correctly filters irrelevant retrievals.
    Returns negative detection rate and list of failures.
    """
    from app.rag.qa_chain import rag_query
    from app.agent.llm import create_llm

    negative_pairs = [qa for qa in qa_pairs if qa["source_article"] == "none"]
    if not negative_pairs:
        return {"negative_detection_rate": 1.0, "negative_correct": 0, "negative_total": 0, "negative_wrong": []}

    # Use real LLM for CRAG assessment
    llm = create_llm(streaming=False)

    def _llm_call(messages):
        try:
            return llm.invoke(messages).content
        except Exception:
            return "3"  # fail-open

    correct = 0
    total = 0
    failures = []

    for qa in negative_pairs:
        total += 1
        try:
            result = rag_query(qa["question"], _llm_call, top_k=3)
            if not result.sources:
                correct += 1
            else:
                failures.append({
                    "id": qa["id"],
                    "question": qa["question"][:60],
                    "sources_count": len(result.sources),
                    "sources": [s.slug for s in result.sources[:3]],
                })
        except Exception as e:
            correct += 1
            print(f"    [{qa['id']}] error (counted as correct): {e}")

    return {
        "negative_detection_rate": correct / total if total > 0 else 0,
        "negative_correct": correct,
        "negative_total": total,
        "negative_wrong": failures,
    }


def test_by_category(retrieve_fn, qa_pairs, k=3):
    """Evaluate recall broken down by difficulty and type."""
    results = {}

    # By difficulty
    by_diff = defaultdict(list)
    for qa in qa_pairs:
        by_diff[qa.get("difficulty", "unknown")].append(qa)

    for diff, pairs in sorted(by_diff.items()):
        r = test_recall(retrieve_fn, pairs, k=k)
        results[f"difficulty_{diff}"] = {
            "recall": r["recall"],
            "precision": r["precision"],
            "mrr": r["mrr"],
            "count": len(pairs),
        }

    # By type
    by_type = defaultdict(list)
    for qa in qa_pairs:
        by_type[qa.get("type", "unknown")].append(qa)

    for typ, pairs in sorted(by_type.items()):
        r = test_recall(retrieve_fn, pairs, k=k)
        results[f"type_{typ}"] = {
            "recall": r["recall"],
            "precision": r["precision"],
            "mrr": r["mrr"],
            "count": len(pairs),
        }

    return results


def measure_latency(fn, qa_pairs, num_runs=3):
    """Measure function latency over multiple runs."""
    all_latencies = []
    for qa in qa_pairs:
        for _ in range(num_runs):
            start = time.perf_counter()
            fn(qa["question"])
            elapsed_ms = (time.perf_counter() - start) * 1000
            all_latencies.append(elapsed_ms)

    sorted_lats = sorted(all_latencies)
    n = len(sorted_lats)
    return {
        "mean_ms": round(statistics.mean(sorted_lats), 1),
        "p50_ms": round(sorted_lats[n // 2], 1),
        "p99_ms": round(sorted_lats[min(int(n * 0.99), n - 1)], 1),
        "min_ms": round(sorted_lats[0], 1),
        "max_ms": round(sorted_lats[-1], 1),
        "num_samples": n,
    }


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Aureon RAG Benchmark")
    parser.add_argument(
        "--mode",
        choices=["local", "railway"],
        default=os.getenv("BENCHMARK_MODE", "local"),
        help="Benchmark mode",
    )
    parser.add_argument("--compare", help="Compare with previous run (JSON file)")
    parser.add_argument("--full", action="store_true", help="Run all concurrency levels")
    parser.add_argument("--output-dir", default="data", help="Output directory")
    parser.add_argument("--skip-concurrency", action="store_true", help="Skip concurrency tests")
    return parser.parse_args()


async def run_railway_benchmark(args):
    """Run full benchmark in Railway mode via HTTP API.

    Tests: quality (Recall@K, MRR, nDCG), latency distribution, cost, concurrency.
    """
    from app.benchmark import (
        detect_environment,
        RailwayBenchmarkClient,
        ConcurrencyTestSuite,
        CostTracker,
    )
    from app.benchmark.report_generator import (
        generate_terminal_output,
        generate_markdown_report,
        save_json_report,
    )

    env = detect_environment()
    print(f"\n> Environment: {env.mode.upper()}")
    print(f"  URL: {env.base_url}")
    print(f"  Vector: {env.vector_backend}")

    # Create client
    client = RailwayBenchmarkClient(
        base_url=env.base_url,
        api_key=env.api_key,
    )

    # Health check
    print("\n> Checking API health...")
    if not await client.health_check():
        print("  API health check failed!")
        return
    print("  API is healthy")

    # Load test queries
    from app.rag.test_data import TEST_QA_PAIRS
    queries = [qa["question"] for qa in TEST_QA_PAIRS]

    # ── Phase 1: Quality Evaluation via HTTP API ──
    print(f"\n> Phase 1: Quality Evaluation ({len(TEST_QA_PAIRS)} QA pairs via API)")

    positive_hits = {3: 0, 5: 0, 10: 0}
    positive_total = 0
    negative_correct = 0
    negative_total = 0
    mrr_scores = []
    ndcg_scores = []
    latencies = []
    positive_misses = []
    negative_wrong = []
    cost_tracker = CostTracker()

    for i, qa in enumerate(TEST_QA_PAIRS):
        query = qa["question"]
        expected_keywords = qa["answer"][:50].split()[:3]
        source_article = qa.get("source_article", "")
        is_negative = source_article == "none" or qa.get("type") == "negative"

        try:
            # Call API with top_k=10 for comprehensive quality metrics
            start = time.perf_counter()
            resp = await client._client.post(
                f"{client.base_url}/api/rag/query",
                json={"query": query, "top_k": 10},
                headers=client.headers,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "")
                sources = data.get("sources", [])

                # Estimate cost: rough token count from text length
                query_tokens = len(query) // 2  # ~2 chars per token for CJK
                answer_tokens = len(answer) // 2
                source_tokens = sum(len(s.get("chunk", "")) // 2 for s in sources)
                total_tokens = query_tokens + answer_tokens + source_tokens
                cost_tracker.record_tokens(
                    input_tokens=query_tokens + source_tokens,
                    output_tokens=answer_tokens,
                    model="qwen3.6-flash",
                )

                # Check retrieval quality
                source_texts = []
                for s in sources:
                    combined = (s.get("title", "") + " " + s.get("slug", "") + " " +
                                s.get("chunk_text_snippet", s.get("chunk", ""))).lower()
                    source_texts.append(combined)

                def _check_hit(k):
                    for doc_text in source_texts[:k]:
                        if source_article and source_article != "none" and source_article.lower() in doc_text:
                            return True
                        if any(kw.lower() in doc_text for kw in expected_keywords):
                            return True
                    return False

                if is_negative:
                    negative_total += 1
                    # Negative: correct if API returns no sources or no keyword matches
                    has_keyword_match = any(
                        any(kw.lower() in t for kw in expected_keywords)
                        for t in source_texts
                    )
                    if not sources or not has_keyword_match:
                        negative_correct += 1
                    else:
                        negative_wrong.append({
                            "id": qa["id"],
                            "question": query[:60],
                            "sources_count": len(sources),
                            "sources": [s.get("slug", "") for s in sources[:3]],
                        })
                else:
                    positive_total += 1
                    for k in [3, 5, 10]:
                        if _check_hit(k):
                            positive_hits[k] += 1
                    if not _check_hit(3):
                        positive_misses.append({
                            "id": qa["id"],
                            "question": query[:60],
                            "expected": source_article,
                            "retrieved": [s.get("slug", "") for s in sources[:3]],
                        })

                    # MRR
                    mrr_rank = 0
                    for j, doc_text in enumerate(source_texts[:10]):
                        if source_article and source_article.lower() in doc_text:
                            mrr_rank = j + 1
                            break
                        if any(kw.lower() in doc_text for kw in expected_keywords):
                            mrr_rank = j + 1
                            break
                    mrr_scores.append(1.0 / mrr_rank if mrr_rank > 0 else 0.0)

                    # nDCG@10 — count relevant docs for correct IDCG
                    def _is_relevant(doc_text):
                        if source_article and source_article != "none" and source_article.lower() in doc_text:
                            return True
                        return any(kw.lower() in doc_text for kw in expected_keywords)

                    relevant_count = sum(1 for d in source_texts[:10] if _is_relevant(d))
                    dcg = 0.0
                    for idx, doc_text in enumerate(source_texts[:10]):
                        if _is_relevant(doc_text):
                            dcg += 1.0 / math.log2(idx + 2)
                    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(relevant_count, 10)))
                    ndcg_scores.append(dcg / idcg if idcg > 0 else 0.0)
            else:
                print(f"    [{i+1}] HTTP {resp.status_code}: {query[:40]}...")

        except Exception as e:
            print(f"    [{i+1}] Error: {e}")
            if is_negative:
                negative_total += 1
            else:
                positive_total += 1
                mrr_scores.append(0.0)
                ndcg_scores.append(0.0)

        # Progress
        if (i + 1) % 20 == 0 or i == len(TEST_QA_PAIRS) - 1:
            print(f"  Progress: {i+1}/{len(TEST_QA_PAIRS)}")

    # Quality results
    recall_3 = positive_hits[3] / positive_total if positive_total > 0 else 0
    recall_5 = positive_hits[5] / positive_total if positive_total > 0 else 0
    recall_10 = positive_hits[10] / positive_total if positive_total > 0 else 0
    mrr = statistics.mean(mrr_scores) if mrr_scores else 0
    ndcg_10 = statistics.mean(ndcg_scores) if ndcg_scores else 0
    neg_rate = negative_correct / negative_total if negative_total > 0 else 0

    quality_results = {
        "recall_3": recall_3,
        "recall_5": recall_5,
        "recall_10": recall_10,
        "recall_at_3": recall_3,
        "recall_at_5": recall_5,
        "recall_at_10": recall_10,
        "recall_hits_3": positive_hits[3],
        "recall_hits_5": positive_hits[5],
        "recall_hits_10": positive_hits[10],
        "recall_total": positive_total,
        "precision_3": recall_3,
        "mrr": mrr,
        "ndcg_10": ndcg_10,
        "ndcg_at_10": ndcg_10,
        "negative_detection_rate": neg_rate,
        "negative_correct": negative_correct,
        "negative_total": negative_total,
    }

    print(f"\n  Hybrid Retrieval:")
    print(f"    Recall@3:     {recall_3*100:.1f}% ({positive_hits[3]}/{positive_total})")
    print(f"    Recall@5:     {recall_5*100:.1f}% ({positive_hits[5]}/{positive_total})")
    print(f"    Recall@10:    {recall_10*100:.1f}% ({positive_hits[10]}/{positive_total})")
    print(f"    Precision@3:  {recall_3*100:.1f}%")
    print(f"    MRR:          {mrr:.3f}")
    print(f"    nDCG@10:      {ndcg_10:.3f}")
    print(f"    Neg Detection: {neg_rate*100:.1f}% ({negative_correct}/{negative_total})")

    if positive_misses:
        print(f"\n  Top misses:")
        for m in positive_misses[:5]:
            print(f"    [{m['id']}] {m['question']}")
            print(f"      expected: {m['expected']}, got: {m['retrieved']}")

    if negative_wrong:
        print(f"\n  Negative detection failures:")
        for m in negative_wrong[:5]:
            print(f"    [{m['id']}] {m['question']}")
            print(f"      returned {m['sources_count']} sources: {m['sources']}")

    # ── Phase 2: Latency Distribution ──
    lat_sorted = sorted(latencies)
    n = len(lat_sorted)
    if n > 0:
        latency_results = {
            "mean_ms": round(statistics.mean(lat_sorted), 1),
            "p50_ms": round(lat_sorted[n // 2], 1),
            "p90_ms": round(lat_sorted[int(n * 0.9)], 1),
            "p99_ms": round(lat_sorted[min(int(n * 0.99), n - 1)], 1),
            "min_ms": round(lat_sorted[0], 1),
            "max_ms": round(lat_sorted[-1], 1),
            "num_samples": n,
        }
        print(f"\n> Phase 2: Latency Distribution (from quality evaluation)")
        print(f"  Samples:  {n}")
        print(f"  Mean:     {latency_results['mean_ms']}ms")
        print(f"  P50:      {latency_results['p50_ms']}ms")
        print(f"  P90:      {latency_results['p90_ms']}ms")
        print(f"  P99:      {latency_results['p99_ms']}ms")
        print(f"  Min:      {latency_results['min_ms']}ms")
        print(f"  Max:      {latency_results['max_ms']}ms")
    else:
        latency_results = {}

    # ── Phase 3: Concurrency Tests ──
    concurrency_results = []
    if args.skip_concurrency:
        print("\n> Phase 3: Concurrency tests SKIPPED (--skip-concurrency)")
        # Load existing concurrency data if available
        import glob as _glob
        existing = sorted(_glob.glob(str(Path(args.output_dir) / "benchmark_railway_*.json")))
        if existing:
            with open(existing[-1], encoding="utf-8") as f:
                prev = json.load(f)
            concurrency_results = prev.get("concurrency", [])
            if concurrency_results:
                print(f"  Loaded {len(concurrency_results)} levels from {Path(existing[-1]).name}")
    else:
        print("\n> Phase 3: Concurrency tests...")
        suite = ConcurrencyTestSuite()
        levels = [1, 10, 25, 50, 75, 100] if args.full else [10, 50, 100]
        for level in levels:
            print(f"\n  Testing {level} concurrent...")
            result = await suite.test_http_concurrent(client, queries, level)
            concurrency_results.append(result)
            print(f"    QPS: {result['qps']}, Success: {result['success_rate']*100:.1f}%")

    # Build results
    from datetime import datetime
    results = {
        "metadata": {
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": env.mode,
            "vector_backend": env.vector_backend,
            "embedding_provider": env.embedding_provider,
            "rerank_provider": env.rerank_provider,
        },
        "quality": quality_results,
        "latency": latency_results,
        "concurrency": concurrency_results,
        "cost": cost_tracker.summary(),
    }

    # Generate reports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save reports BEFORE terminal output (terminal may crash on Windows GBK)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"benchmark_railway_{timestamp}.json"
    save_json_report(results, str(json_path))

    md_path = output_dir / f"benchmark_railway_{timestamp}.md"
    generate_markdown_report(results, str(md_path))

    # Terminal output (may fail on Windows GBK due to emoji)
    try:
        print("\n" + generate_terminal_output(results))
    except UnicodeEncodeError:
        print("\n" + generate_terminal_output(results, ascii_safe=True))

    print(f"\n  JSON report: {json_path}")
    print(f"  Markdown report: {md_path}")

    await client.close()


def main():
    print("=" * 70)
    print("  Aureon RAG Benchmark — Multi-Metric Evaluation")
    print("=" * 70)

    # ── Step 1: Load QA pairs ──
    print("\n[1/5] Loading QA pairs...")
    qa_pairs = load_qa_pairs()
    by_type = defaultdict(list)
    for qa in qa_pairs:
        by_type[qa.get("type", "unknown")].append(qa)

    print(f"  Total QA pairs: {len(qa_pairs)}")
    print(f"  By type: {', '.join(f'{t}({len(v)})' for t, v in sorted(by_type.items()))}")

    # ── Step 2: Load index ──
    print("\n[2/5] Loading vector index...")
    from app.rag.vector_store import retrieve, retrieve_keyword, get_collection_stats
    stats = get_collection_stats()
    print(f"  Documents: {stats[0]}, Chunks: {stats[1]}")

    # ── Step 3: Retrieval evaluation ──
    print("\n[3/5] Retrieval evaluation (Recall@3, Precision@3, MRR)...")
    from app.rag.qa_chain import hybrid_retrieve

    # Separate positive and negative queries for targeted testing
    positive_pairs = [qa for qa in qa_pairs if qa["source_article"] != "none"]
    negative_pairs = [qa for qa in qa_pairs if qa["source_article"] == "none"]

    # Hybrid retrieval
    hybrid_results = test_recall(hybrid_retrieve, qa_pairs, k=3)
    print(f"\n  Hybrid Retrieval:")
    print(f"    Recall@3:     {hybrid_results['recall']*100:.1f}% ({hybrid_results['recall_hits']}/{hybrid_results['recall_total']})")
    print(f"    Recall@10:    {hybrid_results['recall_10']*100:.1f}% ({hybrid_results['recall_10_hits']}/{hybrid_results['recall_total']})")
    print(f"    Precision@3:  {hybrid_results['precision']*100:.1f}%")
    print(f"    MRR:          {hybrid_results['mrr']:.3f}")
    print(f"    nDCG@10:      {hybrid_results['ndcg_10']:.3f}")
    print(f"    Negative Detection: {hybrid_results['negative_detection_rate']*100:.1f}% ({hybrid_results['negative_correct']}/{hybrid_results['negative_total']})")

    if hybrid_results["misses"]:
        print(f"\n  Top misses:")
        for m in hybrid_results["misses"][:5]:
            print(f"    [{m['id']}] {m['question']}")
            print(f"      expected: {m['expected']}, got: {m['retrieved'][:3]}")

    if hybrid_results["negative_wrong"]:
        print(f"\n  Negative detection failures (hallucinated answers):")
        for m in hybrid_results["negative_wrong"][:5]:
            print(f"    [{m['id']}] {m['question']}")
            print(f"      returned {m['retrieved_count']} results from: {m['retrieved_sources'][:3]}")

    # BM25-only
    bm25_results = test_recall(retrieve_keyword, qa_pairs, k=3)
    print(f"\n  BM25 Retrieval:")
    print(f"    Recall@3:     {bm25_results['recall']*100:.1f}% ({bm25_results['recall_hits']}/{bm25_results['recall_total']})")
    print(f"    Precision@3:  {bm25_results['precision']*100:.1f}%")
    print(f"    MRR:          {bm25_results['mrr']:.3f}")

    # Dense vector-only
    dense_results = test_recall(retrieve, qa_pairs, k=3)
    print(f"\n  Dense Vector Retrieval:")
    print(f"    Recall@3:     {dense_results['recall']*100:.1f}% ({dense_results['recall_hits']}/{dense_results['recall_total']})")
    print(f"    Precision@3:  {dense_results['precision']*100:.1f}%")
    print(f"    MRR:          {dense_results['mrr']:.3f}")

    # ── Step 3b: Per-category breakdown ──
    print("\n  Per-difficulty breakdown (Hybrid):")
    cat_results = test_by_category(hybrid_retrieve, qa_pairs, k=3)
    for key in sorted(cat_results.keys()):
        if key.startswith("difficulty_"):
            diff = key.replace("difficulty_", "")
            r = cat_results[key]
            print(f"    {diff:>8}: Recall={r['recall']*100:.1f}% P@3={r['precision']*100:.1f}% MRR={r['mrr']:.3f} (n={r['count']})")

    print("\n  Per-type breakdown (Hybrid):")
    for key in sorted(cat_results.keys()):
        if key.startswith("type_"):
            typ = key.replace("type_", "")
            r = cat_results[key]
            print(f"    {typ:>14}: Recall={r['recall']*100:.1f}% P@3={r['precision']*100:.1f}% MRR={r['mrr']:.3f} (n={r['count']})")

    # ── Step 4: Latency ──
    print("\n[4/6] Latency measurement...")
    lat_bm25 = measure_latency(retrieve_keyword, positive_pairs, num_runs=3)
    lat_vector = measure_latency(retrieve, positive_pairs, num_runs=3)
    lat_hybrid = measure_latency(hybrid_retrieve, positive_pairs, num_runs=3)

    print(f"  BM25:   mean={lat_bm25['mean_ms']}ms  p50={lat_bm25['p50_ms']}ms  p99={lat_bm25['p99_ms']}ms")
    print(f"  Vector: mean={lat_vector['mean_ms']}ms  p50={lat_vector['p50_ms']}ms  p99={lat_vector['p99_ms']}ms")
    print(f"  Hybrid: mean={lat_hybrid['mean_ms']}ms  p50={lat_hybrid['p50_ms']}ms  p99={lat_hybrid['p99_ms']}ms")

    # ── Step 4b: Adaptive Embedding Latency ──
    print("\n[4b/6] Adaptive embedding latency (CPU vs GPU by batch size)...")
    adaptive_latencies = {}
    dispatch_stats = {}
    try:
        from app.rag.embed_gpu import get_adaptive_embedder, GPUEmbedder
        import torch

        adaptive_embedder = get_adaptive_embedder()
        batch_sizes = [1, 2, 4, 8, 16, 32, 64]
        adaptive_latencies = {}

        # Test adaptive embedder
        for bs in batch_sizes:
            texts = ["测试文本用于延迟测量"] * bs
            latencies = []
            for _ in range(3):
                start = time.perf_counter()
                adaptive_embedder.encode(texts, batch_size=bs)
                latencies.append((time.perf_counter() - start) * 1000)
            adaptive_latencies[f"batch_{bs}"] = round(statistics.mean(latencies), 1)

        # Get dispatch stats
        dispatch_stats = adaptive_embedder.get_stats()

        print(f"  Adaptive Embedder (threshold={dispatch_stats['threshold']}):")
        for bs_key, lat in sorted(adaptive_latencies.items()):
            print(f"    {bs_key}: {lat}ms")

        print(f"\n  Dispatch Stats:")
        print(f"    GPU calls: {dispatch_stats['gpu_calls']}")
        print(f"    CPU calls: {dispatch_stats['cpu_calls']}")
        print(f"    GPU ratio: {dispatch_stats['gpu_ratio']:.1%}")

        # Compare with pure GPU (if available)
        if torch.cuda.is_available():
            print(f"\n  Comparison (batch=1):")
            cpu_embedder = GPUEmbedder(device="cpu", use_fp16=False)
            gpu_embedder = GPUEmbedder(device="cuda")

            single_text = ["单条查询测试"]

            # CPU single
            start = time.perf_counter()
            cpu_embedder.encode(single_text, batch_size=1)
            cpu_single = (time.perf_counter() - start) * 1000

            # GPU single
            start = time.perf_counter()
            gpu_embedder.encode(single_text, batch_size=1)
            gpu_single = (time.perf_counter() - start) * 1000

            print(f"      CPU: {cpu_single:.1f}ms")
            print(f"      GPU: {gpu_single:.1f}ms")
            print(f"      Ratio: {gpu_single/cpu_single:.1f}x {'slower' if gpu_single > cpu_single else 'faster'}")

    except Exception as e:
        print(f"  Adaptive embedding test skipped: {e}")

    # ── Step 4c: CRAG Pipeline Negative Detection ──
    # Tests full rag_query pipeline with LLM classifier for negative queries.
    # First run: ~10 min (20 pairs × ~30s LLM). Subsequent runs use classifier cache.
    print("\n[4c/6] CRAG Pipeline negative detection (with LLM classifier)...")
    crag_results = test_pipeline_negative_detection(qa_pairs)
    print(f"  Negative Detection (Pipeline): {crag_results['negative_detection_rate']*100:.1f}% "
          f"({crag_results['negative_correct']}/{crag_results['negative_total']})")
    if crag_results["negative_wrong"]:
        print(f"  Pipeline negative detection failures:")
        for m in crag_results["negative_wrong"][:5]:
            print(f"    [{m['id']}] {m['question'][:50]}... (sources: {m['sources']})")

    # ── Step 5: Summary ──
    print("\n[5/6] Summary")
    print("=" * 70)
    print(f"{'Metric':<35} {'Value':>12} {'Target':>12} {'Status':>8}")
    print("-" * 70)

    targets = {
        "Recall@3 (Hybrid)": (hybrid_results["recall"], 0.95),
        "Recall@10 (Hybrid)": (hybrid_results["recall_10"], 0.97),
        "nDCG@10 (Hybrid)": (hybrid_results["ndcg_10"], 0.80),
        "Precision@3 (Hybrid)": (hybrid_results["precision"], 0.80),
        "MRR (Hybrid)": (hybrid_results["mrr"], 0.85),
        "Negative Detection (Pipeline)": (crag_results["negative_detection_rate"], 0.90),
        "Recall@3 (BM25)": (bm25_results["recall"], 0.90),
        "Recall@3 (Dense)": (dense_results["recall"], 0.85),
        "Latency BM25 (ms)": (lat_bm25["mean_ms"], 10),
        "Latency Vector (ms)": (lat_vector["mean_ms"], 10),
        "Latency Hybrid (ms)": (lat_hybrid["mean_ms"], 26),
    }

    passed = 0
    total = len(targets)
    for label, (actual, target) in targets.items():
        if "Latency" in label:
            passes = actual <= target
            actual_str = f"{actual:.1f}ms"
            target_str = f"≤{target}ms"
        elif "MRR" in label or "nDCG" in label:
            passes = actual >= target
            actual_str = f"{actual:.3f}"
            target_str = f"≥{target}"
        else:
            passes = actual >= target
            actual_str = f"{actual*100:.1f}%"
            target_str = f"≥{target*100:.0f}%"

        status = "[PASS]" if passes else "[FAIL]"
        if passes:
            passed += 1
        print(f"{label:<35} {actual_str:>12} {target_str:>12} {status:>8}")

    print("-" * 70)
    print(f"  Total: {passed}/{total} passed")

    # ── Step 6: Adaptive Dispatch Summary ──
    if dispatch_stats:
        print(f"\n[6/6] Adaptive Device Dispatch Summary")
        print("-" * 70)
        print(f"  Threshold:      {dispatch_stats.get('threshold', 'N/A')} texts")
        print(f"  GPU available:  {dispatch_stats.get('gpu_available', 'N/A')}")
        print(f"  GPU calls:      {dispatch_stats.get('gpu_calls', 0)}")
        print(f"  CPU calls:      {dispatch_stats.get('cpu_calls', 0)}")
        print(f"  Total texts:    {dispatch_stats.get('total_texts', 0)}")
        print(f"  GPU ratio:      {dispatch_stats.get('gpu_ratio', 0):.1%}")
        print()
        print(f"  Batch Latency Breakdown:")
        for bs_key, lat in sorted(adaptive_latencies.items()):
            bs_num = int(bs_key.split('_')[1])
            device = "GPU" if bs_num >= dispatch_stats.get('threshold', 4) else "CPU"
            print(f"    {bs_key:>8}: {lat:>8.1f}ms  ({device})")

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_qa_pairs": len(qa_pairs),
        "collection": {"docs": stats[0], "chunks": stats[1]},
        "hybrid": {
            "recall@3": hybrid_results["recall"],
            "recall@10": hybrid_results["recall_10"],
            "ndcg@10": hybrid_results["ndcg_10"],
            "precision@3": hybrid_results["precision"],
            "mrr": hybrid_results["mrr"],
            "negative_detection_rate": hybrid_results["negative_detection_rate"],
        },
        "bm25": {
            "recall@3": bm25_results["recall"],
            "precision@3": bm25_results["precision"],
            "mrr": bm25_results["mrr"],
        },
        "dense": {
            "recall@3": dense_results["recall"],
            "precision@3": dense_results["precision"],
            "mrr": dense_results["mrr"],
        },
        "by_category": cat_results,
        "latency": {"bm25": lat_bm25, "vector": lat_vector, "hybrid": lat_hybrid},
        "adaptive_embedding": {
            "latencies": adaptive_latencies,
            "dispatch_stats": dispatch_stats,
        },
        "failures": {
            "retrieval_misses": hybrid_results["misses"][:20],
            "negative_wrong": hybrid_results["negative_wrong"][:10],
        },
        "pass_rate": f"{passed}/{total}",
    }

    out_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_actual.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Results saved: {out_path}")

    return output


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "railway":
        asyncio.run(run_railway_benchmark(args))
    else:
        main()
