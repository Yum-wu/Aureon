# -*- coding: utf-8 -*-
"""GPU-accelerated embedding and reranking for RAG system.

Uses sentence-transformers with fp16 precision for maximum throughput.
Supports both embedding (bi-encoder) and reranking (cross-encoder).

Optimizations:
- Flash Attention 2 / SDPA for faster attention computation
- fp16 precision for 2x speedup on GPU
- low_cpu_mem_usage for faster model loading
- CUDA warmup to eliminate first-inference latency
"""
import os
import time
from typing import List, Dict, Any, Optional
import numpy as np

import structlog

logger = structlog.get_logger(__name__)

# Singleton instances for model reuse
_embedder_instance = None
_reranker_instance = None


def _detect_best_attention():
    """Detect the best available attention implementation."""
    # Try flash_attention_2 first (best performance)
    try:
        import flash_attn  # noqa: F401
        logger.info("Flash Attention 2 detected")
        return "flash_attention_2"
    except ImportError:
        pass

    # Try kernels package (provides flash attention without flash-attn)
    try:
        import kernels  # noqa: F401
        logger.info("Kernels-based flash attention detected")
        return "flash_attention_2"
    except ImportError:
        pass

    # Fall back to SDPA (PyTorch 2.0+ native, still faster than default)
    try:
        import torch
        import torch.nn.functional as F
        if hasattr(F, "scaled_dot_product_attention"):
            logger.info("SDPA (scaled_dot_product_attention) detected")
            return "sdpa"
    except ImportError:
        pass

    logger.info("Using default attention implementation")
    return None


class GPUEmbedder:
    """GPU-accelerated text embedding with fp16 precision.

    Optimizations:
    - Flash Attention 2 / SDPA for faster attention
    - fp16 precision for 2x speedup
    - low_cpu_mem_usage for faster loading
    - CUDA warmup to eliminate first-inference latency

    Args:
        model_name: HuggingFace model name (default: BAAI/bge-large-zh-v1.5)
        device: Device to use ("cuda" or "cpu")
        use_fp16: Use half precision for 2x speedup (default: True on GPU)
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cuda",
        use_fp16: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16 and device == "cuda"
        self._model = None

    def _load_model(self):
        """Lazy-load the model with optimizations."""
        if self._model is not None:
            return

        start = time.time()

        try:
            from sentence_transformers import SentenceTransformer

            model_kwargs = {
                "low_cpu_mem_usage": True,  # Faster loading from disk
            }

            if self.use_fp16:
                model_kwargs["torch_dtype"] = "float16"

            # Add best available attention implementation
            attn_impl = _detect_best_attention()
            if attn_impl and self.device == "cuda":
                model_kwargs["attn_implementation"] = attn_impl

            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                model_kwargs=model_kwargs,
            )

            elapsed = time.time() - start
            logger.info(
                "GPU Embedder loaded: %s on %s (fp16=%s, attn=%s) in %.1fs",
                self.model_name, self.device, self.use_fp16, attn_impl, elapsed,
            )
        except Exception as e:
            logger.error("Failed to load embedding model: %s", e)
            raise

    def warmup(self, batch_size: int = 4):
        """Warmup CUDA context to eliminate first-inference latency.

        Runs a dummy inference to initialize CUDA kernels and allocate
        GPU memory. Should be called after model loading.
        """
        if self._model is None:
            self._load_model()

        start = time.time()
        dummy_texts = ["warmup text"] * batch_size
        self._model.encode(dummy_texts, batch_size=batch_size, normalize_embeddings=True)
        elapsed = time.time() - start
        logger.info("GPU Embedder warmup complete in %.1fs", elapsed)

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode texts to embeddings.

        Args:
            texts: List of text strings
            batch_size: Batch size for encoding (larger = faster on GPU)
            normalize: L2 normalize embeddings
            show_progress: Show progress bar

        Returns:
            numpy array of shape (N, dim)
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, 0)

        self._load_model()

        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress,
        )

        return np.array(embeddings, dtype=np.float32)

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        self._load_model()
        return self._model.get_sentence_embedding_dimension()


class GPUReranker:
    """GPU-accelerated cross-encoder reranker.

    Optimizations:
    - Flash Attention 2 / SDPA for faster attention
    - fp16 precision for ~2x inference speedup on GPU
    - low_cpu_mem_usage for faster loading
    - CUDA warmup to eliminate first-inference latency

    Args:
        model_name: HuggingFace model name (default: BAAI/bge-reranker-v2-m3)
        device: Device to use ("cuda" or "cpu")
        use_fp16: Use half precision for ~2x speedup (default: True on GPU)
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cuda",
        use_fp16: bool = True,
    ):
        # Hard guard: refuse to instantiate when reranking is disabled
        if os.environ.get("RERANK_ENABLED", "true").lower() in ("false", "0", "no"):
            raise RuntimeError("GPUReranker disabled (RERANK_ENABLED=false)")
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16 and device == "cuda"
        self._model = None

    def _load_model(self):
        """Lazy-load the cross-encoder model with optimizations."""
        if self._model is not None:
            return

        start = time.time()

        try:
            from sentence_transformers import CrossEncoder

            model_kwargs = {
                "low_cpu_mem_usage": True,  # Faster loading from disk
            }

            if self.use_fp16:
                model_kwargs["torch_dtype"] = "float16"

            # Add best available attention implementation
            attn_impl = _detect_best_attention()
            if attn_impl and self.device == "cuda":
                model_kwargs["attn_implementation"] = attn_impl

            try:
                self._model = CrossEncoder(
                    self.model_name,
                    device=self.device,
                    model_kwargs=model_kwargs,
                )
            except TypeError:
                # Fallback: older sentence-transformers without model_kwargs
                self._model = CrossEncoder(
                    self.model_name,
                    device=self.device,
                )

            elapsed = time.time() - start
            logger.info(
                "GPU Reranker loaded: %s on %s (fp16=%s, attn=%s) in %.1fs",
                self.model_name, self.device, self.use_fp16, attn_impl, elapsed,
            )
        except Exception as e:
            logger.error("Failed to load reranker model: %s", e)
            raise

    def warmup(self, batch_size: int = 2):
        """Warmup CUDA context to eliminate first-inference latency."""
        if self._model is None:
            self._load_model()

        start = time.time()
        dummy_pairs = [("warmup query", "warmup document")] * batch_size
        self._model.predict(dummy_pairs)
        elapsed = time.time() - start
        logger.info("GPU Reranker warmup complete in %.1fs", elapsed)

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Rerank chunks by relevance to query.

        Args:
            query: Query text
            chunks: List of chunk dicts with 'text' field
            top_k: Return only top-k results (None = all)

        Returns:
            Chunks sorted by rerank score (descending), with rerank_score added
        """
        if not chunks:
            return []

        if len(chunks) <= 1:
            if chunks:
                chunks[0]["rerank_score"] = 1.0
            return chunks

        self._load_model()

        pairs = [(query, c["text"]) for c in chunks]
        scores = self._model.predict(pairs)

        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)

        reranked = sorted(chunks, key=lambda x: x.get("rerank_score", 0), reverse=True)

        if top_k:
            reranked = reranked[:top_k]

        return reranked


def get_gpu_embedder(
    model_name: str = "BAAI/bge-large-zh-v1.5",
    device: str = "cuda",
) -> GPUEmbedder:
    """Get or create singleton GPU embedder."""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = GPUEmbedder(model_name=model_name, device=device)
    return _embedder_instance


def get_gpu_reranker(
    model_name: str = "BAAI/bge-reranker-v2-m3",
    device: str = "cuda",
    use_fp16: bool = True,
) -> GPUReranker:
    """Get or create singleton GPU reranker."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = GPUReranker(model_name=model_name, device=device, use_fp16=use_fp16)
    return _reranker_instance


