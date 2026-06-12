"""Tests for app.rag.ensemble_reranker — ensemble reranking with weighted voting."""

import pytest
import asyncio
import numpy as np
from unittest.mock import patch, MagicMock

from app.rag.ensemble_reranker import (
    EnsembleReranker,
    RerankerConfig,
    create_default_ensemble,
)


class TestRerankerConfig:
    """Test RerankerConfig dataclass."""

    def test_default_config(self):
        config = RerankerConfig(name="test")
        assert config.name == "test"
        assert config.weight == 1.0
        assert config.enabled is True
        assert config.model_name is None

    def test_custom_config(self):
        config = RerankerConfig(
            name="bge-v2-m3",
            weight=0.6,
            enabled=True,
            model_name="BAAI/bge-reranker-v2-m3",
            device="cuda",
            use_fp16=True,
        )
        assert config.name == "bge-v2-m3"
        assert config.weight == 0.6
        assert config.device == "cuda"
        assert config.use_fp16 is True


class TestEnsembleRerankerInit:
    """Test EnsembleReranker initialization."""

    def test_default_initialization(self):
        reranker = EnsembleReranker()
        assert reranker is not None
        assert len(reranker.configs) == 3  # Default configs
        assert len(reranker._enabled_configs) >= 1  # At least BGE enabled

    def test_custom_initialization(self):
        config = RerankerConfig(name="bge-v2-m3", weight=1.0, enabled=True)
        reranker = EnsembleReranker(configs=[config])
        assert len(reranker.configs) == 1
        assert len(reranker._enabled_configs) == 1

    def test_single_reranker(self):
        config = RerankerConfig(
            name="bge-v2-m3",
            weight=1.0,
            enabled=True,
            model_name="BAAI/bge-reranker-v2-m3",
        )
        reranker = EnsembleReranker(configs=[config])
        assert reranker is not None
        assert len(reranker._enabled_configs) == 1

    def test_no_enabled_configs(self):
        config = RerankerConfig(name="disabled", enabled=False)
        reranker = EnsembleReranker(configs=[config])
        assert len(reranker._enabled_configs) == 0


class TestScoreNormalization:
    """Test score normalization methods."""

    def setup_method(self):
        self.reranker = EnsembleReranker(configs=[])

    def test_normalize_single_value(self):
        scores = np.array([0.75], dtype=np.float32)
        normalized = self.reranker._normalize_scores(scores)
        assert len(normalized) == 1
        assert normalized[0] == 1.0  # Single value normalizes to 1.0

    def test_normalize_identical_scores(self):
        scores = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        normalized = self.reranker._normalize_scores(scores)
        assert all(s == 0.5 for s in normalized)  # All equal -> 0.5

    def test_normalize_min_max(self):
        scores = np.array([0.2, 0.5, 0.8], dtype=np.float32)
        normalized = self.reranker._normalize_scores(scores)
        assert normalized[0] == 0.0  # Min -> 0.0
        assert normalized[1] == pytest.approx(0.5, abs=1e-5)  # Mid -> 0.5
        assert normalized[2] == 1.0  # Max -> 1.0

    def test_normalize_preserves_order(self):
        scores = np.array([0.1, 0.9, 0.5], dtype=np.float32)
        normalized = self.reranker._normalize_scores(scores)
        assert normalized[0] < normalized[1]
        assert normalized[0] < normalized[2]
        assert normalized[1] > normalized[2]


