# -*- coding: utf-8 -*-
"""Tests for GPU-accelerated embedding.

Uses mocks to avoid model downloads on CI. Real model tests are in
test_embed_gpu_integration.py (run locally with GPU).
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


class TestGPUEmbeddingUnit:
    """Unit tests for GPUEmbedder (no model loading)."""

    def test_fp16_disabled_on_cpu(self):
        """GPUEmbedder with device='cpu' should disable fp16."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(device="cpu", use_fp16=True)
        assert embedder.use_fp16 is False

    def test_fp16_enabled_on_cuda(self):
        """GPUEmbedder with device='cuda' and use_fp16=True should enable fp16."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(device="cuda", use_fp16=True)
        assert embedder.use_fp16 is True

    def test_empty_encode_returns_empty_array(self):
        """Encode with empty list returns empty array."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(device="cpu")
        result = embedder.encode([])
        assert result.shape[0] == 0

    def test_singleton_embedder(self):
        """get_gpu_embedder returns same instance."""
        from app.rag.embed_gpu import get_gpu_embedder, _embedder_instance
        # Reset singleton for test
        import app.rag.embed_gpu as mod
        mod._embedder_instance = None
        e1 = get_gpu_embedder(device="cpu")
        e2 = get_gpu_embedder(device="cpu")
        assert e1 is e2

    def test_singleton_reranker(self):
        """get_gpu_reranker returns same instance."""
        from app.rag.embed_gpu import get_gpu_reranker
        import app.rag.embed_gpu as mod
        mod._reranker_instance = None
        r1 = get_gpu_reranker(device="cpu")
        r2 = get_gpu_reranker(device="cpu")
        assert r1 is r2


class TestGPURerankerUnit:
    """Unit tests for GPUReranker (no model loading)."""

    def test_fp16_disabled_on_cpu(self):
        """GPUReranker with device='cpu' should disable fp16."""
        from app.rag.embed_gpu import GPUReranker
        reranker = GPUReranker(device="cpu", use_fp16=True)
        assert reranker.use_fp16 is False

    def test_rerank_empty_returns_empty(self):
        """Rerank with empty chunks returns empty list."""
        from app.rag.embed_gpu import GPUReranker
        reranker = GPUReranker(device="cpu")
        result = reranker.rerank("test", [])
        assert result == []

    def test_rerank_single_chunk_returns_with_score(self):
        """Rerank with single chunk returns with score 1.0."""
        from app.rag.embed_gpu import GPUReranker
        reranker = GPUReranker(device="cpu")
        result = reranker.rerank("test", [{"text": "hello"}])
        assert len(result) == 1
        assert result[0]["rerank_score"] == 1.0


class TestGPUConfig:
    """Test GPU configuration and detection."""

    def test_detect_best_attention_returns_string(self):
        """_detect_best_attention returns a string or None."""
        from app.rag.embed_gpu import _detect_best_attention
        result = _detect_best_attention()
        assert result is None or isinstance(result, str)

    def test_embedder_load_model_with_mock(self):
        """GPUEmbedder._load_model with mocked SentenceTransformer."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(device="cpu")
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 1024

        with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
            embedder._load_model()
            assert embedder._model is mock_model

    def test_reranker_load_model_with_mock(self):
        """GPUReranker._load_model with mocked CrossEncoder."""
        from app.rag.embed_gpu import GPUReranker
        reranker = GPUReranker(device="cpu")
        mock_model = MagicMock()

        with patch("sentence_transformers.CrossEncoder", return_value=mock_model):
            reranker._load_model()
            assert reranker._model is mock_model

    def test_reranker_fallback_without_model_kwargs(self):
        """GPUReranker falls back when model_kwargs not supported."""
        from app.rag.embed_gpu import GPUReranker
        reranker = GPUReranker(device="cpu")
        mock_model = MagicMock()

        call_count = 0
        def fake_cross_encoder(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TypeError("unexpected keyword argument 'model_kwargs'")
            return mock_model

        with patch("sentence_transformers.CrossEncoder", side_effect=fake_cross_encoder):
            reranker._load_model()
            assert reranker._model is mock_model
            assert call_count == 2
