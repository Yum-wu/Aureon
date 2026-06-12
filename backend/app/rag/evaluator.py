"""
RAG Evaluation: Recall@k, Faithfulness (LLM-as-judge), Latency stats.
"""

import json
import math
import time
import statistics
from typing import Callable, List, Dict, Any

from app.rag.test_data import TEST_QA_PAIRS, RETRIEVAL_EXPECTED
from app.rag.models import RAGQueryResponse

try:
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    # Provide fallback functions
    def ragas_evaluate(*args, **kwargs):
        raise ImportError("ragas is not installed. Install it with: pip install ragas")
    class _FallbackMetric:
        def __init__(self, name):
            self.name = name
        def __call__(self, *args, **kwargs):
            raise ImportError(f"ragas is not installed. Cannot compute {self.name}")
    faithfulness = _FallbackMetric("faithfulness")
    answer_relevancy = _FallbackMetric("answer_relevancy")
    context_precision = _FallbackMetric("context_precision")


# ── Recall@k ──

def evaluate_recall(
    retrieve_fn: Callable,
    qa_pairs: List[Dict] = None,
    expected_map: Dict[str, str] = None,
    k: int = 3,
) -> Dict[str, Any]:
    """Evaluate Recall@k: does correct source appear in top-k results?"""
    pairs = qa_pairs or TEST_QA_PAIRS
    exp = expected_map or RETRIEVAL_EXPECTED

    hits = 0
    total = 0
    details = []

    for qa in pairs:
        q = qa["question"]
        if q not in exp:
            continue
        total += 1
        expected_article = exp[q]
        chunks = retrieve_fn(q, top_k=k)
        retrieved_sources = {c["metadata"].get("slug", "") for c in chunks}
        hit = expected_article in retrieved_sources
        if hit:
            hits += 1
        details.append({
            "question": q[:60],
            "expected": expected_article,
            "retrieved": list(retrieved_sources),
            "hit": hit,
        })

    recall = hits / total if total > 0 else 0.0
    return {
        "metric": "Recall@k",
        "k": k,
        "hits": hits,
        "total": total,
        "score": round(recall, 4),
        "details": details,
    }


def ndcg_at_k(retrieved_sources: list, expected_source: str, k: int = 10) -> float:
    """Calculate nDCG@K for a single query. Relevant doc scores 1.0."""
    dcg = 0.0
    for i, source in enumerate(retrieved_sources[:k]):
        rel = 1.0 if source == expected_source else 0.0
        dcg += rel / math.log2(i + 2)
    idcg = 1.0  # ideal: relevant doc at rank 1
    return dcg / idcg if idcg > 0 else 0.0


FAITHFULNESS_JUDGE_PROMPT = """你是一个评估助手。判断以下回答是否忠实于提供的参考文档。

判断标准（0-10）：
- 10：完全基于参考文档，无任何编造
- 7-9：大部分基于参考文档，少量合理推断
- 4-6：部分内容不在参考文档中
- 1-3：大量内容不在参考文档中或与文档矛盾
- 0：完全无关或编造

只输出 JSON 格式：{{"score": <int>, "reason": "<一句话理由>"}}

参考文档：
{context}

回答：{answer}
"""


def evaluate_faithfulness(
    rag_query_fn: Callable,
    llm,
    qa_pairs: List[Dict] = None,
) -> Dict[str, Any]:
    """Evaluate answer faithfulness using LLM-as-judge."""
    pairs = qa_pairs or TEST_QA_PAIRS

    scores = []
    details = []

    for qa in pairs:
        q = qa["question"]
        qa["answer"]

        result: RAGQueryResponse = rag_query_fn(q)
        if not result.sources:
            continue

        context_parts = []
        for s in result.sources:
            context_parts.append(f"[{s.title}]\n{s.chunk}")
        context = "\n\n".join(context_parts)

        judge_prompt = FAITHFULNESS_JUDGE_PROMPT.format(
            context=context, answer=result.answer
        )
        try:
            judge_resp = llm.invoke([{"role": "user", "content": judge_prompt}])
            judge_data = json.loads(judge_resp.content.strip().removeprefix("```json").removesuffix("```").strip())
            score = judge_data["score"]
        except Exception:
            score = 0

        scores.append(score)
        details.append({
            "question": q[:60],
            "answer": result.answer[:200],
            "faithfulness_score": score,
        })

    avg = statistics.mean(scores) if scores else 0.0
    return {
        "metric": "Faithfulness",
        "average_score": round(avg, 2),
        "min": min(scores) if scores else 0,
        "max": max(scores) if scores else 0,
        "num_samples": len(scores),
        "details": details,
    }


# ── Latency ──