class TestScoreCombination:
    """Test weighted score combination."""

    def setup_method(self):
        self.reranker = EnsembleReranker(configs=[])

    def test_single_model_combination(self):
        documents = [{"text": "doc1"}, {"text": "doc2"}]
        scores_bge = np.array([0.9, 0.7], dtype=np.float32)
        all_scores = [("bge-v2-m3", 1.0, scores_bge)]

        ensemble_scores = self.reranker._combine_scores(documents, all_scores)

        assert len(ensemble_scores) == 2
        assert ensemble_scores[0] > ensemble_scores[1]  # 0.9 > 0.7

    def test_multi_model_combination(self):
        documents = [{"text": "doc1"}, {"text": "doc2"}, {"text": "doc3"}]
        scores_bge = np.array([0.9, 0.7, 0.5], dtype=np.float32)
        scores_cohere = np.array([0.85, 0.75, 0.6], dtype=np.float32)

        all_scores = [
            ("bge-v2-m3", 0.6, scores_bge),
            ("cohere", 0.4, scores_cohere),
        ]

        ensemble_scores = self.reranker._combine_scores(documents, all_scores)

        assert len(ensemble_scores) == 3
        # Ensemble should prefer doc1 (highest in both models)
        assert ensemble_scores[0] > ensemble_scores[2]

    def test_weighted_voting_effect(self):
        """Test that higher weights have more influence."""
        documents = [{"text": "doc1"}, {"text": "doc2"}]
        scores_a = np.array([1.0, 0.0], dtype=np.float32)  # Model A prefers doc1
        scores_b = np.array([0.0, 1.0], dtype=np.float32)  # Model B prefers doc2

        # Model A has higher weight -> doc1 should rank higher
        all_scores_weighted = [
            ("a", 0.9, scores_a),
            ("b", 0.1, scores_b),
        ]
        ensemble_weighted = self.reranker._combine_scores(documents, all_scores_weighted)

        # Model A has lower weight -> doc2 should rank higher
        all_scores_unweighted = [
            ("a", 0.1, scores_a),
            ("b", 0.9, scores_b),
        ]
        ensemble_unweighted = self.reranker._combine_scores(documents, all_scores_unweighted)

        assert ensemble_weighted[0] > ensemble_unweighted[0]  # Doc1 more favored with high weight
        assert ensemble_weighted[1] < ensemble_unweighted[1]  # Doc2 less favored with low weight

    def test_empty_score_list(self):
        documents = [{"text": "doc1"}]
        ensemble_scores = self.reranker._combine_scores(documents, [])
        assert len(ensemble_scores) == 1
        assert ensemble_scores[0] == 0.0

    def test_score_count_mismatch_handling(self):
        """Test graceful handling when scores count doesn't match documents."""
        documents = [{"text": "doc1"}, {"text": "doc2"}]
        scores_wrong = np.array([0.9, 0.7, 0.5], dtype=np.float32)  # 3 scores for 2 docs
        all_scores = [("bge", 1.0, scores_wrong)]

        # Should handle gracefully (skip mismatched model)
        ensemble_scores = self.reranker._combine_scores(documents, all_scores)
        assert len(ensemble_scores) == 2


class TestRerank:
    """Test the main rerank method."""

    def test_rerank_empty_documents(self):
        reranker = EnsembleReranker(configs=[])
        result = asyncio.run(reranker.rerank("test", [], top_k=5))
        assert result == []

    def test_rerank_single_document(self):
        reranker = EnsembleReranker(configs=[])
        docs = [{"text": "single doc"}]
        result = asyncio.run(reranker.rerank("test", docs, top_k=5))
        assert len(result) == 1
        assert result[0]["ensemble_score"] == 1.0

    @patch.object(EnsembleReranker, '_rerank_single', return_value=np.array([0.9, 0.7, 0.5]))
    def test_rerank_with_mock_scores(self, mock_rerank):
        config = RerankerConfig(name="mock", weight=1.0, enabled=True)
        reranker = EnsembleReranker(configs=[config])

        # Mock _get_reranker to return a dummy
        reranker._get_reranker = MagicMock(return_value=("mock", {}))

        docs = [{"text": "doc1"}, {"text": "doc2"}, {"text": "doc3"}]
        result = asyncio.run(reranker.rerank("test", docs, top_k=2))

        assert len(result) == 2
        assert result[0]["ensemble_score"] >= result[1]["ensemble_score"]

    def test_rerank_top_k_limits_output(self):
        config = RerankerConfig(name="bge", weight=1.0, enabled=False)
        reranker = EnsembleReranker(configs=[config])

        docs = [{"text": f"doc{i}"} for i in range(10)]
        result = asyncio.run(reranker.rerank("test", docs, top_k=3))
        assert len(result) == 3

    def test_stats_tracking(self):
        config = RerankerConfig(name="bge", weight=1.0, enabled=False)
        reranker = EnsembleReranker(configs=[config])

        asyncio.run(reranker.rerank("test1", [{"text": "doc"}]))
        asyncio.run(reranker.rerank("test2", [{"text": "doc"}]))

        stats = reranker.get_stats()
        assert stats["total_queries"] == 2