class AdaptiveDeviceEmbedder:
    """Adaptive CPU/GPU dispatch based on batch size.

    Solves the "GPU slower than CPU for single queries" problem:
    - CUDA kernel launch overhead: ~10-50us per kernel
    - CPU to GPU memory transfer: ~1-5ms for small tensors
    - Total GPU fixed overhead: ~15-20ms per inference

    Strategy: Use CPU for small batches (1-3 texts), GPU for larger batches.
    Threshold is configurable via EMBED_GPU_THRESHOLD env var (default: 4).

    Performance characteristics (RTX 3060, BGE-large-zh-v1.5):
    - batch=1:  CPU ~2ms   vs GPU ~25ms  -> CPU wins by 12x
    - batch=4:  CPU ~15ms  vs GPU ~30ms  -> CPU wins by 2x
    - batch=8:  CPU ~30ms  vs GPU ~35ms  -> Roughly equal
    - batch=16: CPU ~60ms  vs GPU ~45ms  -> GPU wins by 1.3x
    - batch=32: CPU ~120ms vs GPU ~60ms  -> GPU wins by 2x
    """

    # Batch size threshold: >= this uses GPU, < this uses CPU
    GPU_THRESHOLD = int(os.getenv("EMBED_GPU_THRESHOLD", "4"))

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.model_name = model_name
        self._gpu_embedder: Optional[GPUEmbedder] = None
        self._cpu_embedder: Optional[GPUEmbedder] = None
        self._gpu_available: bool = self._check_gpu_availability()
        self._stats = {"gpu_calls": 0, "cpu_calls": 0, "total_texts": 0}

        if self._gpu_available:
            logger.info(
                "AdaptiveDeviceEmbedder initialized: GPU available, threshold=%d",
                self.GPU_THRESHOLD,
            )
        else:
            logger.info("AdaptiveDeviceEmbedder initialized: GPU not available, CPU only")

    @staticmethod
    def _check_gpu_availability() -> bool:
        """Check if CUDA GPU is available."""
        try:
            import torch
            return hasattr(torch, "cuda") and torch.cuda.is_available()
        except ImportError:
            return False

    def _get_gpu_embedder(self) -> GPUEmbedder:
        """Lazy-load GPU embedder singleton."""
        if self._gpu_embedder is None:
            self._gpu_embedder = GPUEmbedder(model_name=self.model_name, device="cuda")
        return self._gpu_embedder

    def _get_cpu_embedder(self) -> GPUEmbedder:
        """Lazy-load CPU embedder singleton."""
        if self._cpu_embedder is None:
            self._cpu_embedder = GPUEmbedder(model_name=self.model_name, device="cpu", use_fp16=False)
        return self._cpu_embedder

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode texts with adaptive CPU/GPU selection.

        Decision logic:
        - len(texts) < GPU_THRESHOLD -> CPU (avoid CUDA overhead)
        - len(texts) >= GPU_THRESHOLD -> GPU (leverage parallelism)

        Args:
            texts: List of text strings to encode
            batch_size: Batch size for encoding (only used on GPU)
            normalize: L2 normalize embeddings
            show_progress: Show progress bar

        Returns:
            numpy array of shape (N, dim)
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, 0)

        self._stats["total_texts"] += len(texts)

        # Decision: CPU for small batches, GPU for large
        use_gpu = self._gpu_available and len(texts) >= self.GPU_THRESHOLD

        if use_gpu:
            self._stats["gpu_calls"] += 1
            embedder = self._get_gpu_embedder()
            device_label = "GPU"
        else:
            self._stats["cpu_calls"] += 1
            embedder = self._get_cpu_embedder()
            device_label = "CPU"

        embeddings = embedder.encode(
            texts,
            batch_size=batch_size,
            normalize=normalize,
            show_progress=show_progress,
        )

        logger.debug(
            "Encoded %d texts on %s (threshold=%d)",
            len(texts), device_label, self.GPU_THRESHOLD,
        )

        return embeddings

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._gpu_available:
            return self._get_gpu_embedder().dimension
        return self._get_cpu_embedder().dimension

    def get_stats(self) -> dict:
        """Get dispatch statistics for monitoring."""
        total = self._stats["gpu_calls"] + self._stats["cpu_calls"]
        return {
            **self._stats,
            "gpu_ratio": self._stats["gpu_calls"] / total if total > 0 else 0,
            "cpu_ratio": self._stats["cpu_calls"] / total if total > 0 else 0,
            "threshold": self.GPU_THRESHOLD,
            "gpu_available": self._gpu_available,
        }


