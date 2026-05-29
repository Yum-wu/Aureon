"""Tests for RAG router (POST /api/rag/query, POST /api/rag/query/stream,
GET /api/rag/health, GET /api/rag/benchmark)."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_rag_query_returns_response():
    """POST /api/rag/query returns RAG query response with answer and sources."""
    mock_result = MagicMock()
    mock_result.answer = "This is a test answer"
    mock_result.sources = []

    with patch("app.routers.rag.rag_query_with_cache", new_callable=AsyncMock, return_value=mock_result), \
         patch("app.agent.llm.create_llm", return_value=MagicMock()), \
         patch("app.routers.rag.record_query", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/rag/query",
                json={"query": "test question", "top_k": 3, "use_mmr": True},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["answer"] == "This is a test answer"


@pytest.mark.asyncio
async def test_rag_query_stream_returns_sse():
    """POST /api/rag/query/stream returns SSE with text/event-stream content type."""

    async def fake_astream(query, llm, top_k=3, use_mmr=True):
        yield {"type": "sources", "sources": []}
        yield {"type": "text", "content": "streamed answer"}
        yield {"type": "done"}

    with patch("app.routers.rag.rag_query_astream", side_effect=fake_astream), \
         patch("app.agent.llm.create_llm", return_value=MagicMock()), \
         patch("app.routers.rag.record_query", new_callable=AsyncMock), \
         patch("app.cache.redis_client.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.cache.redis_client.set_cached", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/rag/query/stream",
                json={"query": "test question", "top_k": 3, "use_mmr": True},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "streamed answer" in body


@pytest.mark.asyncio
async def test_rag_health():
    """GET /api/rag/health returns health status with required fields."""
    mock_bm25 = {"docs": 10, "terms": 100}

    with patch("app.rag.vector_store.get_bm25_stats", return_value=mock_bm25), \
         patch("app.routers.rag.settings") as mock_settings, \
         patch("app.routers.rag.os.path.isdir", return_value=True):
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "test-model"
        mock_settings.fallback_api_key = None
        mock_settings.langchain_api_key = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "llm_configured" in data
    assert "model" in data
    assert "index_status" in data
    assert "hybrid_search_enabled" in data


@pytest.mark.asyncio
async def test_rag_benchmark():
    """GET /api/rag/benchmark returns benchmark results structure."""
    with patch("app.routers.rag.os.path.isfile", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/benchmark")

    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert data["metrics"] == []
    assert data["timestamp"] is None
