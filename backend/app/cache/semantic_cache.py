"""
Semantic LLM Cache with two-layer lookup architecture.

Implements Exact → Semantic → LLM caching strategy:
- Exact: Direct hash lookup for identical queries (fastest)
- Semantic: Vector similarity search for semantically similar queries
- LLM: Fallback to actual LLM call

Uses Redis for persistence with in-memory fallback.
Embedding model: BAAI/bge-large-zh-v1.5 (lazy-loaded).
"""

import hashlib
import json
import re
import time
from collections import OrderedDict
from typing import Optional, Dict, Any, Tuple, List
import structlog

logger = structlog.get_logger()

# Sentinel: None = uninitialized, False = unavailable, valid client = ready
_redis = None
_redis_fail_count = 0
_RECONNECT_AFTER = 5  # Retry after N failures


class SemanticLLMCache:
    """Two-layer semantic cache for LLM responses.

    Architecture:
        Layer 1: Exact match (hash-based, O(1))
        Layer 2: Semantic similarity (vector embedding, cosine similarity)
        Layer 3: LLM fallback (actual API call)

    Features:
        - Lazy embedding model loading
        - Redis persistence with in-memory fallback
        - LRU eviction for cache size management
        - TTL-based expiry (default 24 hours)
        - Cosine similarity for semantic matching
    """

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        default_ttl: int = 86400,  # 24 hours
        max_cache_size: int = 10000,
        embedding_model: str = "BAAI/bge-large-zh-v1.5",
        embedding_dim: int = 1024,
    ):
        """Initialize semantic cache.

        Args:
            similarity_threshold: Minimum cosine similarity to consider a cache hit (0-1)
            default_ttl: Default time-to-live in seconds (default: 24 hours)
            max_cache_size: Maximum number of cached entries (LRU eviction)
            embedding_model: BGE model name for embeddings
            embedding_dim: Embedding dimensions
        """
        self.similarity_threshold = similarity_threshold
        self.default_ttl = default_ttl
        self.max_cache_size = max_cache_size
        self.embedding_model_name = embedding_model
        self.embedding_dim = embedding_dim

        # Lazy-loaded embedding model
        self._embedding_model = None
        self._embedding_model_loaded = False

        # In-memory caches (fallback when Redis unavailable)
        self._mem_exact_cache: OrderedDict = OrderedDict()  # LRU
        self._mem_semantic_cache: Dict[str, Dict] = {}
        self._stats = {
            "exact_hits": 0,
            "semantic_hits": 0,
            "misses": 0,
            "sets": 0,
            "errors": 0,
        }

        # Cache key version (increment to invalidate all caches)
        self._cache_version = "v1"

    def _get_redis(self):
        """Return Redis client singleton, or False if unavailable.

        Retries connection after _RECONNECT_AFTER failures to handle
        cases where Redis becomes available after app startup.
        """
        global _redis, _redis_fail_count

        if _redis is not None:
            return _redis

        # Retry after enough failures
        if _redis is False and _redis_fail_count < _RECONNECT_AFTER:
            return False

        if _redis is False:
            _redis = None  # Reset to retry
            _redis_fail_count = 0

        try:
            import redis.asyncio as aioredis
            from app.config import settings

            _redis = aioredis.from_url(
                settings.redis_url or "redis://localhost:6379/0",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            _redis_fail_count = 0
            logger.info("Semantic cache: Redis connected")
        except Exception as e:
            logger.warning("Semantic cache: Redis unavailable (non-fatal): %s", e)
            _redis = False
            _redis_fail_count += 1

        return _redis

    def _load_embedding_model(self):
        """Lazy-load the BGE embedding model on first use.

        Skips loading if SKIP_LOCAL_EMBED=true (recommended for Railway/CPU).
        """
        if self._embedding_model_loaded:
            return self._embedding_model is not None

        # Check if local embedding is disabled (e.g., Railway with limited memory)
        import os
        skip_local = os.getenv("SKIP_LOCAL_EMBED", "").lower() in ("1", "true", "yes")
        if skip_local:
            logger.info("Skipping local BGE embed (SKIP_LOCAL_EMBED=true), semantic cache will use exact match only")
            self._embedding_model_loaded = True
            return False

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "Loading embedding model: %s (this may take a moment)",
                self.embedding_model_name,
            )
            self._embedding_model = SentenceTransformer(self.embedding_model_name)
            self._embedding_model_loaded = True
            logger.info("Embedding model loaded successfully")
            return True
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Semantic cache will fallback to exact match only. "
                "Install with: pip install sentence-transformers"
            )
            self._embedding_model_loaded = True
            return False
        except Exception as e:
            logger.error(
                "Failed to load embedding model %s: %s",
                self.embedding_model_name,
                e,
            )
            self._embedding_model_loaded = True
            return False

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding vector for text.

        Args:
            text: Input text to embed

        Returns:
            List of floats (embedding vector) or None if unavailable
        """
        if not self._load_embedding_model():
            return None

        try:
            embedding = self._embedding_model.encode(
                text,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return embedding.tolist()
        except Exception as e:
            logger.error("Embedding generation failed: %s", e)
            return None

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec1: First embedding vector
            vec2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        # Compute dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Compute magnitudes
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def _exact_cache_key(
        self,
        query: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate deterministic cache key for exact matching.

        Args:
            query: User query
            model: LLM model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Hash string for cache key
        """
        # Normalize query: lowercase, remove extra whitespace
        normalized_query = re.sub(r'\s+', ' ', query.strip().lower())

        # Create composite key
        key_parts = [
            f"model:{model}",
            f"temp:{temperature}",
            f"max_tokens:{max_tokens}",
            f"query:{normalized_query}",
        ]
        key_string = "|".join(key_parts)

        # Generate hash
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"semantic:{self._cache_version}:exact:{key_hash}"

    def _semantic_cache_key(
        self,
        model: str,
        temperature: float,
        max_tokens: int,
        embedding_hash: str,
    ) -> str:
        """Generate cache key for semantic matching.

        Args:
            model: LLM model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            embedding_hash: Hash of the embedding vector

        Returns:
            Cache key string
        """
        return (
            f"semantic:{self._cache_version}:semantic:"
            f"{model}:{temperature}:{max_tokens}:{embedding_hash}"
        )

    async def get_exact(
        self,
        query: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Optional[str]:
        """Fast exact match cache lookup.

        Args:
            query: User query
            model: LLM model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Cached response or None
        """
        cache_key = self._exact_cache_key(query, model, temperature, max_tokens)

        # Try in-memory first (fastest)
        if cache_key in self._mem_exact_cache:
            # Move to end (most recently used)
            self._mem_exact_cache.move_to_end(cache_key)
            entry = self._mem_exact_cache[cache_key]
            if time.monotonic() < entry["expires_at"]:
                self._stats["exact_hits"] += 1
                logger.debug("Exact cache HIT (in-memory)")
                return entry["response"]
            else:
                del self._mem_exact_cache[cache_key]

        # Try Redis
        r = self._get_redis()
        if r:
            try:
                cached = await r.get(cache_key)
                if cached is not None:
                    self._stats["exact_hits"] += 1
                    logger.debug("Exact cache HIT (Redis)")
                    # Populate in-memory cache
                    self._mem_exact_cache[cache_key] = {
                        "response": cached,
                        "expires_at": time.monotonic() + self.default_ttl,
                    }
                    return cached
            except Exception as e:
                logger.debug("Redis exact lookup error: %s", e)

        return None

    async def get_semantic(
        self,
        query: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Optional[Tuple[str, float]]:
        """Vector similarity search for semantically similar queries.

        Args:
            query: User query
            model: LLM model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Tuple of (cached_response, similarity_score) or None
        """
        # Get embedding for query
        embedding = self._get_embedding(query)
        if embedding is None:
            return None

        # Search in-memory semantic cache
        best_match = None
        best_score = 0.0

        for key, entry in self._mem_semantic_cache.items():
            # Check if same model/params and not expired
            if (
                entry.get("model") != model
                or entry.get("temperature") != temperature
                or entry.get("max_tokens") != max_tokens
            ):
                continue

            if time.monotonic() > entry.get("expires_at", 0):
                continue

            # Compute similarity
            cached_embedding = entry.get("embedding")
            if cached_embedding:
                score = self._cosine_similarity(embedding, cached_embedding)
                if score > best_score and score >= self.similarity_threshold:
                    best_score = score
                    best_match = entry

        if best_match:
            self._stats["semantic_hits"] += 1
            logger.debug(
                "Semantic cache HIT (in-memory, score=%.3f)", best_score
            )
            return best_match["response"], best_score

        # Search Redis (simplified: iterate by pattern)
        r = self._get_redis()
        if r:
            try:
                pattern = f"semantic:{self._cache_version}:semantic:{model}:{temperature}:{max_tokens}:*"
                cursor = 0
                while True:
                    cursor, keys = await r.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    for key in keys:
                        try:
                            cached_data = await r.get(key)
                            if cached_data:
                                data = json.loads(cached_data)
                                cached_embedding = data.get("embedding")
                                if cached_embedding:
                                    score = self._cosine_similarity(
                                        embedding, cached_embedding
                                    )
                                    if score > best_score and score >= self.similarity_threshold:
                                        best_score = score
                                        best_match = data
                        except Exception as e:
                            logger.debug("Redis semantic lookup error for key %s: %s", key, e)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug("Redis semantic scan error: %s", e)

        if best_match:
            self._stats["semantic_hits"] += 1
            logger.debug("Semantic cache HIT (Redis, score=%.3f)", best_score)
            return best_match["response"], best_score

        return None

    async def set(
        self,
        query: str,
        response: str,
        model: str,
        temperature: float,
        max_tokens: int,
        ttl: Optional[int] = None,
    ) -> bool:
        """Store response in cache (both exact and semantic).

        Args:
            query: User query
            response: LLM response to cache
            model: LLM model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            ttl: Time-to-live in seconds (uses default if None)

        Returns:
            True if successfully cached
        """
        ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.monotonic() + ttl

        # Store in exact cache
        exact_key = self._exact_cache_key(query, model, temperature, max_tokens)

        # In-memory exact cache
        self._mem_exact_cache[exact_key] = {
            "response": response,
            "expires_at": expires_at,
        }

        # Evict LRU if over limit
        while len(self._mem_exact_cache) > self.max_cache_size:
            self._mem_exact_cache.popitem(last=False)

        # Redis exact cache
        r = self._get_redis()
        if r:
            try:
                await r.setex(exact_key, ttl, response)
            except Exception as e:
                logger.debug("Redis exact set error: %s", e)

        # Store in semantic cache with embedding
        embedding = self._get_embedding(query)
        if embedding:
            embedding_hash = hashlib.sha256(
                json.dumps(embedding).encode()
            ).hexdigest()[:16]

            semantic_key = self._semantic_cache_key(
                model, temperature, max_tokens, embedding_hash
            )

            semantic_data = {
                "response": response,
                "embedding": embedding,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "expires_at": expires_at,
                "query": query[:100],  # Store first 100 chars for debugging
            }

            # In-memory semantic cache
            self._mem_semantic_cache[semantic_key] = semantic_data

            # Redis semantic cache
            if r:
                try:
                    # Store without embedding in Redis (too large)
                    redis_data = {
                        "response": response,
                        "model": model,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "query": query[:100],
                    }
                    await r.setex(semantic_key, ttl, json.dumps(redis_data))
                except Exception as e:
                    logger.debug("Redis semantic set error: %s", e)

        self._stats["sets"] += 1
        logger.debug("Cache SET for query (exact+semantic)")
        return True

    async def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics.

        Returns:
            Dictionary with cache hit/miss rates and other stats
        """
        total_lookups = (
            self._stats["exact_hits"]
            + self._stats["semantic_hits"]
            + self._stats["misses"]
        )

        stats = {
            **self._stats,
            "total_lookups": total_lookups,
            "hit_rate": (
                (self._stats["exact_hits"] + self._stats["semantic_hits"])
                / total_lookups
                if total_lookups > 0
                else 0.0
            ),
            "exact_hit_rate": (
                self._stats["exact_hits"] / total_lookups
                if total_lookups > 0
                else 0.0
            ),
            "semantic_hit_rate": (
                self._stats["semantic_hits"] / total_lookups
                if total_lookups > 0
                else 0.0
            ),
            "in_memory_exact_size": len(self._mem_exact_cache),
            "in_memory_semantic_size": len(self._mem_semantic_cache),
            "embedding_model_loaded": self._embedding_model_loaded,
            "similarity_threshold": self.similarity_threshold,
            "max_cache_size": self.max_cache_size,
            "default_ttl": self.default_ttl,
        }

        # Add Redis stats if available
        r = self._get_redis()
        if r:
            try:
                info = await r.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "unknown")
            except Exception as e:
                stats["redis_memory_used"] = "error: %s" % e

        return stats

    def increment_misses(self):
        """Increment miss counter (call when LLM is actually called)."""
        self._stats["misses"] += 1

    async def clear(self, prefix: Optional[str] = None) -> int:
        """Clear cache entries.

        Args:
            prefix: Optional prefix to clear specific cache entries.
                    If None, clears all semantic cache entries.

        Returns:
            Number of entries cleared
        """
        cleared = 0

        # Clear in-memory caches
        if prefix is None:
            self._mem_exact_cache.clear()
            self._mem_semantic_cache.clear()
            logger.info("Cleared all in-memory semantic cache entries")
            return -1  # Indicate all cleared

        # Clear Redis
        r = self._get_redis()
        if r:
            try:
                pattern = f"semantic:{self._cache_version}:{prefix}*"
                cursor = 0
                while True:
                    cursor, keys = await r.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    if keys:
                        cleared += await r.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning("Cache clear error: %s", e)

        return cleared

    async def close(self):
        """Close Redis connection on shutdown."""
        global _redis

        if _redis:
            try:
                await _redis.close()
            except Exception:
                pass
            _redis = None


# Module-level singleton
_cache_instance: Optional[SemanticLLMCache] = None


def get_semantic_cache() -> SemanticLLMCache:
    """Get or create the singleton SemanticLLMCache instance."""
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = SemanticLLMCache()
        logger.info("Created singleton SemanticLLMCache instance")

    return _cache_instance


async def close_semantic_cache():
    """Close the singleton cache instance."""
    global _cache_instance

    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None
        logger.info("Closed SemanticLLMCache instance")
