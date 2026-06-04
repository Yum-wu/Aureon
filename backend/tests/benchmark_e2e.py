"""Full End-to-End RAG Benchmark: RRF + LLM + Answer Quality.

Tests the complete pipeline: Embedding -> Hybrid Retrieval (RRF) -> LLM Generation.
Measures per-stage latency and answer quality against 97 QA pairs.

Run: cd backend && python -m tests.benchmark_e2e
"""

import time
import os
import sys
import statistics
import json
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.rag.test_data import TEST_QA_PAIRS
from app.rag.vector_store import (
    retrieve, retrieve_keyword, embed_texts_llm,
    get_collection_stats, _build_kw_index
)
from app.rag.qa_chain import hybrid_retrieve


def make_llm_call(llm, messages):
    """Synchronous LLM call."""
    response = llm.invoke(messages)
    return response.content


def check_answer_quality(answer: str, expected_answer: str) -> dict:
    """Simple answer quality check: keyword overlap + length."""
    answer_lower = answer.lower()
    expected_words = set(expected_answer.lower().split())
    answer_words = set(answer_lower.split())

    # Don't penalize "knowledge base doesn't have" answers for negative questions
    if "知识库中没有" in answer or "no relevant" in answer_lower or "not found" in answer_lower:
        if "知识库中没有" in expected_answer or "no" in expected_answer.lower():
            return {"relevance": 1.0, "completeness": 1.0, "faithful": True}

    # Keyword overlap
    if expected_words:
        overlap = len(answer_words & expected_words) / len(expected_words)
    else:
        overlap = 0.0

    # Length check (too short = incomplete, too long = verbose)
    len_ratio = len(answer) / max(len(expected_answer), 1)
    if 0.3 < len_ratio < 3.0:
        length_score = 1.0
    elif len_ratio <= 0.3:
        length_score = len_ratio / 0.3
    else:
        length_score = 3.0 / len_ratio

    return {
        "relevance": min(overlap * 2, 1.0),
        "completeness": length_score,
        "faithful": "不知道" not in answer and "没有" not in answer or "知识库中没有" in expected_answer,
    }


