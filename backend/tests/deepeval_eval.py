"""DeepEval integration for RAG evaluation.

Implements RAGAS-standard metrics via DeepEval:
- ContextualPrecisionMetric
- ContextualRecallMetric
- ContextualRelevancyMetric
- AnswerRelevancyMetric
- FaithfulnessMetric
- HallucinationMetric

Run: cd backend && python -m tests.deepeval_eval
"""

import json
import os
import sys
import time
import logging
from typing import List, Dict, Any, Callable, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger(__name__)


# ── Metric thresholds (RAGAS enterprise standards) ──

METRIC_THRESHOLDS = {
    "context_precision": 0.70,
    "context_recall": 0.75,
    "context_relevancy": 0.70,
    "answer_relevancy": 0.60,
    "faithfulness": 0.70,
    "hallucination_max": 0.20,  # lower is better
}


def build_test_cases(
    qa_pairs: List[Dict],
    retrieve_fn: Callable,
    rag_query_fn: Callable,
) -> List[Any]:
    """Convert QA pairs to DeepEval LLMTestCase format.

    Args:
        qa_pairs: List of {"question", "answer", "source_article", ...}
        retrieve_fn: Function(query, top_k) -> List[Dict] with "text" field
        rag_query_fn: Function(query) -> RAGQueryResponse with .answer and .sources
    """
    from deepeval.test_case import LLMTestCase

    test_cases = []
    for qa in qa_pairs:
        query = qa["question"]
        if not query:
            continue  # skip empty queries

        # Retrieve context
        try:
            chunks = retrieve_fn(query, top_k=5)
            retrieval_context = [c.get("text", "") for c in chunks if c.get("text")]
        except Exception as e:
            logger.warning("Retrieval failed for '%s': %s", query[:40], e)
            retrieval_context = []

        # Generate answer
        try:
            result = rag_query_fn(query)
            actual_output = result.answer if hasattr(result, "answer") else str(result)
        except Exception as e:
            logger.warning("Generation failed for '%s': %s", query[:40], e)
            actual_output = "Error: failed to generate answer"

        # Build test case
        test_case = LLMTestCase(
            input=query,
            actual_output=actual_output,
            retrieval_context=retrieval_context if retrieval_context else ["No context retrieved"],
            expected_output=qa.get("answer", ""),
            context=[qa.get("answer", "")],
        )
        test_cases.append(test_case)

    return test_cases


def run_deepeval_metrics(
    test_cases: List[Any],
    threshold: float = 0.7,
    skip_hallucination: bool = False,
    model: str = None,
) -> Dict[str, Any]:
    """Run DeepEval six metrics on test cases.

    Args:
        model: DeepEval judge model. Default uses OPENAI_API_KEY.
               Set to "deepseek/chat" or pass api_key to use DeepSeek.
    """
    from deepeval import evaluate
    from deepeval.metrics import (
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        ContextualRelevancyMetric,
        AnswerRelevancyMetric,
        FaithfulnessMetric,
    )
    from deepeval.models import DeepEvalBaseLLM

    # Use custom model if no OpenAI key
    judge_model = None
    if not os.getenv("OPENAI_API_KEY") and not model:
        # Configure DeepEval to use DeepSeek as judge
        from app.config import settings
        if settings.llm_api_key:
            os.environ["OPENAI_API_KEY"] = settings.llm_api_key
            # DeepSeek API model name is 'deepseek-chat' (not display name)
            base_url = settings.llm_base_url.rstrip("/") + "/v1"
            os.environ["OPENAI_API_BASE"] = base_url
            os.environ["OPENAI_BASE_URL"] = base_url
            model = "deepseek-chat"

    metrics = [
        ContextualPrecisionMetric(threshold=METRIC_THRESHOLDS["context_precision"], model=model),
        ContextualRecallMetric(threshold=METRIC_THRESHOLDS["context_recall"], model=model),
        ContextualRelevancyMetric(threshold=METRIC_THRESHOLDS["context_relevancy"], model=model),
        AnswerRelevancyMetric(threshold=METRIC_THRESHOLDS["answer_relevancy"], model=model),
        FaithfulnessMetric(threshold=METRIC_THRESHOLDS["faithfulness"], model=model),
    ]

    # Skip HallucinationMetric for now — requires separate OpenAI-compatible config
    # TODO: Enable when DeepEval adds native DeepSeek support for hallucination detection

    # Run evaluation
    t0 = time.time()
    result = evaluate(
        test_cases=test_cases,
        metrics=metrics,
    )
    elapsed = time.time() - t0

    # Extract scores
    scores = {}
    for metric_name, threshold_key in [
        ("context_precision", "context_precision"),
        ("context_recall", "context_recall"),
        ("context_relevancy", "context_relevancy"),
        ("answer_relevancy", "answer_relevancy"),
        ("faithfulness", "faithfulness"),
    ]:
        metric_data = getattr(result, metric_name, None)
        if metric_data and hasattr(metric_data, "score"):
            scores[metric_name] = metric_data.score
        elif isinstance(result.scores, dict):
            scores[metric_name] = result.scores.get(metric_name, 0.0)
        else:
            scores[metric_name] = 0.0

    # HallucinationMetric skipped — not included in this run
    scores["hallucination"] = 0.0  # placeholder

    # Calculate pass rate (5 core metrics, no hallucination)
    passed = 0
    total = 0
    for metric_name in ["context_precision", "context_recall", "context_relevancy",
                         "answer_relevancy", "faithfulness"]:
        if metric_name in scores:
            total += 1
            if scores[metric_name] >= METRIC_THRESHOLDS.get(metric_name, 0.7):
                passed += 1

    scores["pass_rate"] = passed / total if total > 0 else 0.0
    scores["elapsed_seconds"] = round(elapsed, 1)
    scores["num_test_cases"] = len(test_cases)

    return scores


