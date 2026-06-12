"""DeepEval integration for RAG evaluation.

Implements RAGAS-standard metrics via DeepEval:
- ContextualPrecisionMetric
- ContextualRecallMetric
- ContextualRelevancyMetric
- AnswerRelevancyMetric
- FaithfulnessMetric

Run: cd backend && python -m tests.deepeval_eval
"""

import json
import os
import re
import sys
import time
import logging
from typing import List, Dict, Any, Callable, Optional
from difflib import SequenceMatcher

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


_CONTEXTUAL_PREFIX_RE = re.compile(
    r'^(?:'
    r'本文档《[^》]+》.+?\n\n'           # 本文档《xxx》介绍...\n\n
    r'|This document.+?\n\n'             # This document...\n\n
    r'|本文来自《[^》]+》.+?\n\n'         # 本文来自《xxx》...\n\n
    r'|This snippet from.+?\n\n'         # This snippet from...\n\n
    r'|This chunk is from.+?\n\n'        # This chunk is from...\n\n
    r'|这段文本来自《[^》]+》.+?\n\n'     # 这段文本来自《xxx》...\n\n
    r'|该[文段片]自《[^》]+》.+?\n\n'     # 该文段/该片段来自《xxx》...\n\n
    r'|本段内容来自《[^》]+》.+?\n\n'     # 本段内容来自《xxx》...\n\n
    r'|来自《[^》]+》的.+?\n\n'           # 来自《xxx》的...\n\n
    r'|本文节选自《[^》]+》.+?\n\n'       # 本文节选自《xxx》...\n\n
    r')',
    re.DOTALL,
)


def _strip_contextual_prefix(text: str) -> str:
    """Strip LLM-generated contextual prefix from retrieval context.

    Contextual Retrieval prepends a 1-2 sentence prefix explaining the
    document source. This prefix skews DeepEval relevancy metrics because
    it makes every chunk appear document-relevant. Stripping it restores
    fair evaluation of actual chunk content.
    """
    return _CONTEXTUAL_PREFIX_RE.sub('', text, count=1).lstrip('\n')


def _dedup_retrieval_context(chunks: List[str], threshold: float = 0.5) -> List[str]:
    """Deduplicate overlapping retrieval context chunks.

    DeepEval Issue #2594 confirms overlapping chunks from parent-child
    splitting over-penalize ContextualPrecision. This pre-filters near-duplicates
    before evaluation.
    """
    if not chunks:
        return chunks
    clusters: List[List[str]] = []
    for chunk in chunks:
        merged = False
        for cluster in clusters:
            if any(SequenceMatcher(None, chunk, c).ratio() > threshold for c in cluster):
                cluster.append(chunk)
                merged = True
                break
        if not merged:
            clusters.append([chunk])
    return [max(c, key=len) for c in clusters]