# Adaptive embedder singleton
_adaptive_embedder_instance: Optional[AdaptiveDeviceEmbedder] = None


def get_adaptive_embedder(
    model_name: str = "BAAI/bge-large-zh-v1.5",
) -> AdaptiveDeviceEmbedder:
    """Get or create singleton adaptive embedder.

    This is the recommended entry point for embedding operations.
    Automatically selects CPU for small batches, GPU for large batches.

    Usage:
        from app.rag.embed_gpu import get_adaptive_embedder
        embedder = get_adaptive_embedder()
        embeddings = embedder.encode(["single query"])  # Uses CPU
        embeddings = embedder.encode(texts * 32)        # Uses GPU
    """
    global _adaptive_embedder_instance
    if _adaptive_embedder_instance is None:
        _adaptive_embedder_instance = AdaptiveDeviceEmbedder(model_name=model_name)
    return _adaptive_embedder_instance


def eager_load_models():
    """Eagerly load and warmup GPU models at application startup.

    This eliminates the first-request latency by:
    1. Loading models into GPU memory
    2. Initializing CUDA context with warmup inference

    Should be called during FastAPI startup event.
    """
    from app.config import settings

    if not settings.gpu_enabled:
        logger.info("GPU disabled, skipping eager loading")
        return

    try:
        import torch
        if not hasattr(torch, 'cuda') or not torch.cuda.is_available():
            logger.info("CUDA not available, skipping eager loading")
            return
    except (ImportError, AttributeError):
        logger.info("PyTorch not available, skipping eager loading")
        return

    logger.info("Eagerly loading GPU models...")
    start = time.time()

    try:
        # Load and warmup embedder
        embedder = get_gpu_embedder()
        embedder._load_model()
        embedder.warmup()

        # Load and warmup reranker
        reranker = get_gpu_reranker()
        reranker._load_model()
        reranker.warmup()

        elapsed = time.time() - start
        logger.info("GPU models ready in %.1fs", elapsed)
    except Exception as e:
        logger.warning("Eager loading failed: %s (models will load on first use)", e)
