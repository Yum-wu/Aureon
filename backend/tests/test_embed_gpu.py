"""GPU/local embedding tests removed - API-only mode.

Original GPU embedder module has been replaced with stubs.
These tests verify the stubs raise RuntimeError as expected.
"""
import pytest


class TestEmbedGpuRemoved:
    """Verify GPU embedder stubs raise RuntimeError."""

    def test_gpuembedder_raises(self):
        from app.rag.embed_gpu import GPUEmbedder
        with pytest.raises(RuntimeError, match="GPU embedder removed"):
            GPUEmbedder()

    def test_gpureranker_raises(self):
        from app.rag.embed_gpu import GPUReranker
        with pytest.raises(RuntimeError, match="GPU reranker removed"):
            GPUReranker()

    def test_get_adaptive_embedder_raises(self):
        from app.rag.embed_gpu import get_adaptive_embedder
        with pytest.raises(RuntimeError, match="Adaptive embedder removed"):
            get_adaptive_embedder()

    def test_eager_load_models_noop(self):
        from app.rag.embed_gpu import eager_load_models
        eager_load_models()  # should not raise