class TestModelLoading:
    """Test lazy model loading."""

    def test_get_reranker_bge(self):
        config = RerankerConfig(
            name="bge-v2-m3",
            model_name="BAAI/bge-reranker-v2-m3",
        )
        reranker = EnsembleReranker(configs=[config])

        # Should try to load BGE reranker
        result = reranker._get_reranker(config)
        # Result is tuple (type, config) or None
        assert result is None or isinstance(result, tuple)

    def test_get_reranker_cohere_without_key(self):
        config = RerankerConfig(name="cohere", api_key=None)
        reranker = EnsembleReranker(configs=[config])

        # Should fail gracefully without API key
        result = reranker._get_reranker(config)
        assert result is None

    def test_caching_loaded_models(self):
        config = RerankerConfig(
            name="bge-v2-m3",
            model_name="BAAI/bge-reranker-v2-m3",
        )
        reranker = EnsembleReranker(configs=[config])

        # Mock the loading
        with patch.object(reranker, '_load_bge_reranker', return_value=("mock", {})):
            result1 = reranker._get_reranker(config)
            result2 = reranker._get_reranker(config)

            # Should return cached instance
            assert result1 is result2


class TestScoreNormalizationIntegration:
    """Test score normalization with actual reranker output."""

    def test_different_score_ranges(self):
        """Test normalization handles different score ranges from different models."""
        reranker = EnsembleReranker(configs=[])

        # Model 1: scores in [0, 1]
        scores_1 = np.array([0.1, 0.5, 0.9], dtype=np.float32)
        normalized_1 = reranker._normalize_scores(scores_1)

        # Model 2: scores in [-5, 5]
        scores_2 = np.array([-4.0, 0.0, 4.0], dtype=np.float32)
        normalized_2 = reranker._normalize_scores(scores_2)

        # After normalization, both should be in [0, 1]
        assert all(0 <= s <= 1 for s in normalized_1)
        assert all(0 <= s <= 1 for s in normalized_2)

        # Order should be preserved
        assert normalized_1[0] < normalized_1[1] < normalized_1[2]
        assert normalized_2[0] < normalized_2[1] < normalized_2[2]


class TestEnsembleRerankerStats:
    """Test statistics tracking."""

    def test_initial_stats(self):
        reranker = EnsembleReranker(configs=[])
        stats = reranker.get_stats()
        assert stats["total_queries"] == 0
        assert stats["avg_latency_ms"] == 0.0
        assert stats["total_latency_ms"] == 0.0
        assert stats["models_used"] == {}

    def test_stats_after_queries(self):
        reranker = EnsembleReranker(configs=[])
        asyncio.run(reranker.rerank("test", [{"text": "doc"}]))
        asyncio.run(reranker.rerank("test2", [{"text": "doc"}]))

        stats = reranker.get_stats()
        assert stats["total_queries"] == 2
        assert stats["total_latency_ms"] >= 0
        assert stats["avg_latency_ms"] >= 0

    def test_reset_stats(self):
        reranker = EnsembleReranker(configs=[])
        asyncio.run(reranker.rerank("test", [{"text": "doc"}]))

        reranker.reset_stats()
        stats = reranker.get_stats()
        assert stats["total_queries"] == 0


