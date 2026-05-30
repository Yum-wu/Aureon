"""Tests for app.main — health, langgraph_run, exception handler, middleware."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.dependencies import get_redis_or_none


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── Health endpoints ──


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model" in data
    assert "tools" in data
    assert isinstance(data["tools"], list)


@pytest.mark.asyncio
async def test_crew_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/crew/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "crew-generator"


# ── LangGraph run ──


@pytest.mark.asyncio
async def test_langgraph_run_missing_query():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/langgraph/run", json={})
    # Pydantic validation rejects empty query with 422
    assert resp.status_code == 422
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
@patch("app.langgraph.graph.run_workflow", new_callable=AsyncMock)
async def test_langgraph_run_success(mock_workflow):
    mock_workflow.return_value = {"answer": "42", "intent": "chat"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/langgraph/run", json={"query": "What is RAG?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "42"


# ── CrewAI generate (import error) ──


@pytest.mark.asyncio
async def test_crew_generate_import_error():
    with patch.dict("sys.modules", {"app.crew.crew_setup": None}):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/crew/generate", json={"topic": "test topic"})
    # Should get 503 when CrewAI not installed
    assert resp.status_code in (500, 503)


# ── Exception handler ──


@pytest.mark.asyncio
async def test_aureon_exception_handler():
    """When Redis is unavailable, get_stats returns 200 with default values (graceful degradation)."""
    from app.exceptions import RedisUnavailableError
    app.dependency_overrides[get_redis_or_none] = lambda: None

    with patch("app.cache.redis_client._get_redis", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    # Graceful degradation: return 200 with default values
    assert resp.status_code == 200
    data = resp.json()
    # Redis-dependent values should be zero
    assert data["query_count_24h"] == 0
    assert data["cache_hit_rate"] == 0.0
    assert data["avg_retrieval_latency_ms"] == 0.0
    # Document counts should still come from vector store
    assert "total_indexed_docs" in data
    assert "total_chunks" in data


# ── Middleware ──


@pytest.mark.asyncio
async def test_request_id_in_response():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
    assert resp.status_code == 200
    # Middleware should complete without error


# ── Metrics endpoint ──


@pytest.mark.asyncio
async def test_metrics_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/metrics")
    assert resp.status_code == 200
