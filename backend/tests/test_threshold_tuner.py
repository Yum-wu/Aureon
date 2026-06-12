"""Tests for CRAG threshold auto-tuning via grid search."""
from app.rag.threshold_tuner import (
    ThresholdConfig,
    evaluate_thresholds,
    grid_search_thresholds,
)


class TestThresholdConfig:
    def test_default_values(self):
        cfg = ThresholdConfig()
        assert cfg.high == 0.05
        assert cfg.low == 0.01

    def test_custom_values(self):
        cfg = ThresholdConfig(high=0.10, low=0.02)
        assert cfg.high == 0.10


class TestEvaluateThresholds:
    def test_perfect_classification(self):
        positive_scores = [0.10, 0.08, 0.06]
        negative_scores = [0.005, 0.003, 0.001]
        cfg = ThresholdConfig(high=0.05, low=0.01)
        result = evaluate_thresholds(cfg, positive_scores, negative_scores)
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_partial_classification(self):
        positive_scores = [0.10, 0.03, 0.005]
        negative_scores = [0.001, 0.002]
        cfg = ThresholdConfig(high=0.05, low=0.01)
        result = evaluate_thresholds(cfg, positive_scores, negative_scores)
        assert 0 < result["f1"] < 1.0


class TestGridSearch:
    def test_returns_best_config(self):
        positive_scores = [0.10, 0.08, 0.06, 0.04, 0.02]
        negative_scores = [0.005, 0.003, 0.001]
        result = grid_search_thresholds(positive_scores, negative_scores)
        assert isinstance(result, ThresholdConfig)
        assert result.high > result.low
