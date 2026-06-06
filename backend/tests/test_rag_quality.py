"""CI Quality Gate — RAG evaluation for pull requests.

Runs core regression set (27 QA) with DeepEval metrics.
Fails if any critical metric drops below threshold.

Usage:
    cd backend && python -m pytest tests/test_rag_quality.py -v --timeout=300
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Quality thresholds — failing these blocks the merge
THRESHOLDS = {
    "context_precision": 0.70,
    "context_recall": 0.75,
    "faithfulness": 0.70,
    "hallucination_max": 0.20,
}

# Warning thresholds — these trigger warnings but don't block
WARNING_THRESHOLDS = {
    "answer_relevancy": 0.60,
    "context_relevancy": 0.65,
}


@pytest.fixture(scope="module")
def evaluation_results():
    """Run full evaluation once per test module."""
    from tests.test_data_golden import load_dataset, get_dataset_info
    from tests.deepeval_eval import build_test_cases, run_deepeval_metrics, _load_article_texts
    from app.rag.qa_chain import hybrid_retrieve, rag_query
    from app.agent.llm import create_llm

    dataset_name = "core_regression_27qa"
    qa_pairs = load_dataset(dataset_name)
    info = get_dataset_info(dataset_name)

    llm = create_llm()

    def rag_query_fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    article_texts = _load_article_texts()
    test_cases, used_qa_indices = build_test_cases(qa_pairs, hybrid_retrieve, rag_query_fn, article_texts)
    scores = run_deepeval_metrics(test_cases, qa_pairs=qa_pairs, used_qa_indices=used_qa_indices)
    scores["dataset_info"] = info

    return scores


class TestRAGQualityGate:
    """Quality gate tests — must pass for PR merge."""

    def test_context_precision(self, evaluation_results):
        """Context Precision >= 0.70"""
        score = evaluation_results.get("context_precision", 0)
        assert score >= THRESHOLDS["context_precision"], \
            f"Context Precision {score:.3f} < {THRESHOLDS['context_precision']}"

    def test_context_recall(self, evaluation_results):
        """Context Recall >= 0.75"""
        score = evaluation_results.get("context_recall", 0)
        assert score >= THRESHOLDS["context_recall"], \
            f"Context Recall {score:.3f} < {THRESHOLDS['context_recall']}"

    def test_faithfulness(self, evaluation_results):
        """Faithfulness >= 0.70"""
        score = evaluation_results.get("faithfulness", 0)
        assert score >= THRESHOLDS["faithfulness"], \
            f"Faithfulness {score:.3f} < {THRESHOLDS['faithfulness']}"

    def test_hallucination(self, evaluation_results):
        """Hallucination <= 0.20"""
        score = evaluation_results.get("hallucination", 0)
        assert score <= THRESHOLDS["hallucination_max"], \
            f"Hallucination {score:.3f} > {THRESHOLDS['hallucination_max']}"

    def test_answer_relevancy_warning(self, evaluation_results):
        """Answer Relevancy >= 0.60 (warning, not blocking)"""
        score = evaluation_results.get("answer_relevancy", 0)
        if score < WARNING_THRESHOLDS["answer_relevancy"]:
            pytest.warns(
                UserWarning,
                match=f"Answer Relevancy {score:.3f} below warning threshold"
            )

    def test_overall_pass_rate(self, evaluation_results):
        """At least 80% of critical metrics should pass"""
        pass_rate = evaluation_results.get("pass_rate", 0)
        assert pass_rate >= 0.8, \
            f"Pass rate {pass_rate:.0%} < 80%"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=300"])