def run_e2e_benchmark():
    print("=" * 70)
    print("  AUREON RAG -- Full E2E Benchmark (RRF + LLM)")
    print("=" * 70)

    # ── Init ──
    print("\n> Phase 1: Initialization")
    _build_kw_index(force=True)
    doc_count, chunk_count = get_collection_stats()
    print(f"  Documents: {doc_count}, Chunks: {chunk_count}")

    # ── Init LLM ──
    print("\n> Phase 2: LLM Setup")
    from app.agent.llm import create_llm
    llm = create_llm()
    print(f"  Model: {llm.model_name if hasattr(llm, 'model_name') else 'deepseek'}")

    # ── Test categories ──
    positive_qa = [qa for qa in TEST_QA_PAIRS if "知识库中没有" not in qa["answer"]]
    negative_qa = [qa for qa in TEST_QA_PAIRS if "知识库中没有" in qa["answer"]]
    print(f"  Positive QA: {len(positive_qa)}, Negative QA: {len(negative_qa)}")

    # ═══════════════════════════════════════════════════════════════
    # Phase 3: Hybrid Retrieval (RRF) Quality
    # ═══════════════════════════════════════════════════════════════
    print(f"\n> Phase 3: Hybrid Retrieval (RRF) -- {len(TEST_QA_PAIRS)} queries")

    rrf_results = {"recall": {3: 0, 5: 0, 10: 0}, "mrr": [], "hits": 0,
                   "latencies": [], "vector_only_hits": 0, "bm25_only_hits": 0, "rrf_extra": 0}

    for i, qa in enumerate(TEST_QA_PAIRS):
        query = qa["question"]
        source = qa.get("source_article", "")

        # Hybrid retrieval (RRF)
        t0 = time.perf_counter()
        chunks = hybrid_retrieve(query, top_k=10)
        latency = (time.perf_counter() - t0) * 1000
        rrf_results["latencies"].append(latency)

        # Vector-only for comparison
        v_results = retrieve(query, top_k=10)
        b_results = retrieve_keyword(query, top_k=10)

        # Check if RRF found the source
        rrf_found = False
        for k in [3, 5, 10]:
            found = False
            for doc in chunks[:k]:
                text = (doc.get("text", "") + doc.get("metadata", {}).get("source", "")).lower()
                if source and source.lower() in text:
                    found = True
                    break
            if found:
                rrf_results["recall"][k] += 1
                if k == 5:
                    rrf_found = True

        # MRR
        mrr_rank = 0
        for j, doc in enumerate(chunks[:10]):
            text = (doc.get("text", "") + doc.get("metadata", {}).get("source", "")).lower()
            if source and source.lower() in text:
                mrr_rank = j + 1
                break
        rrf_results["mrr"].append(1.0 / mrr_rank if mrr_rank > 0 else 0.0)
        if mrr_rank > 0:
            rrf_results["hits"] += 1

        # Compare: did RRF find it when individual retrievers didn't?
        v_found = any(source.lower() in (d.get("text", "") + d.get("metadata", {}).get("source", "")).lower()
                      for d in v_results[:5])
        b_found = any(source.lower() in d.get("text", "").lower() for d in b_results[:5])

        if v_found:
            rrf_results["vector_only_hits"] += 1
        if b_found:
            rrf_results["bm25_only_hits"] += 1
        if rrf_found and not v_found and not b_found:
            rrf_results["rrf_extra"] += 1

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i+1}/{len(TEST_QA_PAIRS)}")

    # ═══════════════════════════════════════════════════════════════
    # Phase 4: End-to-End RAG (Retrieval + LLM Generation)
    # ═══════════════════════════════════════════════════════════════
    print(f"\n> Phase 4: E2E RAG (Retrieval + LLM) -- testing {min(20, len(positive_qa))} positive QA")

    # Test a subset to save time (LLM calls are slow)
    test_sample = positive_qa[:20]
    e2e_results = {"answers": [], "latencies": [], "stage_latencies": [],
                   "quality_scores": []}

    from app.rag.qa_chain import format_context

    for i, qa in enumerate(test_sample):
        query = qa["question"]
        expected = qa["answer"]
        source = qa.get("source_article", "")

        # Stage 1: Embedding
        t0 = time.perf_counter()
        embed_texts_llm([query])
        t_embed = (time.perf_counter() - t0) * 1000

        # Stage 2: Hybrid retrieval (RRF)
        t0 = time.perf_counter()
        chunks = hybrid_retrieve(query, top_k=3)
        t_retrieve = (time.perf_counter() - t0) * 1000

        # Stage 3: Format context
        t0 = time.perf_counter()
        context = format_context(chunks)
        t_format = (time.perf_counter() - t0) * 1000

        # Stage 4: LLM generation
        from app.agent.llm import create_llm
        llm = create_llm()
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Answer based on the provided context. If the context doesn't contain relevant information, say so."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
        ]
        t0 = time.perf_counter()
        answer = make_llm_call(llm, messages)
        t_llm = (time.perf_counter() - t0) * 1000

        total = t_embed + t_retrieve + t_format + t_llm

        # Quality check
        quality = check_answer_quality(answer, expected)

        e2e_results["answers"].append({"query": query, "answer": answer[:200], "expected": expected[:200]})
        e2e_results["latencies"].append(total)
        e2e_results["stage_latencies"].append({
            "embed": t_embed, "retrieve": t_retrieve,
            "format": t_format, "llm": t_llm, "total": total
        })
        e2e_results["quality_scores"].append(quality)

        if (i + 1) % 5 == 0:
            print(f"  Progress: {i+1}/{len(test_sample)} | Last: {total:.0f}ms (LLM: {t_llm:.0f}ms)")

    # ═══════════════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  FULL E2E BENCHMARK RESULTS")
    print("=" * 70)

    # --- Hybrid Retrieval (RRF) ---
    print(f"\n  === Hybrid Retrieval (RRF) ===")
    print(f"  Total queries:         {len(TEST_QA_PAIRS)}")
    for k in [3, 5, 10]:
        rate = rrf_results["recall"][k] / len(TEST_QA_PAIRS) * 100
        target = "OK" if rate >= 80 else "WARN"
        print(f"  Recall@{k}:              {rrf_results['recall'][k]}/{len(TEST_QA_PAIRS)} = {rate:.1f}%  [{target}]")

    rrf_mrr = statistics.mean(rrf_results["mrr"])
    print(f"  MRR:                   {rrf_mrr:.3f}  [{'OK' if rrf_mrr >= 0.6 else 'WARN'}]")
    print(f"  Hit Rate:              {rrf_results['hits']}/{len(TEST_QA_PAIRS)} = {rrf_results['hits']/len(TEST_QA_PAIRS)*100:.1f}%")

    print(f"\n  --- RRF Value Analysis ---")
    print(f"  Vector alone found:    {rrf_results['vector_only_hits']}/{len(TEST_QA_PAIRS)}")
    print(f"  BM25 alone found:      {rrf_results['bm25_only_hits']}/{len(TEST_QA_PAIRS)}")
    print(f"  RRF found (neither):   {rrf_results['rrf_extra']}/{len(TEST_QA_PAIRS)}  <-- RRF unique contribution")

    lat_sorted = sorted(rrf_results["latencies"])
    print(f"\n  --- Retrieval Latency ---")
    print(f"  P50:                   {lat_sorted[len(lat_sorted)//2]:.1f}ms")
    print(f"  P90:                   {lat_sorted[int(len(lat_sorted)*0.9)]:.1f}ms")
    print(f"  Avg:                   {statistics.mean(rrf_results['latencies']):.1f}ms")

    # --- E2E RAG ---
    print(f"\n  === E2E RAG (Retrieval + LLM) ===")
    print(f"  Tested:                {len(test_sample)} queries")

    # Stage breakdown
    stages = {"embed": [], "retrieve": [], "format": [], "llm": [], "total": []}
    for sl in e2e_results["stage_latencies"]:
        for k in stages:
            stages[k].append(sl[k])

    print(f"\n  --- Per-Stage Latency ---")
    for stage_name, stage_label in [("embed", "Embedding"), ("retrieve", "Retrieval (RRF)"),
                                     ("format", "Context Format"), ("llm", "LLM Generation"),
                                     ("total", "TOTAL")]:
        vals = stages[stage_name]
        avg = statistics.mean(vals)
        p50 = sorted(vals)[len(vals)//2]
        print(f"  {stage_label:25s}  Avg: {avg:7.0f}ms  P50: {p50:7.0f}ms")

    # LLM contribution
    llm_pct = statistics.mean(stages["llm"]) / statistics.mean(stages["total"]) * 100
    retrieve_pct = statistics.mean(stages["retrieve"]) / statistics.mean(stages["total"]) * 100
    print(f"\n  --- Time Distribution ---")
    print(f"  LLM Generation:        {llm_pct:.0f}% of total")
    print(f"  Retrieval (RRF):       {retrieve_pct:.0f}% of total")
    print(f"  Embedding + Format:    {100-llm_pct-retrieve_pct:.0f}% of total")

    # Quality
    print(f"\n  --- Answer Quality ---")
    avg_relevance = statistics.mean([q["relevance"] for q in e2e_results["quality_scores"]])
    avg_completeness = statistics.mean([q["completeness"] for q in e2e_results["quality_scores"]])
    faithful_count = sum(1 for q in e2e_results["quality_scores"] if q["faithful"])
    print(f"  Relevance:             {avg_relevance:.2f}  (target: >0.5)")
    print(f"  Completeness:          {avg_completeness:.2f}  (target: >0.5)")
    print(f"  Faithful:              {faithful_count}/{len(test_sample)} = {faithful_count/len(test_sample)*100:.0f}%")

    # Sample answers
    print(f"\n  --- Sample Answers ---")
    for item in e2e_results["answers"][:3]:
        print(f"  Q: {item['query'][:60]}...")
        print(f"  A: {item['answer'][:100]}...")
        print()

    # --- Summary ---
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Metric':<30} {'Value':<15} {'Target':<15} {'Status'}")
    print(f"  {'-'*30} {'-'*15} {'-'*15} {'-'*10}")

    r5_rate = rrf_results["recall"][5] / len(TEST_QA_PAIRS) * 100
    print(f"  {'RRF Recall@5':<30} {r5_rate:.1f}%{'':<11} {'>=85%':<15} {'OK' if r5_rate >= 85 else 'WARN'}")
    print(f"  {'RRF MRR':<30} {rrf_mrr:.3f}{'':<12} {'>=0.600':<15} {'OK' if rrf_mrr >= 0.6 else 'WARN'}")
    print(f"  {'RRF Latency P50':<30} {lat_sorted[len(lat_sorted)//2]:.0f}ms{'':<10} {'<200ms':<15} {'OK' if lat_sorted[len(lat_sorted)//2] < 200 else 'WARN'}")
    print(f"  {'E2E Total Latency':<30} {statistics.mean(stages['total']):.0f}ms{'':<10} {'<5000ms':<14} {'OK' if statistics.mean(stages['total']) < 5000 else 'WARN'}")
    print(f"  {'LLM Generation':<30} {statistics.mean(stages['llm']):.0f}ms{'':<10} {'<3000ms':<14} {'OK' if statistics.mean(stages['llm']) < 3000 else 'WARN'}")
    print(f"  {'Answer Relevance':<30} {avg_relevance:.2f}{'':<13} {'>0.50':<15} {'OK' if avg_relevance > 0.5 else 'WARN'}")
    print(f"  {'Answer Faithful':<30} {faithful_count/len(test_sample)*100:.0f}%{'':<12} {'>90%':<15} {'OK' if faithful_count/len(test_sample) > 0.9 else 'WARN'}")
    print("=" * 70)


if __name__ == "__main__":
    run_e2e_benchmark()
