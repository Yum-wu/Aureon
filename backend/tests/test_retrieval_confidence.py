"""Tests for CRAG retrieval confidence gating."""
from app.rag.retrieval_confidence import (
    evaluate_retrieval_confidence,
    build_answer_with_confidence,
)


class TestEvaluateRetrievalConfidence:
    def test_empty_chunks_returns_incorrect(self):
        assert evaluate_retrieval_confidence([]) == "incorrect"

    def test_high_score_returns_correct(self):
        chunks = [{"score": 0.10, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "correct"

    def test_medium_score_returns_ambiguous(self):
        chunks = [{"score": 0.03, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "ambiguous"

    def test_low_score_returns_incorrect(self):
        chunks = [{"score": 0.005, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "incorrect"

    def test_boundary_high_confidence(self):
        chunks = [{"score": 0.05, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "correct"

    def test_boundary_low_confidence(self):
        chunks = [{"score": 0.01, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "ambiguous"


class TestBuildAnswerWithConfidence:
    def test_correct_returns_original(self):
        assert build_answer_with_confidence("answer text", "correct", "en") == "answer text"

    def test_ambiguous_prepends_warning_en(self):
        result = build_answer_with_confidence("answer text", "ambiguous", "en")
        assert "limited" in result.lower()
        assert "answer text" in result

    def test_ambiguous_prepends_warning_zh(self):
        result = build_answer_with_confidence("答案内容", "ambiguous", "zh")
        assert "不完整" in result
        assert "答案内容" in result

    def test_incorrect_returns_fallback_en(self):
        result = build_answer_with_confidence("answer text", "incorrect", "en")
        assert "not find" in result.lower() or "no relevant" in result.lower()

    def test_incorrect_returns_fallback_zh(self):
        result = build_answer_with_confidence("答案内容", "incorrect", "zh")
        assert "没有找到" in result or "暂无相关" in result
