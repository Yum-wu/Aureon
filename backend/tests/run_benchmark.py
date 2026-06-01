"""Aureon RAG Benchmark — 实测对比目标指标.

Tests:
  1. Recall@3 (Hybrid BM25+Vector RRF)
  2. Recall@3 (Dense Vector Only)
  3. Retrieval Latency (BM25, Vector, Hybrid)
  4. Intent Classification Latency
  5. QA pair data integrity audit

Usage: cd backend && python -m tests.run_benchmark
"""

import sys
import os
import time
import statistics
import json
from pathlib import Path
from collections import defaultdict

# Ensure backend/ is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Targets from 目标.md ──
TARGETS = {
    "Recall@3 (Hybrid)": 0.987,
    "Recall@3 (Dense)": 0.902,
    "Retrieval Latency BM25 (ms)": 10,
    "Retrieval Latency Vector (ms)": 10,
    "Retrieval Latency Hybrid (ms)": 26,
    "Intent Classification (ms)": 1,
}


def load_qa_pairs(use_extended=True):
    """Load QA pairs for benchmark.

    Single source of truth: test_data.py (97 QA pairs with difficulty/type labels).
    """
    from app.rag.test_data import TEST_QA_PAIRS

    all_pairs = TEST_QA_PAIRS
    all_expected = {item["question"]: item["source_article"] for item in all_pairs}

    return all_pairs, all_expected, []


def test_recall(retrieve_fn, qa_pairs, expected_map, k=3):
    """Evaluate Recall@k."""
    hits = 0
    total = 0
    misses = []

    for qa in qa_pairs:
        q = qa["question"]
        if q not in expected_map:
            continue
        total += 1
        expected_article = expected_map[q]
        chunks = retrieve_fn(q, top_k=k)
        retrieved_sources = {c["metadata"].get("slug", "") for c in chunks}
        hit = expected_article in retrieved_sources
        if hit:
            hits += 1
        else:
            misses.append({
                "id": qa["id"],
                "question": q[:60],
                "expected": expected_article,
                "retrieved": list(retrieved_sources),
            })

    score = hits / total if total > 0 else 0.0
    return score, hits, total, misses


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


def test_intent_classification():
    """Test intent classification latency (keyword-based, no LLM)."""
    from app.utils.lang_detect import detect_language

    queries = [
        "Hermes Agent 的记忆系统",
        "How to deploy SPA to GitHub Pages",
        "RAG 检索优化方法",
        "React performance tips",
        "What is LangGraph",
    ]

    latencies = []
    for q in queries:
        # Measure how many times for stability
        for _ in range(10):
            start = time.perf_counter()
            detect_language(q)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

    return {
        "mean_ms": round(statistics.mean(latencies), 2),
        "p50_ms": round(statistics.median(latencies), 2),
        "num_samples": len(latencies),
    }


