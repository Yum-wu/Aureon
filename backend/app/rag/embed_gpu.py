"""GPU/local embedding removed - API-only mode.

All functions here are stubs for backward compatibility.
"""
import structlog
logger = structlog.get_logger(__name__)

def eager_load_models():
    """No-op: local/GPU models removed."""
    logger.info("Local/GPU models removed, using API-only embedding")

def get_gpu_embedder(*a, **kw):
    raise RuntimeError("GPU embedder removed - use API embedding")

def get_gpu_reranker(*a, **kw):
    raise RuntimeError("GPU reranker removed - use API reranker")

def get_adaptive_embedder(*a, **kw):
    raise RuntimeError("Adaptive embedder removed - use API embedding")

class GPUEmbedder:
    def __init__(self, *a, **kw):
        raise RuntimeError("GPU embedder removed - use API embedding")

class GPUReranker:
    def __init__(self, *a, **kw):
        raise RuntimeError("GPU reranker removed - use API reranker")

class AdaptiveDeviceEmbedder:
    def __init__(self, *a, **kw):
        raise RuntimeError("Adaptive embedder removed - use API embedding")
