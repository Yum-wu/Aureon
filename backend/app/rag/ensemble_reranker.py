"""
Ensemble reranker combining multiple cross-encoder models with weighted voting.

Uses a committee of rerankers (BGE, Cohere, Jina) to produce more robust
document rankings through score normalization and weighted aggregation.
"""

import os
import threading
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RerankerConfig:
    """Configuration for a single reranker model."""

    name: str
    weight: float = 1.0
    enabled: bool = True
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    device: Optional[str] = None
    use_fp16: bool = True


@dataclass
class EnsembleRerankerStats:
    """Statistics for ensemble reranker performance tracking."""

    total_queries: int = 0
    models_used: Dict[str, int] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    total_latency_ms: float = 0.0


class EnsembleReranker:
    """Ensemble reranker combining multiple models with weighted voting.

    Combines scores from multiple cross-encoder models to produce
    more robust and reliable document rankings.

    Default weights:
    - BGE-Reranker-v2-m3: 0.6 (primary, local or GPU-accelerated)
    - Cohere Rerank 3: 0.3 (API-based, optional)
    - Jina Reranker: 0.1 (API-based, optional)

    Usage:
        config = RerankerConfig(name="bge-v2-m3", weight=0.6, model_name="BAAI/bge-reranker-v2-m3")
        reranker = EnsembleReranker(configs=[config])
        results = await reranker.rerank(query, documents, top_k=5)
    """

    DEFAULT_CONFIGS = [
        RerankerConfig(
            name="bge-v2-m3",
            weight=0.6,
            enabled=True,
            model_name="BAAI/bge-reranker-v2-m3",
        ),
        RerankerConfig(
            name="cohere",
            weight=0.3,
            enabled=False,
            api_key=None,
        ),
        RerankerConfig(
            name="jina",
            weight=0.1,
            enabled=False,
        ),
    ]

    def __init__(self, configs: List[RerankerConfig] = None):
        """Initialize ensemble reranker.

        Args:
            configs: List of RerankerConfig objects. If None, uses DEFAULT_CONFIGS.
        """
        self.configs = configs or self.DEFAULT_CONFIGS
        self._rerankers: Dict[str, Any] = {}
        self._stats = EnsembleRerankerStats()

        # Filter to only enabled configs
        self._enabled_configs = [c for c in self.configs if c.enabled]

        if not self._enabled_configs:
            logger.warning("No reranker models enabled")

        logger.info(
            "Ensemble reranker initialized with %d enabled models: %s",
            len(self._enabled_configs),
            [c.name for c in self._enabled_configs],
        )

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Rerank documents using ensemble of models.

        Args:
            query: The search query
            documents: List of document dicts with 'text' field
            top_k: Number of results to return

        Returns:
            Reranked documents with 'ensemble_score' field added
        """
        if not documents:
            return []

        start_time = time.time()
        self._stats.total_queries += 1

        if len(documents) <= 1:
            for doc in documents:
                doc["ensemble_score"] = 1.0

            elapsed_ms = (time.time() - start_time) * 1000
            self._stats.total_latency_ms += elapsed_ms
            self._stats.avg_latency_ms = (
                self._stats.total_latency_ms / self._stats.total_queries
            )
            return documents

        # Collect scores from each enabled reranker
        all_scores: List[Tuple[str, float, np.ndarray]] = []

        for config in self._enabled_configs:
            try:
                reranker = self._get_reranker(config)
                if reranker is None:
                    continue

                scores = await self._rerank_single(
                    name=config.name,
                    reranker=reranker,
                    query=query,
                    documents=documents,
                )

                if scores is not None and len(scores) > 0:
                    all_scores.append((config.name, config.weight, scores))
                    self._stats.models_used[config.name] = (
                        self._stats.models_used.get(config.name, 0) + 1
                    )
            except Exception as e:
                logger.warning("Reranker %s failed: %s", config.name, e)
                continue

        if not all_scores:
            # Fallback: return documents as-is
            logger.warning("No reranker produced scores, returning original order")
            for doc in documents:
                doc["ensemble_score"] = 0.5
            return documents[:top_k]

        # Combine scores and sort
        ensemble_scores = self._combine_scores(documents, all_scores)

        # Attach scores and sort
        for doc, score in zip(documents, ensemble_scores):
            doc["ensemble_score"] = float(score)

        reranked = sorted(documents, key=lambda x: x.get("ensemble_score", 0), reverse=True)

        # Update stats
        elapsed_ms = (time.time() - start_time) * 1000
        self._stats.total_latency_ms += elapsed_ms
        self._stats.avg_latency_ms = (
            self._stats.total_latency_ms / self._stats.total_queries
        )

        logger.debug(
            "Ensemble rerank complete: %d docs, %d models, %.1fms",
            len(documents),
            len(all_scores),
            elapsed_ms,
        )

        return reranked[:top_k]

    def _get_reranker(self, config: RerankerConfig) -> Any:
        """Lazy-load reranker model based on config.

        Returns a callable reranker or None if unavailable.
        """
        if config.name in self._rerankers:
            return self._rerankers[config.name]

        reranker = None

        # BGE: SentenceTransformer CrossEncoder (local or GPU-accelerated)
        if config.name.startswith("bge"):
            reranker = self._load_bge_reranker(config)

        # Cohere: REST API
        elif config.name == "cohere":
            reranker = self._load_cohere_reranker(config)

        # Jina: REST API
        elif config.name == "jina":
            reranker = self._load_jina_reranker(config)

        if reranker is not None:
            self._rerankers[config.name] = reranker
            logger.info("Loaded reranker: %s", config.name)

        return reranker

    def _load_bge_reranker(self, config: RerankerConfig) -> Optional[Any]:
        """Load BGE cross-encoder reranker.

        Uses CPU cross-encoder with lazy loading.
        """
        model_name = config.model_name or "BAAI/bge-reranker-v2-m3"

        # CPU reranker with lazy loading
        try:
            return ("cpu", {"model_name": model_name})
        except Exception as e:
            logger.warning("BGE reranker unavailable: %s", e)
            return None

    def _load_cohere_reranker(self, config: RerankerConfig) -> Optional[Any]:
        """Load Cohere Rerank 3 API client."""
        api_key = config.api_key or os.environ.get("COHERE_API_KEY")
        if not api_key:
            logger.debug("Cohere API key not configured")
            return None

        try:
            import cohere
            client = cohere.Client(api_key=api_key)
            model = config.model_name or "rerank-multilingual-v3.0"
            return ("api", {"client": client, "model": model, "api_key": api_key})
        except ImportError:
            logger.warning("Cohere library not installed: pip install cohere")
            return None
        except Exception as e:
            logger.warning("Cohere reranker unavailable: %s", e)
            return None

    def _load_jina_reranker(self, config: RerankerConfig) -> Optional[Any]:
        """Load Jina Reranker REST API client."""
        api_key = config.api_key or os.environ.get("JINA_API_KEY")
        if not api_key:
            logger.debug("Jina API key not configured")
            return None

        return ("api", {"api_key": api_key, "model": "jina-reranker-v2-base-multilingual"})

    async def _rerank_single(
        self,
        name: str,
        reranker: Any,
        query: str,
        documents: List[Dict[str, Any]],
    ) -> Optional[np.ndarray]:
        """Rerank using a single model.

        Args:
            name: Reranker name for logging
            reranker: Tuple of (type, config) from _get_reranker
            query: Search query
            documents: List of documents to rerank

        Returns:
            Array of scores, one per document, or None on failure
        """
        if reranker is None:
            return None

        reranker_type, config = reranker

        try:
            if reranker_type == "cpu":
                # CPU reranker (lazy-load CrossEncoder)
                return await self._rerank_with_cpu(config, query, documents)
            elif reranker_type == "api":
                # API-based reranker (Cohere, Jina)
                return await self._rerank_with_api(config, query, documents)
            else:
                logger.warning("Unknown reranker type: %s", reranker_type)
                return None
        except Exception as e:
            logger.warning("Reranker %s failed: %s", name, e)
            return None

    async def _rerank_with_cpu(
        self,
        config: Any,
        query: str,
        documents: List[Dict[str, Any]],
    ) -> np.ndarray:
        """Rerank using CPU cross-encoder with lazy loading."""
        try:
            from sentence_transformers import CrossEncoder

            # Lazy-load model on first use
            if not hasattr(self, '_cpu_reranker_models'):
                self._cpu_reranker_models = {}

            model_name = config["model_name"]
            if model_name not in self._cpu_reranker_models:
                self._cpu_reranker_models[model_name] = CrossEncoder(
                    model_name,
                    device="cpu",
                    use_fp16=False,
                )

            model = self._cpu_reranker_models[model_name]
            pairs = [(query, doc["text"]) for doc in documents]
            scores = model.predict(pairs)
            return np.array(scores, dtype=np.float32)
        except Exception as e:
            logger.warning("CPU reranker failed: %s", e)
            return None

    async def _rerank_with_api(
        self,
        config: Any,
        query: str,
        documents: List[Dict[str, Any]],
    ) -> Optional[np.ndarray]:
        """Rerank using REST API (Cohere, Jina)."""

        if "client" in config:
            # Cohere
            return await self._rerank_cohere(config, query, documents)
        else:
            # Jina
            return await self._rerank_jina(config, query, documents)

    async def _rerank_cohere(
        self,
        config: Any,
        query: str,
        documents: List[Dict[str, Any]],
    ) -> np.ndarray:
        """Rerank using Cohere Rerank 3 API."""
        import aiohttp

        api_key = config["api_key"]
        model = config["model"]
        url = "https://api.cohere.ai/v1/rerank"

        texts = [doc["text"] for doc in documents]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "query": query,
            "documents": texts,
            "top_n": len(texts),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"Cohere API error {resp.status}: {error}")
                data = await resp.json()

        # Build scores array (Cohere returns relevance_scores in order)
        scores = np.zeros(len(texts), dtype=np.float32)
        for result in data.get("results", []):
            idx = result["index"]
            scores[idx] = result["relevance_score"]

        return scores

    async def _rerank_jina(
        self,
        config: Any,
        query: str,
        documents: List[Dict[str, Any]],
    ) -> np.ndarray:
        """Rerank using Jina Reranker API."""
        import aiohttp

        api_key = config["api_key"]
        model = config["model"]
        url = "https://api.jina.ai/v1/rerank"

        texts = [doc["text"] for doc in documents]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "query": query,
            "documents": texts,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"Jina API error {resp.status}: {error}")
                data = await resp.json()

        # Build scores array (Jina returns results with index and relevance_score)
        scores = np.zeros(len(texts), dtype=np.float32)
        for result in data.get("results", []):
            idx = result["index"]
            scores[idx] = result["relevance_score"]

        return scores

    def _combine_scores(
        self,
        documents: List[Dict[str, Any]],
        all_scores: List[Tuple[str, float, np.ndarray]],
    ) -> np.ndarray:
        """Combine scores from multiple rerankers using weighted voting.

        Args:
            documents: Original documents (for normalization reference)
            all_scores: List of tuples (reranker_name, weight, scores_array)

        Returns:
            Array of ensemble scores, one per document
        """
        n_docs = len(documents)
        if not all_scores:
            return np.zeros(n_docs, dtype=np.float32)

        # Initialize ensemble scores
        ensemble_scores = np.zeros(n_docs, dtype=np.float32)
        total_weight = 0.0

        for name, weight, scores in all_scores:
            if len(scores) != n_docs:
                logger.warning(
                    "Score count mismatch for %s: %d vs %d docs",
                    name, len(scores), n_docs,
                )
                continue

            # Normalize scores to [0, 1]
            normalized = self._normalize_scores(scores)

            # Apply weight and add to ensemble
            ensemble_scores += normalized * weight
            total_weight += weight

        # Normalize final ensemble scores
        if total_weight > 0:
            ensemble_scores /= total_weight

        return ensemble_scores

    def _normalize_scores(self, scores: np.ndarray) -> np.ndarray:
        """Normalize scores to [0, 1] range using min-max normalization.

        Handles edge cases:
        - All scores equal: returns 0.5 for all
        - Single document: returns 1.0
        """
        if len(scores) == 0:
            return scores

        if len(scores) == 1:
            return np.array([1.0], dtype=np.float32)

        min_score = np.min(scores)
        max_score = np.max(scores)

        # Handle edge case: all scores equal
        if max_score - min_score < 1e-6:
            return np.full_like(scores, 0.5, dtype=np.float32)

        # Min-max normalization
        normalized = (scores - min_score) / (max_score - min_score)
        return normalized.astype(np.float32)

    def get_stats(self) -> Dict[str, Any]:
        """Get ensemble reranker statistics."""
        return {
            "total_queries": self._stats.total_queries,
            "avg_latency_ms": round(self._stats.avg_latency_ms, 2),
            "total_latency_ms": round(self._stats.total_latency_ms, 2),
            "models_used": self._stats.models_used.copy(),
            "enabled_configs": [
                {
                    "name": c.name,
                    "weight": c.weight,
                    "model_name": c.model_name,
                }
                for c in self._enabled_configs
            ],
        }

    def reset_stats(self):
        """Reset performance statistics."""
        self._stats = EnsembleRerankerStats()


_ensemble_reranker_lock = threading.Lock()


def get_ensemble_reranker() -> EnsembleReranker:
    """Get a singleton ensemble reranker instance.

    Creates and caches a default ensemble reranker on first call.
    Returns the same instance on subsequent calls for connection reuse.

    Returns:
        EnsembleReranker instance with auto-detected available models
    """
    if hasattr(get_ensemble_reranker, "_instance"):  # Fast path (no lock)
        return get_ensemble_reranker._instance

    with _ensemble_reranker_lock:
        if hasattr(get_ensemble_reranker, "_instance"):  # Double-check
            return get_ensemble_reranker._instance
        get_ensemble_reranker._instance = create_default_ensemble()
    return get_ensemble_reranker._instance


def create_default_ensemble() -> EnsembleReranker:
    """Create default ensemble reranker with config weights."""
    from app.config import settings

    configs = [
        RerankerConfig(
            name="bge-v2-m3",
            weight=settings.ensemble_bge_weight,
            enabled=True,
            model_name="BAAI/bge-reranker-v2-m3",
        ),
        RerankerConfig(
            name="cohere",
            weight=settings.ensemble_cohere_weight,
            enabled=settings.cohere_api_key is not None,
            api_key=settings.cohere_api_key,
            model_name=settings.cohere_rerank_model,
        ),
        RerankerConfig(
            name="jina",
            weight=settings.ensemble_jina_weight,
            enabled=settings.jina_api_key is not None,
            api_key=settings.jina_api_key,
        ),
    ]

    return EnsembleReranker(configs)
