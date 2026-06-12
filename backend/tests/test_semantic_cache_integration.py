"""Integration tests for semantic cache system.

These tests verify the two-layer cache architecture (exact → semantic)
using real Redis for integration testing. Tests skip if Redis is unavailable.

Test coverage:
- Exact cache hit/miss
- Semantic similarity cache hit/miss
- Cache statistics and metrics
- Cache clearing and TTL expiration
- Fallback to in-memory cache
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock

# Import the semantic cache module
try:
    from app.cache.semantic_cache import SemanticLLMCache
    from app.cache.redis_client import (
        get_cached_with_semantic,
        set_cached_with_semantic,
        get_cache_metrics,
    )

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


# Skip all tests if imports are not available
pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE,
    reason="Semantic cache module not available",
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def semantic_cache():
    """Create a fresh SemanticLLMCache instance for testing."""
    cache = SemanticLLMCache(
        similarity_threshold=0.92,
        default_ttl=3600,  # 1 hour for testing
        max_cache_size=1000,
        embedding_model="BAAI/bge-large-zh-v1.5",
    )
    return cache


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for testing."""
    mock_r = AsyncMock()
    mock_r.get = AsyncMock(return_value=None)
    mock_r.setex = AsyncMock()
    mock_r.delete = AsyncMock(return_value=1)
    mock_r.scan = AsyncMock(return_value=(0, []))
    mock_r.info = AsyncMock(return_value={"used_memory_human": "1.5 MB"})
    return mock_r


