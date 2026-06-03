# RAG 测试套件全面重建

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current "cheated" QA test suite with a rigorous, multi-dimensional RAG evaluation that catches real-world failures — not just source-matching recall.

**Architecture:** 
1. Audit + clean existing 96 QA pairs (remove cheated ones, fix weak cross-article queries)
2. Generate 100+ new QA pairs from all 40 documents, covering factual/reasoning/negative/cross-article types
3. Add Precision@3, MRR, negative detection metrics to benchmark
4. Run full benchmark against production and publish results

**Tech Stack:** Python, pytest, existing evaluator.py (recall/faithfulness), run_benchmark.py

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/rag/test_data.py` | Modify | Clean + deduplicate + add negative cases |
| `backend/app/rag/new_qa_pairs.py` | Delete | Merge into test_data.py, remove duplicates |
| `backend/tests/run_benchmark.py` | Modify | Add Precision@3, MRR, negative detection, faithfulness |
| `backend/data/benchmark_results.json` | Modify | Update with new comprehensive results |
| `backend/tests/test_rag_quality.py` | Create | Pytest-based quality gates for CI |

---

## Task 1: Audit and Clean Existing QA Pairs

**Files:**
- Modify: `backend/app/rag/test_data.py`

### Problems to Fix

1. **Remove "cheated" QA pairs** where the question contains retrieval keywords that make the answer trivially extractable:
   - Questions like "X的百分比是多少?" → single-number recall (too easy)
   - Questions where the question text contains the article title/topic verbatim

2. **Strengthen cross-article queries** — replace vague "两篇文章的共同点是什么?" with specific comparison questions:
   - "LangChain Agent 和 Hermes Agent 在记忆管理上有什么区别?"
   - "RAG 系统和纯微调方案各有什么优劣?"

3. **Deduplicate** — merge test_data.py and new_qa_pairs.py into a single file, remove 7 duplicate pairs

4. **Add quality labels** — each QA pair gets a `difficulty` field: `easy` / `medium` / `hard`

### Criteria for "Cheated" QA Pairs (Remove/Rewrite)

A QA pair is "cheated" if ANY of these are true:
- The question contains a unique keyword that maps 1:1 to one article (e.g., "分支策略" → git-workflow)
- The answer is a single number/phrase extractable from one sentence
- The question uses the exact same phrasing as a section heading in the article
- The question could be answered by keyword matching alone (no semantic understanding needed)

### Criteria for "Good" QA Pairs (Keep/Create)

- Requires understanding multiple sentences/chunks to answer
- Uses different vocabulary than the article (paraphrased question)
- Cannot be answered by finding a single keyword match
- Tests genuine comprehension, not just retrieval

---

## Task 2: Generate Comprehensive QA Pairs from All 40 Documents

**Files:**
- Modify: `backend/app/rag/test_data.py`

### Generation Strategy

For each of the 40 documents, generate 3-5 QA pairs covering:

| Type | Count/Doc | Example |
|------|-----------|---------|
| **Factual** | 1-2 | "What embedding model does Aureon use?" (requires reading the doc) |
| **Reasoning** | 1 | "Why did the author choose BM25 over pure vector search?" (requires synthesis) |
| **Negative** | 0-1 | "What is the deployment cost on AWS?" (answer NOT in any doc) |
| **Cross-article** | Shared | "Compare RAG approach vs fine-tuning based on the articles" |

### Document → QA Generation Rules

For each document:
1. Read the full article content
2. Identify 3-5 key facts/concepts that require multi-sentence understanding
3. Write questions using DIFFERENT vocabulary than the article (no copy-paste)
4. For every 5 factual questions, add 1 negative/unanswerable question
5. Write questions that a keyword-only search would MISS

### Negative/Unanswerable Questions (Critical)

Add at least 15 negative questions covering:
- Topics NOT covered by any article (e.g., "What cloud provider does Aureon use for production?")
- Partially covered topics where the specific detail is missing
- Questions about future plans not documented
- Questions requiring information from external sources not in the knowledge base

Expected negative question topics:
- AWS/GCP/Azure specific configurations (not covered)
- Pricing/cost details (not in articles)
- Specific API rate limits (not documented)
- Team size/hiring plans (not in articles)
- Comparison with specific competitors (not covered)

---

## Task 3: Rebuild Benchmark Script with Multi-Metric Evaluation

**Files:**
- Modify: `backend/tests/run_benchmark.py`

### New Metrics to Add

1. **Precision@3** — of the top-3 retrieved chunks, how many are from the correct article?
2. **MRR (Mean Reciprocal Rank)** — rank of the first relevant result
3. **Negative Detection Rate** — for unanswerable queries, does the system return "no results" instead of hallucinating?
4. **Faithfulness** — use existing `evaluate_faithfulness()` from evaluator.py (LLM-as-judge)

### Benchmark Script Changes

```python
# New metrics structure
results = {
    "recall_at_3": float,       # existing
    "precision_at_3": float,    # NEW
    "mrr": float,               # NEW
    "hit_rate": float,          # existing (same as recall@3 for now)
    "negative_detection_rate": float,  # NEW
    "faithfulness_score": float,       # NEW (LLM-as-judge, sampled)
    "retrieval_latency": {...},  # existing
    "total_qa_pairs": int,
    "negative_qa_pairs": int,
    "by_difficulty": {
        "easy": {"recall": float, "precision": float},
        "medium": {"recall": float, "precision": float},
        "hard": {"recall": float, "precision": float},
    },
    "by_language": {
        "zh": {"recall": float, "count": int},
        "en": {"recall": float, "count": int},
    },
    "failures": [...]  # list of failed QA pairs for debugging
}
```

### Faithfulness Sampling

Full faithfulness evaluation (LLM-as-judge) is expensive. Strategy:
- Run faithfulness on a stratified sample: 20% of QA pairs (stratified by difficulty)
- This gives ~20 faithfulness scores, sufficient for a reliable estimate
- Use DeepSeek as judge (already configured as LLM)

---

## Task 4: Run Full Benchmark Against Production

**Files:**
- Execute: `backend/tests/run_benchmark.py` against production API

### Execution Plan

1. Rebuild production index (`POST /api/rag/index`)
2. Run benchmark script against production endpoints
3. Collect all metrics
4. Compare with previous benchmark (benchmark_actual.json)
5. Publish results to benchmark_results.json

### Expected Output

```
=== Aureon RAG Benchmark Report ===
Date: 2026-06-01
Total QA Pairs: ~150 (96 existing + ~60 new + ~15 negative)