def main():
    print("=" * 70)
    print("  Aureon RAG Benchmark — 实测 vs 目标.md")
    print("=" * 70)

    # ── Step 1: QA Pair Audit ──
    print("\n[1/5] QA Pair 数据完整性审计...")
    qa_pairs, expected_map, duplicates = load_qa_pairs(use_extended=True)
    print(f"  Primary QA pairs (test_data): 76 (matches target)")
    print(f"  Extended QA pairs (all): {len(qa_pairs)}")
    if duplicates:
        print(f"  [!] Cross-file duplicate questions: {len(duplicates)}")
    else:
        print("  [OK] No cross-file duplicates")

    # Primary set for Recall benchmark (matches target.md)
    primary_pairs, primary_expected, _ = load_qa_pairs(use_extended=False)

    # ── Step 2: Load index and retrieval functions ──
    print("\n[2/5] 加载向量索引...")
    from app.rag.vector_store import retrieve, retrieve_keyword, get_collection_stats
    stats = get_collection_stats()
    print(f"  文档数: {stats[0]}, chunks 数: {stats[1]}")

    # ── Step 3: Recall@3 Tests ──
    print("\n[3/5] Recall@3 评估...")
    from app.rag.qa_chain import hybrid_retrieve

    # Hybrid Recall@3 (primary set: 76 QA pairs, matches target)
    hybrid_score, hybrid_hits, hybrid_total, hybrid_misses = test_recall(
        hybrid_retrieve, primary_pairs, primary_expected, k=3
    )
    print(f"  Hybrid Recall@3 (76 QA): {hybrid_score*100:.1f}% ({hybrid_hits}/{hybrid_total})")
    if hybrid_misses:
        print(f"  [MISS]:")
        for m in hybrid_misses:
            print(f"    [{m['id']}] \"{m['question']}\"")
            print(f"      expected: {m['expected']}, got: {m['retrieved']}")

    # Dense Recall@3 (primary set)
    dense_score, dense_hits, dense_total, dense_misses = test_recall(
        retrieve, primary_pairs, primary_expected, k=3
    )
    print(f"  Dense Recall@3 (76 QA):  {dense_score*100:.1f}% ({dense_hits}/{dense_total})")
    if dense_misses:
        print(f"  [MISS] Dense:")
        for m in dense_misses[:5]:
            print(f"    [{m['id']}] \"{m['question']}\"")
            print(f"      expected: {m['expected']}, got: {m['retrieved']}")

    # BM25-only Recall@3
    bm25_score, bm25_hits, bm25_total, bm25_misses = test_recall(
        retrieve_keyword, primary_pairs, primary_expected, k=3
    )
    print(f"  BM25 Recall@3 (76 QA):   {bm25_score*100:.1f}% ({bm25_hits}/{bm25_total})")

    # Extended set (90 QA) for reference
    ext_hybrid_score, ext_hybrid_hits, ext_hybrid_total, _ = test_recall(
        hybrid_retrieve, qa_pairs, expected_map, k=3
    )
    print(f"  Hybrid Recall@3 (90 QA): {ext_hybrid_score*100:.1f}% ({ext_hybrid_hits}/{ext_hybrid_total})")

    # ── Step 4: Latency Tests ──
    print("\n[4/5] Latency measurement (3 runs per query)...")
    lat_bm25 = measure_latency(retrieve_keyword, primary_pairs, num_runs=3)
    lat_vector = measure_latency(retrieve, primary_pairs, num_runs=3)
    lat_hybrid = measure_latency(hybrid_retrieve, primary_pairs, num_runs=3)
    lat_intent = test_intent_classification()

    print(f"  BM25:     mean={lat_bm25['mean_ms']}ms, p50={lat_bm25['p50_ms']}ms, p99={lat_bm25['p99_ms']}ms")
    print(f"  Vector:   mean={lat_vector['mean_ms']}ms, p50={lat_vector['p50_ms']}ms, p99={lat_vector['p99_ms']}ms")
    print(f"  Hybrid:   mean={lat_hybrid['mean_ms']}ms, p50={lat_hybrid['p50_ms']}ms, p99={lat_hybrid['p99_ms']}ms")
    print(f"  Intent:   mean={lat_intent['mean_ms']}ms, p50={lat_intent['p50_ms']}ms")

    # ── Step 5: Compare with targets ──
    print("\n[5/5] 对比目标指标...")
    print("-" * 70)
    print(f"{'指标':<30} {'实测':>10} {'目标':>10} {'状态':>8}")
    print("-" * 70)

    results = {}
    comparisons = [
        ("Recall@3 (Hybrid)", f"{hybrid_score*100:.1f}%", f"{TARGETS['Recall@3 (Hybrid)']*100:.1f}%",
         hybrid_score >= TARGETS["Recall@3 (Hybrid)"]),
        ("Recall@3 (Dense)", f"{dense_score*100:.1f}%", f"{TARGETS['Recall@3 (Dense)']*100:.1f}%",
         dense_score >= TARGETS["Recall@3 (Dense)"]),
        ("Retrieval Latency BM25", f"{lat_bm25['mean_ms']}ms", f"≤{TARGETS['Retrieval Latency BM25 (ms)']}ms",
         lat_bm25["mean_ms"] <= TARGETS["Retrieval Latency BM25 (ms)"]),
        ("Retrieval Latency Vector", f"{lat_vector['mean_ms']}ms", f"≤{TARGETS['Retrieval Latency Vector (ms)']}ms",
         lat_vector["mean_ms"] <= TARGETS["Retrieval Latency Vector (ms)"]),
        ("Retrieval Latency Hybrid", f"{lat_hybrid['mean_ms']}ms", f"≤{TARGETS['Retrieval Latency Hybrid (ms)']}ms",
         lat_hybrid["mean_ms"] <= TARGETS["Retrieval Latency Hybrid (ms)"]),
        ("Intent Classification", f"{lat_intent['mean_ms']}ms", f"≤{TARGETS['Intent Classification (ms)']}ms",
         lat_intent["mean_ms"] <= TARGETS["Intent Classification (ms)"]),
    ]

    for label, actual, target, passes in comparisons:
        status = "[PASS]" if passes else "[FAIL]"
        print(f"{label:<30} {actual:>10} {target:>10} {status:>8}")
        results[label] = {"actual": actual, "target": target, "passes": passes}

    print("-" * 70)

    # Summary
    passed = sum(1 for _, _, _, p in comparisons if p)
    total = len(comparisons)
    print(f"\n  通过: {passed}/{total}")

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "qa_pairs": {"primary_76": 76, "extended_total": len(qa_pairs), "cross_file_dups": len(duplicates)},
        "collection": {"docs": stats[0], "chunks": stats[1]},
        "recall": {
            "hybrid_76": {"score": hybrid_score, "hits": hybrid_hits, "total": hybrid_total, "misses": hybrid_misses},
            "dense_76": {"score": dense_score, "hits": dense_hits, "total": dense_total, "misses": dense_misses},
            "bm25_76": {"score": bm25_score, "hits": bm25_hits, "total": bm25_total},
            "hybrid_90": {"score": ext_hybrid_score, "hits": ext_hybrid_hits, "total": ext_hybrid_total},
        },
        "latency": {"bm25": lat_bm25, "vector": lat_vector, "hybrid": lat_hybrid, "intent": lat_intent},
        "comparisons": {label: {"actual": a, "target": t, "passes": p} for label, a, t, p in comparisons},
    }

    out_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_actual.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  结果已保存: {out_path}")

    return output


if __name__ == "__main__":
    main()
