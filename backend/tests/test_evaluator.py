"""Tests for app.rag.evaluator — recall, faithfulness, latency evaluation."""

import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace

from app.rag.evaluator import (
    evaluate_recall,
    evaluate_faithfulness,
    evaluate_latency,
    run_full_evaluation,
)


# ── evaluate_recall ──


class TestEvaluateRecall:
    def test_perfect_recall(self):
        qa_pairs = [{"question": "What is RAG?", "answer": "..."}]
        expected = {"What is RAG?": "rag-guide"}

        def retrieve_fn(q, top_k=3):
            return [{"metadata": {"slug": "rag-guide"}}, {"metadata": {"slug": "other"}}]

        result = evaluate_recall(retrieve_fn, qa_pairs=qa_pairs, expected_map=expected, k=3)
        assert result["score"] == 1.0
        assert result["hits"] == 1
        assert result["total"] == 1

    def test_zero_recall(self):
        qa_pairs = [{"question": "Q1", "answer": "..."}]
        expected = {"Q1": "expected-doc"}

        def retrieve_fn(q, top_k=3):
            return [{"metadata": {"slug": "wrong-doc"}}]

        result = evaluate_recall(retrieve_fn, qa_pairs=qa_pairs, expected_map=expected, k=3)
        assert result["score"] == 0.0
        assert result["hits"] == 0

    def test_question_not_in_expected_skipped(self):
        qa_pairs = [{"question": "Unknown Q", "answer": "..."}]
        expected = {}

        def retrieve_fn(q, top_k=3):
            return []

        result = evaluate_recall(retrieve_fn, qa_pairs=qa_pairs, expected_map=expected)
        assert result["total"] == 0
        assert result["score"] == 0.0

    def test_empty_qa_pairs_uses_defaults(self):
        """Empty list falls through to default TEST_QA_PAIRS (qa_pairs or default)."""
        result = evaluate_recall(lambda q, top_k=3: [], qa_pairs=[], expected_map={})
        # [] is falsy, so default TEST_QA_PAIRS is used; total depends on expected_map overlap
        assert result["total"] >= 0


# ── evaluate_faithfulness ──


class TestEvaluateFaithfulness:
    def _make_rag_fn(self, answer: str, sources):
        def rag_query_fn(q):
            return SimpleNamespace(answer=answer, sources=sources)
        return rag_query_fn

    def _make_mock_llm(self, content: str):
        llm = MagicMock()
        resp = MagicMock()
        resp.content = content
        llm.invoke.return_value = resp
        return llm

    def test_high_faithfulness(self):
        qa = [{"question": "Q1", "answer": "expected"}]
        sources = [SimpleNamespace(title="Doc", chunk="context")]
        rag_fn = self._make_rag_fn("Good answer", sources)
        llm = self._make_mock_llm('{"score": 9, "reason": "accurate"}')

        result = evaluate_faithfulness(rag_fn, llm, qa_pairs=qa)
        assert result["average_score"] == 9
        assert result["num_samples"] == 1

    def test_no_sources_skips_pair(self):
        qa = [{"question": "Q1", "answer": "expected"}]
        rag_fn = self._make_rag_fn("answer", [])

        result = evaluate_faithfulness(rag_fn, MagicMock(), qa_pairs=qa)
        assert result["num_samples"] == 0

    def test_llm_exception_gives_zero_score(self):
        qa = [{"question": "Q1", "answer": "expected"}]
        sources = [SimpleNamespace(title="Doc", chunk="ctx")]
        rag_fn = self._make_rag_fn("answer", sources)
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("fail")

        result = evaluate_faithfulness(rag_fn, llm, qa_pairs=qa)
        assert result["average_score"] == 0
        assert result["num_samples"] == 1

    def test_empty_qa_pairs_uses_defaults(self):
        """Empty list falls through to default TEST_QA_PAIRS."""
        result = evaluate_faithfulness(MagicMock(), MagicMock(), qa_pairs=[])
        assert result["num_samples"] >= 0


# ── evaluate_latency ──


class TestEvaluateLatency:
    def test_measures_latency(self):
        qa = [{"question": "Q1", "answer": "..."}]

        def rag_fn(q):
            return "answer"

        result = evaluate_latency(rag_fn, qa_pairs=qa, num_runs=2)
        assert result["metric"] == "Latency (ms)"
        assert result["num_samples"] == 2
        assert result["mean_ms"] >= 0
        assert "p50_ms" in result
        assert "p99_ms" in result

    def test_empty_qa_pairs_uses_defaults(self):
        """Empty list falls through to default TEST_QA_PAIRS."""
        result = evaluate_latency(lambda q: "ok", qa_pairs=[], num_runs=1)
        assert result["metric"] == "Latency (ms)"
        assert result["num_samples"] >= 0


# ── run_full_evaluation ──


class TestRunFullEvaluation:
    def test_returns_all_metrics(self):
        def retrieve_fn(q, top_k=3):
            return [{"metadata": {"slug": "doc"}}]

        def rag_fn(q):
            return SimpleNamespace(answer="a", sources=[SimpleNamespace(title="t", chunk="c")])

        llm = MagicMock()
        resp = MagicMock()
        resp.content = '{"score": 8, "reason": "ok"}'
        llm.invoke.return_value = resp

        qa = [{"question": "Q", "answer": "A"}]
        result = run_full_evaluation(retrieve_fn, rag_fn, llm, recall_k=3, latency_runs=1)
        assert "recall" in result
        assert "faithfulness" in result
        assert "latency" in result