Retrieval Metrics:
  Recall@3:     XX.X% (target: ≥95%)
  Precision@3:  XX.X% (target: ≥80%)
  MRR:          X.XX  (target: ≥0.85)
  Hit Rate:     XX.X%

Quality Metrics:
  Negative Detection Rate: XX.X% (target: ≥90%)
  Faithfulness Score:      X.XX  (target: ≥0.85)

By Difficulty:
  Easy:   Recall XX.X% / Precision XX.X%  (N=XX)
  Medium: Recall XX.X% / Precision XX.X%  (N=XX)
  Hard:   Recall XX.X% / Precision XX.X%  (N=XX)

Latency:
  BM25:     X.Xms (p50) / X.Xms (p99)
  Vector:   X.Xms (p50) / X.Xms (p99)
  Hybrid:   X.Xms (p50) / X.Xms (p99)

Top 5 Failures:
  1. [query] → expected [source], got [actual]
  ...
```

---

## Task 5: Create CI Quality Gate

**Files:**
- Create: `backend/tests/test_rag_quality.py`

A pytest-based quality gate that runs on every CI:
- Tests retrieval recall on a small subset (30 QA pairs)
- Tests negative detection (10 unanswerable queries)
- Sets minimum thresholds as pytest asserts
- Runs fast (<30s) for CI, full benchmark only on demand

---

## Execution Order

```
Task 1 (Clean QA) → Task 2 (Generate QA) → Task 3 (Benchmark Script) → Task 4 (Run) → Task 5 (CI Gate)
```

Tasks 1-2 are sequential (clean first, then generate). 
Tasks 3-5 can start after Task 2 completes.
