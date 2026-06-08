"""Unit tests for semantic cache module.

Tests the core semantic cache functionality including:
- Cache initialization and configuration
- Exact cache key generation
- Cosine similarity computation
- Cache hit/miss behavior
- Statistics tracking
- LRU eviction
- Redis integration

Run with: python -m pytest tests/test_semantic_cache.py -v
"""

import asyncio
import pytest
import time
from unittest.mock import patch, AsyncMock, MagicMock

# Import the semantic cache module
try:
    from app.cache.semantic_cache import SemanticLLMCache, get_semantic_cache
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


# Skip all tests if imports are not available
pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE,
    reason="Semantic cache module not available",
)


# ──────────────────────────────────────────────────────────────────────────────
# Test Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def cache():
    """Create a fresh SemanticLLMCache instance for testing."""
    return SemanticLLMCache(
        similarity_threshold=0.92,
        default_ttl=3600,
        max_cache_size=1000,
        embedding_model="BAAI/bge-large-zh-v1.5",
    )


@pytest.fixture
def small_cache():
    """Create a small cache for LRU eviction testing."""
    return SemanticLLMCache(
        similarity_threshold=0.92,
        default_ttl=3600,
        max_cache_size=5,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test: Initialization
# ──────────────────────────────────────────────────────────────────────────────


def test_cache_initialization(cache):
    """Test cache is initialized with correct parameters."""
    assert cache.similarity_threshold == 0.92
    assert cache.default_ttl == 3600
    assert cache.max_cache_size == 1000
    assert cache._embedding_model_loaded is False
    assert len(cache._mem_exact_cache) == 0
    assert len(cache._mem_semantic_cache) == 0


def test_cache_initialization_default_params():
    """Test cache initialization with default parameters."""
    cache = SemanticLLMCache()

    assert cache.similarity_threshold == 0.92
    assert cache.default_ttl == 86400  # 24 hours
    assert cache.max_cache_size == 10000


def test_cache_singleton():
    """Test get_semantic_cache returns singleton instance."""
    cache1 = get_semantic_cache()
    cache2 = get_semantic_cache()

    assert cache1 is cache2


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cache Key Generation
# ──────────────────────────────────────────────────────────────────────────────


def test_exact_cache_key_deterministic(cache):
    """Test that same inputs produce same key."""
    query = "What is RAG?"
    model = "deepseek"
    temperature = 0.0
    max_tokens = 500

    key1 = cache._exact_cache_key(query, model, temperature, max_tokens)
    key2 = cache._exact_cache_key(query, model, temperature, max_tokens)

    assert key1 == key2


def test_exact_cache_key_format(cache):
    """Test key format is correct."""
    key = cache._exact_cache_key("test", "deepseek", 0.0, 500)

    assert key.startswith("semantic:v1:exact:")
    assert len(key) == len("semantic:v1:exact:") + 16  # 16 char hash


def test_exact_cache_key_normalization(cache):
    """Test key normalizes query properly."""
    # Whitespace and case variations should produce same key
    key1 = cache._exact_cache_key("What is RAG?", "deepseek", 0.0, 500)
    key2 = cache._exact_cache_key("  what is rag?  ", "deepseek", 0.0, 500)

    assert key1 == key2


def test_exact_cache_key_unique_per_params(cache):
    """Test different parameters produce different keys."""
    base_key = cache._exact_cache_key("test", "deepseek", 0.0, 500)

    # Different model
    model_key = cache._exact_cache_key("test", "gpt-4", 0.0, 500)
    assert model_key != base_key

    # Different temperature
    temp_key = cache._exact_cache_key("test", "deepseek", 0.7, 500)
    assert temp_key != base_key

    # Different max_tokens
    tokens_key = cache._exact_cache_key("test", "deepseek", 0.0, 1000)
    assert tokens_key != base_key


def test_semantic_cache_key_format(cache):
    """Test semantic cache key format is correct."""
    key = cache._semantic_cache_key("deepseek", 0.0, 500, "abc123")

    assert key.startswith("semantic:v1:semantic:")
    assert "deepseek" in key
    assert "abc123" in key


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cosine Similarity
# ──────────────────────────────────────────────────────────────────────────────


def test_cosine_similarity_identical_vectors():
    """Test cosine similarity with identical vectors."""
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert abs(similarity - 1.0) < 1e-6


def test_cosine_similarity_orthogonal_vectors():
    """Test cosine similarity with orthogonal vectors."""
    vec1 = [1.0, 0.0]
    vec2 = [0.0, 1.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert abs(similarity) < 1e-6


def test_cosine_similarity_similar_vectors():
    """Test cosine similarity with similar but not identical vectors."""
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.9, 0.1, 0.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert 0.8 < similarity < 1.0


def test_cosine_similarity_opposite_vectors():
    """Test cosine similarity with opposite vectors."""
    vec1 = [1.0, 0.0]
    vec2 = [-1.0, 0.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert abs(similarity + 1.0) < 1e-6


def test_cosine_similarity_zero_vectors():
    """Test cosine similarity with zero vectors."""
    vec1 = [0.0, 0.0]
    vec2 = [1.0, 0.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert similarity == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Test: In-Memory Cache
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_cache_set_and_get(cache):
    """Test setting and getting from exact cache."""
    query = "test query"
    response = "test response"
    model = "deepseek"
    temperature = 0.0
    max_tokens = 500

    # Set
    success = await cache.set(
        query=query,
        response=response,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    assert success is True

    # Get exact
    cached = await cache.get_exact(
        query=query,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    assert cached == response


@pytest.mark.asyncio
async def test_exact_cache_miss(cache):
    """Test exact cache miss when entry doesn't exist."""
    cached = await cache.get_exact(
        query="nonexistent query",
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached is None


@pytest.mark.asyncio
async def test_exact_cache_miss_different_model(cache):
    """Test exact cache miss when model differs."""
    query = "test query"
    response = "test response"

    # Set with one model
    await cache.set(
        query=query,
        response=response,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    # Get with different model
    cached = await cache.get_exact(
        query=query,
        model="gpt-4",  # Different model
        temperature=0.0,
        max_tokens=500,
    )

    assert cached is None


@pytest.mark.asyncio
async def test_exact_cache_hit_after_ttl(cache):
    """Test exact cache miss after TTL expires."""
    query = "test query"
    response = "test response"

    # Set with TTL=0 (expires immediately)
    await cache.set(
        query=query,
        response=response,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
        ttl=0,
    )

    # Wait for expiry
    await asyncio.sleep(0.01)

    # Lookup should miss
    cached = await cache.get_exact(
        query=query,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached is None


@pytest.mark.asyncio
async def test_exact_cache_lru_eviction(small_cache):
    """Test LRU eviction when cache exceeds max size."""
    # Add more entries than max_cache_size (5)
    for i in range(10):
        await small_cache.set(
            query=f"Query {i}",
            response=f"Response {i}",
            model="deepseek",
            temperature=0.0,
            max_tokens=500,
        )

    # Verify cache size is within limit
    assert len(small_cache._mem_exact_cache) <= 5


# ──────────────────────────────────────────────────────────────────────────────
# Test: Statistics
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_stats_structure(cache):
    """Test cache statistics return correct structure."""
    stats = await cache.get_stats()

    required_fields = [
        "exact_hits",
        "semantic_hits",
        "misses",
        "sets",
        "total_lookups",
        "hit_rate",
        "exact_hit_rate",
        "semantic_hit_rate",
        "in_memory_exact_size",
        "in_memory_semantic_size",
        "embedding_model_loaded",
        "similarity_threshold",
        "max_cache_size",
        "default_ttl",
    ]

    for field in required_fields:
        assert field in stats, f"Missing required field: {field}"


@pytest.mark.asyncio
async def test_cache_stats_hit_rate(cache):
    """Test hit rate calculation."""
    # Set some entries
    for i in range(5):
        await cache.set(
            query=f"Query {i}",
            response=f"Response {i}",
            model="deepseek",
            temperature=0.0,
            max_tokens=500,
        )

    # Lookup some entries
    for i in range(3):
        await cache.get_exact(
            query=f"Query {i}",
            model="deepseek",
            temperature=0.0,
            max_tokens=500,
        )

    # Get stats
    stats = await cache.get_stats()

    # Verify hit rate is calculated
    assert 0 <= stats["hit_rate"] <= 1
    assert stats["exact_hits"] >= 0


@pytest.mark.asyncio
async def test_cache_stats_in_memory_sizes(cache):
    """Test in-memory cache size tracking."""
    # Add entries
    for i in range(5):
        await cache.set(
            query=f"Query {i}",
            response=f"Response {i}",
            model="deepseek",
            temperature=0.0,
            max_tokens=500,
        )

    stats = await cache.get_stats()

    assert stats["in_memory_exact_size"] == 5
    assert stats["in_memory_semantic_size"] >= 0


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cache Clearing
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_clear_all(cache):
    """Test clearing all cache entries."""
    # Add entries
    for i in range(5):
        await cache.set(
            query=f"Query {i}",
            response=f"Response {i}",
            model="deepseek",
            temperature=0.0,
            max_tokens=500,
        )

    # Clear all
    cleared = await cache.clear()

    assert cleared == -1

    # Verify entries are gone
    cached = await cache.get_exact(
        query="Query 0",
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached is None


# ──────────────────────────────────────────────────────────────────────────────
# Test: Edge Cases
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_empty_query(cache):
    """Test caching with empty query."""
    query = ""
    response = "Response to empty query"

    success = await cache.set(
        query=query,
        response=response,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True

    cached = await cache.get_exact(
        query=query,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached == response


@pytest.mark.asyncio
async def test_cache_long_query(cache):
    """Test caching with very long query."""
    query = "What is " + "artificial intelligence " * 100 + "?"
    response = "AI is a broad field."

    success = await cache.set(
        query=query,
        response=response,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True


@pytest.mark.asyncio
async def test_cache_unicode_query(cache):
    """Test caching with Unicode characters."""
    query = "什么是机器学习？"
    response = "机器学习是人工智能的分支。"

    success = await cache.set(
        query=query,
        response=response,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True

    cached = await cache.get_exact(
        query=query,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached == response


@pytest.mark.asyncio
async def test_cache_special_characters(cache):
    """Test caching with special characters."""
    query = "What is <script>alert('xss')</script>?"
    response = "This is a normal response."

    success = await cache.set(
        query=query,
        response=response,
        model="deepseek",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True


# ──────────────────────────────────────────────────────────────────────────────
# Test: Miss Counter
# ──────────────────────────────────────────────────────────────────────────────


def test_increment_misses(cache):
    """Test incrementing miss counter."""
    initial_misses = cache._stats["misses"]

    cache.increment_misses()

    assert cache._stats["misses"] == initial_misses + 1


@pytest.mark.asyncio
async def test_cache_stats_misses(cache):
    """Test miss counter is tracked in stats."""
    # Increment misses a few times
    for _ in range(10):
        cache.increment_misses()

    stats = await cache.get_stats()

    assert stats["misses"] == 10