class TestCreateDefaultEnsemble:
    """Test factory function."""

    def test_creates_ensemble_with_bge(self):
        reranker = create_default_ensemble()
        assert reranker is not None
        assert len(reranker.configs) >= 1
        # BGE should be enabled
        bge_configs = [c for c in reranker.configs if c.name.startswith("bge")]
        assert len(bge_configs) == 1
        assert bge_configs[0].enabled is True

    def test_cohere_enabled_with_key(self):
        # Patch app.config.settings so create_default_ensemble's
        # local import always sees the patched value, even after
        # importlib.reload in other test modules.
        with patch("app.config.settings") as mock_settings:
            mock_settings.cohere_api_key = "test-key"
            mock_settings.jina_api_key = None
            mock_settings.ensemble_bge_weight = 0.6
            mock_settings.ensemble_cohere_weight = 0.3
            mock_settings.ensemble_jina_weight = 0.1
            mock_settings.cohere_rerank_model = "rerank-multilingual-v3.0"
            reranker = create_default_ensemble()
            cohere_configs = [c for c in reranker.configs if c.name == "cohere"]
            assert len(cohere_configs) == 1
            assert cohere_configs[0].enabled is True

    def test_jina_enabled_with_key(self):
        with patch("app.config.settings") as mock_settings:
            mock_settings.cohere_api_key = None
            mock_settings.jina_api_key = "test-key"
            mock_settings.ensemble_bge_weight = 0.6
            mock_settings.ensemble_cohere_weight = 0.3
            mock_settings.ensemble_jina_weight = 0.1
            mock_settings.cohere_rerank_model = "rerank-multilingual-v3.0"
            reranker = create_default_ensemble()
            jina_configs = [c for c in reranker.configs if c.name == "jina"]
            assert len(jina_configs) == 1
            assert jina_configs[0].enabled is True


class TestErrorHandling:
    """Test error handling and graceful fallback."""

    def test_rerank_failure_fallback(self):
        """Test graceful fallback when reranker fails."""
        config = RerankerConfig(name="failing", weight=1.0, enabled=True)
        reranker = EnsembleReranker(configs=[config])

        # Mock _get_reranker to return None (simulating failure)
        reranker._get_reranker = MagicMock(return_value=None)

        docs = [{"text": "doc1"}, {"text": "doc2"}]
        result = asyncio.run(reranker.rerank("test", docs, top_k=2))

        # Should return original documents with default scores
        assert len(result) == 2
        assert all("ensemble_score" in doc for doc in result)

    def test_invalid_score_array(self):
        """Test handling of invalid score arrays."""
        reranker = EnsembleReranker(configs=[])
        documents = [{"text": "doc1"}]

        # Test with empty score array
        all_scores = [("bge", 1.0, np.array([], dtype=np.float32))]
        ensemble_scores = reranker._combine_scores(documents, all_scores)
        assert len(ensemble_scores) == 1


class TestEnsembleIntegration:
    """Integration tests for ensemble reranking."""

    def test_end_to_end_single_model(self):
        """Test complete reranking with single model."""
        config = RerankerConfig(name="bge", weight=1.0, enabled=True)
        reranker = EnsembleReranker(configs=[config])

        # Mock the rerank_single method
        with patch.object(
            reranker,
            '_rerank_single',
            return_value=np.array([0.8, 0.6, 0.9, 0.7], dtype=np.float32),
        ):
            # Mock _get_reranker to return a dummy
            reranker._get_reranker = MagicMock(return_value=("mock", {}))

            docs = [
                {"text": "doc1"},
                {"text": "doc2"},
                {"text": "doc3"},
                {"text": "doc4"},
            ]

            result = asyncio.run(reranker.rerank("test query", docs, top_k=3))

            assert len(result) == 3
            # doc3 should be first (highest score 0.9)
            assert result[0]["text"] == "doc3"

    def test_end_to_end_multi_model(self):
        """Test complete reranking with multiple models."""
        configs = [
            RerankerConfig(name="bge", weight=0.6, enabled=True),
            RerankerConfig(name="cohere", weight=0.4, enabled=True),
        ]
        reranker = EnsembleReranker(configs=configs)

        docs = [{"text": "doc1"}, {"text": "doc2"}]

        # Mock both models
        reranker._get_reranker = MagicMock(return_value=("mock", {}))

        with patch.object(reranker, '_rerank_single') as mock_rerank:
            # Model A (bge) scores
            mock_rerank.side_effect = [
                np.array([0.9, 0.7], dtype=np.float32),  # bge
                np.array([0.8, 0.8], dtype=np.float32),  # cohere
            ]

            result = asyncio.run(reranker.rerank("test", docs, top_k=2))

            assert len(result) == 2
            assert mock_rerank.call_count == 2


# Import os for environment variable tests