def evaluate_latency(
    rag_query_fn: Callable,
    qa_pairs: List[Dict] = None,
    num_runs: int = 3,
) -> Dict[str, Any]:
    """Measure RAG query latency (p50, p99, mean)."""
    pairs = qa_pairs or TEST_QA_PAIRS

    all_latencies = []

    for qa in pairs:
        q = qa["question"]
        for _ in range(num_runs):
            start = time.time()
            rag_query_fn(q)
            elapsed = (time.time() - start) * 1000
            all_latencies.append(elapsed)

    if not all_latencies:
        return {"metric": "Latency", "error": "no data"}

    sorted_lats = sorted(all_latencies)
    n = len(sorted_lats)

    return {
        "metric": "Latency (ms)",
        "mean_ms": round(statistics.mean(sorted_lats), 1),
        "p50_ms": round(sorted_lats[n // 2], 1),
        "p99_ms": round(sorted_lats[int(n * 0.99) - 1], 1),
        "min_ms": round(sorted_lats[0], 1),
        "max_ms": round(sorted_lats[-1], 1),
        "num_samples": n,
    }


# ── RAGAS Evaluation ──

def evaluate_faithfulness_ragas(
    query: str,
    answer: str,
    contexts: List[str],
) -> Dict[str, Any]:
    """Evaluate faithfulness using RAGAS metric."""
    if not RAGAS_AVAILABLE:
        return {"metric": "Faithfulness (RAGAS)", "error": "ragas not installed", "score": None}
    # Build dataset for ragas
    from datasets import Dataset
    data = {
        "question": [query],
        "answer": [answer],
        "contexts": [contexts],
    }
    dataset = Dataset.from_dict(data)
    result = ragas_evaluate(dataset, metrics=[faithfulness])
    score = result["faithfulness"][0]
    return {
        "metric": "Faithfulness (RAGAS)",
        "score": score,
        "query": query[:60],
        "answer": answer[:200],
    }

def evaluate_answer_relevance_ragas(
    query: str,
    answer: str,
    contexts: List[str],
) -> Dict[str, Any]:
    """Evaluate answer relevance using RAGAS metric."""
    if not RAGAS_AVAILABLE:
        return {"metric": "Answer Relevancy (RAGAS)", "error": "ragas not installed", "score": None}
    from datasets import Dataset
    data = {
        "question": [query],
        "answer": [answer],
        "contexts": [contexts],
    }
    dataset = Dataset.from_dict(data)
    result = ragas_evaluate(dataset, metrics=[answer_relevancy])
    score = result["answer_relevancy"][0]
    return {
        "metric": "Answer Relevancy (RAGAS)",
        "score": score,
        "query": query[:60],
        "answer": answer[:200],
    }

def evaluate_context_precision_ragas(
    query: str,
    contexts: List[str],
    ground_truth: str,
) -> Dict[str, Any]:
    """Evaluate context precision using RAGAS metric."""
    if not RAGAS_AVAILABLE:
        return {"metric": "Context Precision (RAGAS)", "error": "ragas not installed", "score": None}
    from datasets import Dataset
    data = {
        "question": [query],
        "contexts": [contexts],
        "ground_truth": [ground_truth],
    }
    dataset = Dataset.from_dict(data)
    result = ragas_evaluate(dataset, metrics=[context_precision])
    score = result["context_precision"][0]
    return {
        "metric": "Context Precision (RAGAS)",
        "score": score,
        "query": query[:60],
        "ground_truth": ground_truth[:200],
    }

# ── Full suite ──

def run_full_evaluation(
    retrieve_fn: Callable,
    rag_query_fn: Callable,
    llm,
    recall_k: int = 3,
    latency_runs: int = 3,
) -> Dict[str, Any]:
    """Run all evaluations and return combined report."""
    return {
        "recall": evaluate_recall(retrieve_fn, k=recall_k),
        "faithfulness": evaluate_faithfulness(rag_query_fn, llm),
        "latency": evaluate_latency(rag_query_fn, num_runs=latency_runs),
    }


def run_ragas_evaluation(
    rag_query_fn: Callable,
    qa_pairs: List[Dict] = None,
    metrics: List[str] = None,
) -> Dict[str, Any]:
    """Run RAGAS evaluation on QA pairs."""
    if not RAGAS_AVAILABLE:
        return {"metric": "RAGAS", "error": "ragas not installed"}

    pairs = qa_pairs or TEST_QA_PAIRS
    metrics = metrics or ["faithfulness", "answer_relevancy", "context_precision"]

    all_results = {metric: [] for metric in metrics}
    details = []

    for qa in pairs:
        q = qa["question"]
        expected = qa["answer"]

        result: RAGQueryResponse = rag_query_fn(q)
        if not result.sources:
            continue

        contexts = [s.chunk for s in result.sources]
        answer = result.answer

        # Evaluate each metric
        for metric in metrics:
            if metric == "faithfulness":
                eval_result = evaluate_faithfulness_ragas(q, answer, contexts)
            elif metric == "answer_relevancy":
                eval_result = evaluate_answer_relevance_ragas(q, answer, contexts)
            elif metric == "context_precision":
                eval_result = evaluate_context_precision_ragas(q, contexts, expected)
            else:
                continue

            if eval_result.get("score") is not None:
                all_results[metric].append(eval_result["score"])

        details.append({
            "question": q[:60],
            "answer": answer[:200],
            "num_sources": len(contexts),
        })

    # Calculate averages
    avg_results = {}
    for metric, scores in all_results.items():
        avg = statistics.mean(scores) if scores else 0.0
        avg_results[metric] = {
            "average_score": round(avg, 4),
            "num_samples": len(scores),
        }

    return {
        "metric": "RAGAS",
        "metrics": avg_results,
        "details": details[:5],  # Limit details for brevity
    }
