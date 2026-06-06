"""Tests for GPU-accelerated embedding."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


class TestGPUEmbedding:
    """Test GPU embedding wrapper."""

    def test_gpu_embed_returns_correct_shape(self):
        """Test embedding output shape matches input."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")  # cpu for CI
        texts = ["Hello world", "Test sentence"]
        result = embedder.encode(texts)
        assert result.shape[0] == 2
        assert result.shape[1] > 0  # Has dimensions

    def test_gpu_embed_empty_input(self):
        """Test embedding empty input returns empty array."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")
        result = embedder.encode([])
        assert result.shape[0] == 0

    def test_gpu_embed_single_text(self):
        """Test embedding single text."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")
        result = embedder.encode(["Single test"])
        assert result.shape[0] == 1

    def test_gpu_embed_normalized(self):
        """Test embeddings are L2 normalized."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")
        result = embedder.encode(["Test normalization"])
        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_gpu_reranker_returns_scores(self):
        """Test reranker returns score for each pair."""
        from app.rag.embed_gpu import GPUReranker
        reranker = GPUReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu")
        query = "What is RAG?"
        docs = [
            {"text": "RAG is retrieval augmented generation"},
            {"text": "Python is a programming language"},
        ]
        result = reranker.rerank(query, docs)
        assert len(result) == 2
        assert all(isinstance(c.get("rerank_score"), float) for c in result)