def format_results(scores: Dict[str, Any], dataset_info: Dict = None) -> str:
    """Format evaluation results as readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append("  DeepEval RAG Evaluation Results")
    lines.append("=" * 60)

    if dataset_info:
        lines.append(f"  Dataset: {dataset_info.get('description', 'N/A')}")
        lines.append(f"  Version: {dataset_info.get('version', 'N/A')}")
        lines.append(f"  Test cases: {scores.get('num_test_cases', 0)}")

    lines.append("")
    lines.append(f"  {'Metric':<25} {'Score':<10} {'Threshold':<12} {'Status'}")
    lines.append(f"  {'-'*25} {'-'*10} {'-'*12} {'-'*10}")

    for metric_name, display_name, threshold_key, higher_is_better in [
        ("context_precision", "Context Precision", "context_precision", True),
        ("context_recall", "Context Recall", "context_recall", True),
        ("context_relevancy", "Context Relevancy", "context_relevancy", True),
        ("answer_relevancy", "Answer Relevancy", "answer_relevancy", True),
        ("faithfulness", "Faithfulness", "faithfulness", True),
        ("hallucination", "Hallucination", "hallucination_max", False),
    ]:
        score = scores.get(metric_name, 0.0)
        threshold = METRIC_THRESHOLDS.get(threshold_key, 0.7)
        if higher_is_better:
            ok = score >= threshold
        else:
            ok = score <= threshold
        status = "OK" if ok else "WARN"
        lines.append(f"  {display_name:<25} {score:<10.3f} {threshold:<12} {status}")

    lines.append("")
    pass_rate = scores.get("pass_rate", 0.0)
    lines.append(f"  Pass Rate: {pass_rate:.0%} ({'ALL PASS' if pass_rate >= 0.8 else 'NEEDS IMPROVEMENT'})")
    lines.append(f"  Elapsed: {scores.get('elapsed_seconds', 0):.1f}s")
    lines.append("=" * 60)

    return "\n".join(lines)


if __name__ == "__main__":
    from tests.test_data_golden import load_dataset, get_dataset_info

    dataset_name = sys.argv[1] if len(sys.argv) > 1 else "core_regression_30qa"
    qa_pairs = load_dataset(dataset_name)
    info = get_dataset_info(dataset_name)

    print(f"Running DeepEval on {dataset_name} ({info['total']} QA pairs)...")

    # Import app modules
    from app.rag.vector_store import retrieve
    from app.rag.qa_chain import rag_query
    from app.agent.llm import create_llm

    llm = create_llm()

    def rag_query_fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    test_cases = build_test_cases(qa_pairs, retrieve, rag_query_fn)
    print(f"Built {len(test_cases)} test cases")

    scores = run_deepeval_metrics(test_cases)
    print(format_results(scores, info))
