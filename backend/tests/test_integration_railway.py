"""Integration tests for Railway benchmark (requires live API)."""

import os
import pytest
import asyncio


@pytest.mark.skipif(
    os.getenv("BENCHMARK_MODE") != "railway",
    reason="Railway mode not enabled"
)
@pytest.mark.asyncio
async def test_railway_health_check():
    """Test health check against live Railway API."""
    from app.benchmark import detect_environment, RailwayBenchmarkClient

    env = detect_environment()
    if not env.base_url:
        pytest.skip("RAILWAY_API_URL not set")

    client = RailwayBenchmarkClient(env.base_url, env.api_key)
    is_healthy = await client.health_check()
    await client.close()

    assert is_healthy, "Railway API health check failed"


@pytest.mark.skipif(
    os.getenv("BENCHMARK_MODE") != "railway",
    reason="Railway mode not enabled"
)
@pytest.mark.asyncio
async def test_railway_retrieve():
    """Test single query against live Railway API."""
    from app.benchmark import detect_environment, RailwayBenchmarkClient

    env = detect_environment()
    if not env.base_url:
        pytest.skip("RAILWAY_API_URL not set")

    client = RailwayBenchmarkClient(env.base_url, env.api_key)
    results = await client.retrieve("What is RAG?", top_k=3)
    await client.close()

    assert len(results) > 0, "No results returned"


@pytest.mark.skipif(
    os.getenv("BENCHMARK_MODE") != "railway",
    reason="Railway mode not enabled"
)
@pytest.mark.asyncio
async def test_railway_concurrent():
    """Test 10 concurrent requests against live Railway API."""
    from app.benchmark import detect_environment, RailwayBenchmarkClient, ConcurrencyTestSuite

    env = detect_environment()
    if not env.base_url:
        pytest.skip("RAILWAY_API_URL not set")

    client = RailwayBenchmarkClient(env.base_url, env.api_key)
    queries = ["What is RAG?", "How does vector search work?", "Explain embeddings"]

    suite = ConcurrencyTestSuite()
    result = await suite.test_http_concurrent(client, queries, concurrency=10)

    await client.close()

    assert result["success_rate"] >= 0.9, f"Success rate too low: {result['success_rate']}"
    assert result["qps"] > 0, "QPS should be positive"