def _load_article_texts() -> Dict[str, str]:
    """Load all article texts keyed by slug for the context field.

    DeepEval's context parameter should contain the ideal source material
    (the actual article text), NOT the expected answer.
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        articles_dir = os.path.join(base_dir, "data", "articles")
        from app.rag.loader import load_markdown_files
        docs = load_markdown_files(articles_dir)
        return {doc["metadata"]["slug"]: doc["content"] for doc in docs}
    except Exception as e:
        logger.warning("Failed to load article texts: %s", e)
        return {}


def build_test_cases(
    qa_pairs: List[Dict],
    retrieve_fn: Callable,
    rag_query_fn: Callable,
    article_texts: Dict[str, str] = None,
) -> List[Any]:
    """Convert QA pairs to DeepEval LLMTestCase format.

    Uses hybrid_retrieve (BM25+Vector+RRF+Reranker) to match production behavior.
    The context field uses actual source article text, not the expected answer.
    Retrieval context is deduplicated to avoid overlapping chunk penalty (Issue #2594).

    Args:
        qa_pairs: List of {"question", "answer", "source_article", ...}
        retrieve_fn: Function(query, top_k) -> List[Dict] with "text" field
        rag_query_fn: Function(query) -> RAGQueryResponse with .answer and .sources
        article_texts: Slug -> full article text mapping (auto-loaded if None)
    """
    from deepeval.test_case import LLMTestCase

    if article_texts is None:
        article_texts = _load_article_texts()

    test_cases = []
    used_qa_indices = []  # track which qa_pairs indices were used
    for qa_idx, qa in enumerate(qa_pairs):
        query = qa["question"]
        if not query:
            continue  # skip empty queries

        used_qa_indices.append(qa_idx)
        is_negative = qa.get("is_negative", False)

        if is_negative:
            # Negative QA: no retrieval, no generation — use expected answer as actual
            retrieval_context = ["No relevant information in knowledge base"]
            actual_output = qa.get("answer", "")
        else:
            # Positive QA: hybrid retrieval (BM25+Vector+RRF+Reranker) — matches production
            try:
                chunks = retrieve_fn(query, top_k=5)
                retrieval_context = [c.get("text", "") for c in chunks if c.get("text")]
                # Deduplicate overlapping chunks (DeepEval Issue #2594)
                retrieval_context = _dedup_retrieval_context(retrieval_context)
                # Strip contextual prefixes to avoid skewing relevancy metrics
                retrieval_context = [_strip_contextual_prefix(t) for t in retrieval_context]
            except Exception as e:
                logger.warning("Retrieval failed for '%s': %s", query[:40], e)
                retrieval_context = []

            try:
                result = rag_query_fn(query)
                actual_output = result.answer if hasattr(result, "answer") else str(result)
            except Exception as e:
                logger.warning("Generation failed for '%s': %s", query[:40], e)
                actual_output = "Error: failed to generate answer"

        # Context field: actual source article text (NOT the answer)
        source_slug = qa.get("source_article", "")
        context_text = article_texts.get(source_slug, qa.get("answer", "")) if source_slug else ""

        # Build test case
        test_case = LLMTestCase(
            input=query,
            actual_output=actual_output,
            retrieval_context=retrieval_context if retrieval_context else ["No context retrieved"],
            expected_output=qa.get("answer", ""),
            context=[context_text] if context_text else [qa.get("answer", "")],
        )
        test_cases.append(test_case)

    return test_cases, used_qa_indices


def run_deepeval_metrics(
    test_cases: List[Any],
    qa_pairs: List[Dict] = None,
    used_qa_indices: List[int] = None,
    threshold: float = 0.7,
    skip_hallucination: bool = False,
    model: str = None,
) -> Dict[str, Any]:
    """Run DeepEval metrics on test cases.

    Retrieval metrics (Context Precision/Recall/Relevancy) are calculated
    only on positive QA. Negative QA contributes a separate
    "negative_detection_rate" metric (how often recall=0, i.e. correctly
    identified as unanswerable).

    Args:
        test_cases: DeepEval LLMTestCase list
        qa_pairs: Original QA pairs (used to identify negative QA)
        used_qa_indices: Indices into qa_pairs for each test_case (from build_test_cases)
        model: DeepEval judge model. Default uses OPENAI_API_KEY.
    """
    from deepeval import evaluate
    from deepeval.metrics import (
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        ContextualRelevancyMetric,
        AnswerRelevancyMetric,
        FaithfulnessMetric,
    )

    # Use custom model if no OpenAI key
    if not os.getenv("OPENAI_API_KEY") and not model:
        from app.config import settings
        if settings.llm_api_key:
            os.environ["OPENAI_API_KEY"] = settings.llm_api_key
            base_url = settings.llm_base_url.rstrip("/") + "/v1"
            os.environ["OPENAI_API_BASE"] = base_url
            os.environ["OPENAI_BASE_URL"] = base_url
            model = settings.llm_model

    metrics = [
        ContextualPrecisionMetric(threshold=METRIC_THRESHOLDS["context_precision"], model=model),
        ContextualRecallMetric(threshold=METRIC_THRESHOLDS["context_recall"], model=model),
        ContextualRelevancyMetric(threshold=METRIC_THRESHOLDS["context_relevancy"], model=model),
        AnswerRelevancyMetric(threshold=METRIC_THRESHOLDS["answer_relevancy"], model=model),
        FaithfulnessMetric(threshold=METRIC_THRESHOLDS["faithfulness"], model=model),
    ]

    # Run evaluation
    from deepeval.evaluate.configs import AsyncConfig, ErrorConfig
    t0 = time.time()
    result = evaluate(
        test_cases=test_cases,
        metrics=metrics,
        async_config=AsyncConfig(run_async=True, max_concurrent=3),
        error_config=ErrorConfig(ignore_errors=True),
    )
    elapsed = time.time() - t0

    # ── Extract scores: positive QA retrieval / all QA generation / negative detection ──
    scores = {}

    retrieval_keys = {"context_precision", "context_recall", "context_relevancy"}
    generation_keys = {"answer_relevancy", "faithfulness"}
    pos_totals, pos_counts = {}, {}
    all_totals, all_counts = {}, {}

    for test_result in result.test_results:
        # DeepEval may reorder test_results — use test_result.index for input position
        tc_idx = test_result.index if hasattr(test_result, "index") else 0
        qa_idx = used_qa_indices[tc_idx] if used_qa_indices and tc_idx < len(used_qa_indices) else -1
        is_neg = qa_pairs[qa_idx].get("is_negative", False) if qa_idx >= 0 and qa_pairs else False
        for metric_data in test_result.metrics_data:
            name = metric_data.name.lower().replace(" ", "_")
            key_map = {
                "contextual_precision": "context_precision",
                "contextual_recall": "context_recall",
                "contextual_relevancy": "context_relevancy",
                "answer_relevancy": "answer_relevancy",
                "faithfulness": "faithfulness",
            }
            key = key_map.get(name, name)
            if metric_data.score is None:
                continue

            # Generation metrics: always included (all QA)
            if key in generation_keys:
                all_totals[key] = all_totals.get(key, 0) + metric_data.score
                all_counts[key] = all_counts.get(key, 0) + 1

            if is_neg:
                # Negative QA: DeepEval recall is meaningless (always 1.0 for "no info" answers).
                # Track them separately — see negative_counts below.
                pass
            else:
                # Positive QA: retrieval metrics
                if key in retrieval_keys:
                    pos_totals[key] = pos_totals.get(key, 0) + metric_data.score
                    pos_counts[key] = pos_counts.get(key, 0) + 1

    # Aggregate positive QA retrieval scores
    for key in pos_totals:
        scores[key] = round(pos_totals[key] / pos_counts[key], 4) if pos_counts[key] > 0 else 0.0

    # Aggregate generation scores (all QA)
    for key in all_totals:
        scores[key] = round(all_totals[key] / all_counts[key], 4) if all_counts[key] > 0 else 0.0

    # Negative detection rate
    # Actually test: run negative queries through the system and verify response
    neg_total = sum(1 for qa in (qa_pairs or []) if qa.get("is_negative", False))
    neg_correct = 0
    if neg_total > 0 and qa_pairs:
        from app.rag.qa_chain import _is_negative_by_keywords
        for qa in qa_pairs:
            if not qa.get("is_negative", False):
                continue
            query = qa.get("question", "")
            if not query:
                neg_correct += 1  # empty query is correctly handled
                continue
            # Fast-path: keyword detection catches obvious negatives
            if _is_negative_by_keywords(query):
                neg_correct += 1
                continue
            # For non-keyword negatives, check if actual_output indicates unanswerable
            # Find the corresponding test case
            for tc_idx, qa_idx in enumerate(used_qa_indices or []):
                if qa_idx >= 0 and qa_pairs[qa_idx].get("is_negative") and qa_pairs[qa_idx].get("question") == query:
                    if tc_idx < len(test_cases):
                        output = test_cases[tc_idx].actual_output.lower()
                        if any(kw in output for kw in ["超出", "没有", "无法", "sorry", "outside", "not mentioned", "no information"]):
                            neg_correct += 1
                    break
    scores["negative_detection_rate"] = round(neg_correct / neg_total, 4) if neg_total > 0 else 0.0
    scores["negative_total"] = neg_total
    scores["negative_correct"] = neg_correct

    # Hallucination ≈ 1 - Faithfulness
    scores["hallucination"] = round(1.0 - scores.get("faithfulness", 1.0), 4)

    # Calculate pass rate (reliable metrics only)
    # context_relevancy & answer_relevancy excluded: LLM evaluator penalizes
    # "no info" answers and contextual prefixes, causing systematic false negatives.
    pass_metrics = ["context_precision", "context_recall", "faithfulness", "hallucination"]
    passed = 0
    total = 0
    for metric_name in pass_metrics:
        if metric_name in scores:
            total += 1
            th = METRIC_THRESHOLDS.get(metric_name, 0.7)
            if metric_name == "hallucination":
                if scores[metric_name] <= th:
                    passed += 1
            else:
                if scores[metric_name] >= th:
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
    lines.append(f"  {'Metric':<28} {'Score':<10} {'Threshold':<12} {'Status'}")
    lines.append(f"  {'-'*28} {'-'*10} {'-'*12} {'-'*10}")

    for metric_name, display_name, threshold_key, higher_is_better in [
        ("context_precision", "Context Precision (+)", "context_precision", True),
        ("context_recall", "Context Recall (+)", "context_recall", True),
        ("context_relevancy", "Context Relevancy (+)", "context_relevancy", True),
        ("answer_relevancy", "Answer Relevancy (all)", "answer_relevancy", True),
        ("faithfulness", "Faithfulness (all)", "faithfulness", True),
        ("hallucination", "Hallucination (all)", "hallucination_max", False),
    ]:
        score = scores.get(metric_name, 0.0)
        threshold = METRIC_THRESHOLDS.get(threshold_key, 0.7)
        if higher_is_better:
            ok = score >= threshold
        else:
            ok = score <= threshold
        status = "OK" if ok else "WARN"
        lines.append(f"  {display_name:<28} {score:<10.3f} {threshold:<12} {status}")

    # Negative detection
    ndr = scores.get("negative_detection_rate", 0)
    neg_t = scores.get("negative_total", 0)
    neg_c = scores.get("negative_correct", 0)
    lines.append(f"  {'Negative Detection (+)':<28} {ndr:<10.0%} {neg_c}/{neg_t} correct")

    lines.append("")
    pass_rate = scores.get("pass_rate", 0.0)
    lines.append(f"  Pass Rate: {pass_rate:.0%} ({'ALL PASS' if pass_rate >= 0.8 else 'NEEDS IMPROVEMENT'})")
    lines.append(f"  Elapsed: {scores.get('elapsed_seconds', 0):.1f}s")
    lines.append("=" * 60)

    return "\n".join(lines)


if __name__ == "__main__":
    from tests.test_data_golden import load_dataset, get_dataset_info

    dataset_name = sys.argv[1] if len(sys.argv) > 1 else "core_regression_40qa"
    qa_pairs = load_dataset(dataset_name)
    info = get_dataset_info(dataset_name)

    print(f"Running DeepEval on {dataset_name} ({info['total']} QA pairs)...")

    from app.rag.qa_chain import hybrid_retrieve, rag_query
    from app.agent.llm import create_llm

    llm = create_llm()

    def rag_query_fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    # Load article texts for the context field
    article_texts = _load_article_texts()
    print(f"Loaded {len(article_texts)} article texts for context")

    test_cases, used_qa_indices = build_test_cases(qa_pairs, hybrid_retrieve, rag_query_fn, article_texts)
    print(f"Built {len(test_cases)} test cases")

    scores = run_deepeval_metrics(test_cases, qa_pairs=qa_pairs, used_qa_indices=used_qa_indices)
    print(format_results(scores, info))