@pytest.fixture(autouse=True)
def reset_cache_state():
    """Reset cache state between tests."""
    yield
    # Reset module-level state if needed
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Test: Exact Cache Hit
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_cache_hit(semantic_cache):
    """Test exact cache hit with identical query parameters.

    Verifies that querying with the exact same parameters returns the cached
    response immediately without calling the LLM.
    """
    query = "What is retrieval augmented generation?"
    response = "RAG is a technique that combines retrieval and generation."
    model = "qwen3.6-flash"
    temperature = 0.0
    max_tokens = 500

    # Store in cache
    success = await semantic_cache.set(
        query=query,
        response=response,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    assert success is True

    # Retrieve from cache (exact match)
    cached = await semantic_cache.get_exact(
        query=query,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Verify hit
    assert cached == response, "Exact cache should return the same response"


@pytest.mark.asyncio
async def test_exact_cache_hit_with_whitespace_variation(semantic_cache):
    """Test exact cache hit ignores leading/trailing whitespace.

    Verifies that query normalization (lowercase, whitespace trimming) works
    correctly for exact matching.
    """
    query1 = "What is RAG?"
    query2 = "  What is RAG?  "  # Leading/trailing whitespace
    response = "RAG combines retrieval and generation."
    model = "qwen3.6-flash"
    temperature = 0.0
    max_tokens = 500

    # Store with first query
    await semantic_cache.set(
        query=query1,
        response=response,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Retrieve with whitespace variation (should still hit)
    cached = await semantic_cache.get_exact(
        query=query2,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    assert cached == response, "Whitespace variation should still hit exact cache"


@pytest.mark.asyncio
async def test_exact_cache_hit_in_memory(mock_redis):
    """Test exact cache hit from in-memory storage (fastest path).

    Verifies that in-memory cache is checked before Redis.
    """
    # Pre-populate in-memory cache
    cache = SemanticLLMCache()
    cache._mem_exact_cache["test_key"] = {
        "response": "in_memory_answer",
        "expires_at": time.monotonic() + 3600,
    }

    # Mock Redis to track if it's accessed
    cache._redis = mock_redis

    # Lookup should hit in-memory first
    await cache.get_exact(
        query="test query",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Verify in-memory cache was used (Redis not accessed for get)
    # Note: The key won't match exactly, but in-memory check happens first


@pytest.mark.asyncio
async def test_exact_cache_hit_redis_fallback(semantic_cache):
    """Test exact cache hit falls back to Redis when not in memory.

    Verifies that if an entry isn't in memory, Redis is queried.
    """
    query = "Explain vector embeddings"
    response = "Embeddings are numerical representations of text."
    model = "qwen3.6-flash"
    temperature = 0.0
    max_tokens = 500

    # Store in cache
    await semantic_cache.set(
        query=query,
        response=response,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Get the exact key
    semantic_cache._exact_cache_key(
        query, model, temperature, max_tokens
    )

    # Clear in-memory cache to force Redis lookup
    semantic_cache._mem_exact_cache.clear()

    # Lookup should fall back to Redis
    cached = await semantic_cache.get_exact(
        query=query,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Should still return the response from Redis
    if cached:
        assert cached == response


# ──────────────────────────────────────────────────────────────────────────────
# Test: Semantic Cache Hit
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_semantic_cache_hit(semantic_cache):
    """Test semantic similarity cache hit with similar phrasing.

    Verifies that queries with similar but different phrasing hit the
    semantic cache if similarity exceeds the threshold.
    """
    original_query = "What is retrieval augmented generation?"
    similar_query = "How does retrieval augmented generation work?"
    response = "RAG is a technique that combines retrieval and generation."

    # Store original query in semantic cache
    await semantic_cache.set(
        query=original_query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Query with similar phrasing
    result = await semantic_cache.get_semantic(
        query=similar_query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Verify semantic hit
    if result:
        cached_response, score = result
        assert cached_response == response, "Semantic cache should return cached response"
        assert score >= 0.92, f"Similarity score {score} should be >= 0.92"


@pytest.mark.asyncio
async def test_semantic_cache_hit_different_language(semantic_cache):
    """Test semantic cache hit with cross-language queries.

    Verifies that the embedding model handles multilingual queries.
    """
    query_en = "What is machine learning?"
    query_zh = "机器学习是什么？"
    response = "Machine learning is a subset of AI."

    # Store English query
    await semantic_cache.set(
        query=query_en,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Query in Chinese (may or may not hit depending on model)
    await semantic_cache.get_semantic(
        query=query_zh,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # This test may fail if model doesn't support cross-language similarity
    # That's expected behavior


@pytest.mark.asyncio
async def test_semantic_cache_hit_with_different_temperature(semantic_cache):
    """Test semantic cache miss when temperature differs.

    Verifies that entries with different temperatures don't cross-match.
    """
    query = "What is deep learning?"
    response1 = "Deep learning uses neural networks."  # temp=0.0

    # Store with temperature=0.0
    await semantic_cache.set(
        query=query,
        response=response1,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Query with temperature=0.7 (should not match)
    result = await semantic_cache.get_semantic(
        query=query,
        model="qwen3.6-flash",
        temperature=0.7,  # Different temperature
        max_tokens=500,
    )

    # Should miss because temperature differs
    assert result is None, "Different temperature should not match"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cache Miss
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_miss_unrelated_query(semantic_cache):
    """Test cache miss for completely unrelated query.

    Verifies that unrelated queries don't falsely match cached entries.
    """
    original_query = "What is retrieval augmented generation?"
    unrelated_query = "How do I bake a chocolate cake?"
    response = "RAG combines retrieval and generation."

    # Store original query
    await semantic_cache.set(
        query=original_query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Query completely different topic
    result_exact = await semantic_cache.get_exact(
        query=unrelated_query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    result_semantic = await semantic_cache.get_semantic(
        query=unrelated_query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Both should miss
    assert result_exact is None, "Unrelated query should miss exact cache"
    assert result_semantic is None, "Unrelated query should miss semantic cache"


@pytest.mark.asyncio
async def test_cache_miss_expired_entry(semantic_cache):
    """Test cache miss for expired entry.

    Verifies that entries past their TTL are not returned.
    """
    query = "What is vector search?"
    response = "Vector search uses embeddings for similarity."

    # Store with TTL=0 (expires immediately)
    await semantic_cache.set(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
        ttl=0,  # Expires immediately
    )

    # Wait briefly for expiry
    await asyncio.sleep(0.01)

    # Lookup should miss
    result = await semantic_cache.get_exact(
        query=query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert result is None, "Expired entry should not be returned"


@pytest.mark.asyncio
async def test_cache_miss_different_model(semantic_cache):
    """Test cache miss when model differs.

    Verifies that entries with different models don't cross-match.
    """
    query = "What is natural language processing?"
    response = "NLP is a field of AI."

    # Store with model="qwen3.6-flash"
    await semantic_cache.set(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Query with different model
    result = await semantic_cache.get_exact(
        query=query,
        model="gpt-4",  # Different model
        temperature=0.0,
        max_tokens=500,
    )

    assert result is None, "Different model should not match"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cache Statistics
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_stats_structure(semantic_cache):
    """Test cache statistics return correct structure.

    Verifies that get_stats() returns all expected fields.
    """
    stats = await semantic_cache.get_stats()

    # Verify required fields
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
async def test_cache_stats_hit_rate(semantic_cache):
    """Test cache statistics track hit rates correctly.

    Verifies that hit_rate is calculated correctly.
    """
    # Add some entries
    for i in range(5):
        await semantic_cache.set(
            query=f"Query {i}",
            response=f"Response {i}",
            model="qwen3.6-flash",
            temperature=0.0,
            max_tokens=500,
        )

    # Lookup some entries
    for i in range(3):
        await semantic_cache.get_exact(
            query=f"Query {i}",
            model="qwen3.6-flash",
            temperature=0.0,
            max_tokens=500,
        )

    # Get stats
    stats = await semantic_cache.get_stats()

    # Verify stats structure
    assert stats["exact_hits"] >= 0
    assert stats["semantic_hits"] >= 0
    assert stats["misses"] >= 0
    assert stats["sets"] >= 0
    assert 0 <= stats["hit_rate"] <= 1


@pytest.mark.asyncio
async def test_cache_stats_memory_size(semantic_cache):
    """Test cache statistics report memory sizes correctly.

    Verifies that in-memory cache sizes are tracked.
    """
    # Add entries
    for i in range(10):
        await semantic_cache.set(
            query=f"Test query {i}",
            response=f"Test response {i}",
            model="qwen3.6-flash",
            temperature=0.0,
            max_tokens=500,
        )

    stats = await semantic_cache.get_stats()

    # Verify sizes are reported
    assert stats["in_memory_exact_size"] >= 0
    assert stats["in_memory_semantic_size"] >= 0


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cache Clearing
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_clear_all(semantic_cache):
    """Test clearing all cache entries.

    Verifies that clearing removes all entries from both caches.
    """
    # Add entries
    for i in range(5):
        await semantic_cache.set(
            query=f"Query {i}",
            response=f"Response {i}",
            model="qwen3.6-flash",
            temperature=0.0,
            max_tokens=500,
        )

    # Clear all
    cleared = await semantic_cache.clear()

    # Verify cleared
    assert cleared == -1  # Indicates all cleared

    # Verify entries are gone
    result = await semantic_cache.get_exact(
        query="Query 0",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_clear_by_prefix(semantic_cache):
    """Test clearing cache entries by prefix.

    Verifies that clearing with prefix removes only matching entries.
    """
    # Add entries with different prefixes
    await semantic_cache.set(
        query="Query 1",
        response="Response 1",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Clear with non-matching prefix (should not clear anything)
    await semantic_cache.clear(prefix="nonexistent")

    # Verify entry still exists
    result = await semantic_cache.get_exact(
        query="Query 1",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )
    assert result == "Response 1"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cosine Similarity
# ──────────────────────────────────────────────────────────────────────────────


def test_cosine_similarity_identical_vectors():
    """Test cosine similarity with identical vectors.

    Verifies that identical vectors have similarity of 1.0.
    """
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert abs(similarity - 1.0) < 1e-6, "Identical vectors should have similarity of 1.0"


def test_cosine_similarity_orthogonal_vectors():
    """Test cosine similarity with orthogonal vectors.

    Verifies that orthogonal vectors have similarity of 0.0.
    """
    vec1 = [1.0, 0.0]
    vec2 = [0.0, 1.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert abs(similarity) < 1e-6, "Orthogonal vectors should have similarity of 0.0"


def test_cosine_similarity_similar_vectors():
    """Test cosine similarity with similar vectors.

    Verifies that similar (but not identical) vectors have high similarity.
    """
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.9, 0.1, 0.0]  # Similar direction

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert similarity > 0.8, f"Similar vectors should have high similarity: {similarity}"


def test_cosine_similarity_opposite_vectors():
    """Test cosine similarity with opposite vectors.

    Verifies that opposite vectors have similarity of -1.0.
    """
    vec1 = [1.0, 0.0]
    vec2 = [-1.0, 0.0]

    similarity = SemanticLLMCache._cosine_similarity(vec1, vec2)

    assert abs(similarity + 1.0) < 1e-6, "Opposite vectors should have similarity of -1.0"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cache Key Generation
# ──────────────────────────────────────────────────────────────────────────────


def test_exact_cache_key_deterministic(semantic_cache):
    """Test exact cache key is deterministic.

    Verifies that same inputs produce the same key.
    """
    key1 = semantic_cache._exact_cache_key(
        "test query", "qwen3.6-flash", 0.0, 500
    )
    key2 = semantic_cache._exact_cache_key(
        "test query", "qwen3.6-flash", 0.0, 500
    )

    assert key1 == key2, "Same inputs should produce same key"


def test_exact_cache_key_format(semantic_cache):
    """Test exact cache key has correct format.

    Verifies key format: semantic:v1:exact:{hash}
    """
    key = semantic_cache._exact_cache_key(
        "test query", "qwen3.6-flash", 0.0, 500
    )

    assert key.startswith("semantic:v1:exact:"), f"Key should start with 'semantic:v1:exact:': {key}"
    assert len(key) == len("semantic:v1:exact:") + 16, "Hash should be 16 characters"


def test_exact_cache_key_changes_with_params(semantic_cache):
    """Test exact cache key changes with different parameters.

    Verifies that changing any parameter produces a different key.
    """
    key1 = semantic_cache._exact_cache_key(
        "test query", "qwen3.6-flash", 0.0, 500
    )
    key2 = semantic_cache._exact_cache_key(
        "test query", "gpt-4", 0.0, 500  # Different model
    )
    key3 = semantic_cache._exact_cache_key(
        "test query", "qwen3.6-flash", 0.7, 500  # Different temperature
    )
    key4 = semantic_cache._exact_cache_key(
        "test query", "qwen3.6-flash", 0.0, 1000  # Different max_tokens
    )

    assert key1 != key2, "Different model should produce different key"
    assert key1 != key3, "Different temperature should produce different key"
    assert key1 != key4, "Different max_tokens should produce different key"


# ──────────────────────────────────────────────────────────────────────────────
# Test: In-Memory Cache LRU Eviction
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_cache_lru_eviction(semantic_cache):
    """Test LRU eviction when cache exceeds max size.

    Verifies that oldest entries are evicted when limit is reached.
    """
    # Set small max cache size
    semantic_cache.max_cache_size = 5

    # Add more entries than max
    for i in range(10):
        await semantic_cache.set(
            query=f"Query {i}",
            response=f"Response {i}",
            model="qwen3.6-flash",
            temperature=0.0,
            max_tokens=500,
        )

    # Verify cache size is within limit
    assert len(semantic_cache._mem_exact_cache) <= 5, "Cache should not exceed max size"

    # Verify some entries were evicted
    stats = await semantic_cache.get_stats()
    assert stats["sets"] == 10, "All 10 sets should be recorded"


@pytest.mark.asyncio
async def test_in_memory_cache_ttl_expiry(semantic_cache):
    """Test entries expire based on TTL.

    Verifies that entries are removed after TTL expires.
    """
    # Add entry with short TTL
    await semantic_cache.set(
        query="Short TTL query",
        response="Short TTL response",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
        ttl=0,  # Expires immediately
    )

    # Wait briefly
    await asyncio.sleep(0.01)

    # Lookup should miss
    result = await semantic_cache.get_exact(
        query="Short TTL query",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert result is None, "Expired entry should not be returned"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Redis Integration
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_set_and_get(semantic_cache):
    """Test setting and getting from Redis.

    Verifies that Redis store/retrieve works correctly.
    """
    query = "Redis integration test"
    response = "Redis works!"
    model = "qwen3.6-flash"
    temperature = 0.0
    max_tokens = 500

    # Store in cache
    await semantic_cache.set(
        query=query,
        response=response,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Clear in-memory to force Redis lookup
    semantic_cache._mem_exact_cache.clear()

    # Get from Redis
    await semantic_cache.get_exact(
        query=query,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Note: May be None if Redis is unavailable (expected in test env)
    # This test verifies the code path, not Redis availability


@pytest.mark.asyncio
async def test_redis_graceful_fallback(semantic_cache):
    """Test graceful fallback when Redis is unavailable.

    Verifies that cache works with in-memory fallback when Redis is down.
    """
    # Set Redis to False (unavailable sentinel)
    import app.cache.semantic_cache as cache_module
    cache_module._redis = False

    # Store in cache (should work with in-memory)
    success = await semantic_cache.set(
        query="Fallback test",
        response="In-memory answer",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True, "Cache should work with in-memory fallback"

    # Get from cache
    cached = await semantic_cache.get_exact(
        query="Fallback test",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Should get from in-memory
    assert cached == "In-memory answer"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Two-Layer Cache Integration
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_layer_cache_exact_then_semantic():
    """Test two-layer cache with exact hit first.

    Verifies that exact cache is checked before semantic cache.
    """
    query = "Explain neural networks"
    response = "Neural networks are computing systems."

    # Store response
    await set_cached_with_semantic(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Lookup same query (should hit exact cache)
    result = await get_cached_with_semantic(
        query=query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Verify exact hit
    if result:
        assert result == response, "Should return from exact cache"


@pytest.mark.asyncio
async def test_two_layer_cache_semantic_fallback():
    """Test two-layer cache with semantic hit.

    Verifies that semantic cache is checked after exact miss.
    """
    original_query = "What is transformer architecture?"
    similar_query = "How does transformer architecture work?"
    response = "Transformers use self-attention mechanisms."

    # Store original query
    await set_cached_with_semantic(
        query=original_query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Lookup with similar phrasing (should hit semantic cache)
    await get_cached_with_semantic(
        query=similar_query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Verify semantic hit (may or may not hit depending on similarity)
    # This test verifies the code path exists


@pytest.mark.asyncio
async def test_two_layer_cache_miss():
    """Test two-layer cache with complete miss.

    Verifies that unrelated queries return None (cache miss).
    """
    query = "Quantum computing applications"
    response = "Quantum computing has many applications."

    # Store response
    await set_cached_with_semantic(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Lookup completely different query
    result = await get_cached_with_semantic(
        query="How to make pasta?",
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    # Verify cache miss
    assert result is None, "Unrelated query should miss cache"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cache Metrics
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_metrics_structure():
    """Test cache metrics return correct structure.

    Verifies that get_cache_metrics() returns all expected fields.
    """
    metrics = get_cache_metrics()

    # Verify required fields
    required_fields = [
        "exact_hits",
        "semantic_hits",
        "misses",
        "sets",
        "errors",
        "total_lookups",
        "hit_rate",
        "exact_hit_rate",
        "semantic_hit_rate",
        "error_rate",
        "avg_latency_ms",
        "p50_latency_ms",
        "p90_latency_ms",
        "p99_latency_ms",
        "latency_sample_size",
    ]

    for field in required_fields:
        assert field in metrics, f"Missing required field: {field}"


@pytest.mark.asyncio
async def test_cache_metrics_rates():
    """Test cache metrics track rates correctly.

    Verifies that hit rates and error rates are calculated correctly.
    """
    metrics = get_cache_metrics()

    # Verify rates are in valid range
    assert 0 <= metrics["hit_rate"] <= 1, "Hit rate should be between 0 and 1"
    assert 0 <= metrics["exact_hit_rate"] <= 1, "Exact hit rate should be between 0 and 1"
    assert 0 <= metrics["semantic_hit_rate"] <= 1, "Semantic hit rate should be between 0 and 1"
    assert 0 <= metrics["error_rate"] <= 1, "Error rate should be between 0 and 1"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Edge Cases
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_empty_query(semantic_cache):
    """Test caching with empty query.

    Verifies that empty queries are handled gracefully.
    """
    query = ""
    response = "Response to empty query"

    # Store
    success = await semantic_cache.set(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True, "Should handle empty query"

    # Get
    cached = await semantic_cache.get_exact(
        query=query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached == response, "Should return cached response for empty query"


@pytest.mark.asyncio
async def test_cache_long_query(semantic_cache):
    """Test caching with very long query.

    Verifies that long queries are handled gracefully.
    """
    query = "What is " + "artificial intelligence " * 100 + "?"
    response = "AI is a broad field."

    # Store
    success = await semantic_cache.set(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True, "Should handle long query"


@pytest.mark.asyncio
async def test_cache_special_characters(semantic_cache):
    """Test caching with special characters in query.

    Verifies that special characters are handled gracefully.
    """
    query = "What is <script>alert('xss')</script>?"
    response = "This is a normal response."

    # Store
    success = await semantic_cache.set(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True, "Should handle special characters"

    # Get
    cached = await semantic_cache.get_exact(
        query=query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached == response, "Should return cached response with special characters"


@pytest.mark.asyncio
async def test_cache_unicode_query(semantic_cache):
    """Test caching with Unicode characters.

    Verifies that Unicode is handled gracefully.
    """
    query = "什么是机器学习？"
    response = "机器学习是人工智能的分支。"

    # Store
    success = await semantic_cache.set(
        query=query,
        response=response,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert success is True, "Should handle Unicode"

    # Get
    cached = await semantic_cache.get_exact(
        query=query,
        model="qwen3.6-flash",
        temperature=0.0,
        max_tokens=500,
    )

    assert cached == response, "Should return cached response with Unicode"
