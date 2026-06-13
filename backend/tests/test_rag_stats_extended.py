"""Tests for rag_stats helper functions and documents API."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.dependencies import get_redis_or_none
from app.api.rag_stats import _classify_intent, record_query


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── _classify_intent ──


class TestClassifyIntent:
    def test_code_search(self):
        assert _classify_intent("How to implement API?") == "code_search"
        assert _classify_intent("这个函数怎么用") == "code_search"

    def test_document_query(self):
        assert _classify_intent("上传文档") == "document_query"
        assert _classify_intent("list documents") == "document_query"

    def test_general_qa(self):
        assert _classify_intent("What is RAG?") == "general_qa"
        assert _classify_intent("你好") == "general_qa"


# ── record_query ──


@pytest.mark.asyncio
async def test_record_query_no_redis():
    with patch("app.api.rag_stats.get_redis_or_none", return_value=None):
        # Should not raise
        await record_query("test", sources_count=3, latency_ms=100)


@pytest.mark.asyncio
async def test_record_query_with_redis():
    # Pipeline 方法（incr/lpush/ltrim 等）在真实 Redis 中是同步链式调用，
    # 返回 pipeline 自身。Mock 为同步方法避免 "coroutine was never awaited" 警告。
    mock_pipe = MagicMock()
    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=False)
    mock_pipe.execute = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)

    with patch("app.api.rag_stats.get_redis_or_none", return_value=mock_redis):
        await record_query("test query", sources_count=2, latency_ms=150.5,
                          input_tokens=100, output_tokens=50)

    mock_pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_record_query_pipeline_error():
    mock_pipe = MagicMock()
    mock_pipe.__aenter__ = AsyncMock(side_effect=ConnectionError("down"))
    mock_pipe.__aexit__ = AsyncMock(return_value=False)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)

    with patch("app.api.rag_stats.get_redis_or_none", return_value=mock_redis):
        # Should not raise — error is logged
        await record_query("test", sources_count=1, latency_ms=50)





@pytest.mark.asyncio
async def test_get_documents_qdrant_empty():
    """Qdrant backend: empty collection returns empty documents."""
    mock_client = MagicMock()
    mock_info = MagicMock()
    mock_info.points_count = 0
    mock_client.get_collection.return_value = mock_info

    with patch("app.api.rag_stats._get_documents_qdrant") as mock_qdrant:
        mock_qdrant.return_value = {"documents": [], "total_docs": 0, "total_chunks": 0}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/documents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["documents"] == []
    assert data["total_docs"] == 0


@pytest.mark.asyncio
async def test_get_documents_qdrant_with_data():
    """Qdrant backend: returns documents from Qdrant scroll."""
    with patch("app.api.rag_stats._get_documents_qdrant") as mock_qdrant:
        mock_qdrant.return_value = {
            "documents": [
                {"title": "RAG Guide", "source": "guide.md", "file_type": "md",
                 "language": "zh", "chunk_count": 5, "status": "ready"},
            ],
            "total_docs": 1, "total_chunks": 5,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/documents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_docs"] == 1
    assert data["total_chunks"] == 5
    assert data["documents"][0]["source"] == "guide.md"


# ── Stats edge cases ──


@pytest.mark.asyncio
async def test_get_stats_vector_store_error():
    """When vector store fails, returns 200 with zero document counts (graceful degradation)."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="10")
    mock_redis.zrange = AsyncMock(return_value=[("entry1", 100.0)])

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    with patch("app.api.rag_stats.get_collection_stats", side_effect=RuntimeError("vs down")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    # Graceful degradation: return 200 with zero document counts
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_indexed_docs"] == 0
    assert data["total_chunks"] == 0
    # Redis-dependent values should still be available
    assert data["query_count_24h"] == 10
    assert data["avg_retrieval_latency_ms"] == 100.0


@pytest.mark.asyncio
async def test_get_stats_redis_read_error():
    """When Redis raises an exception, returns 200 with default values (graceful degradation)."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("timeout"))

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/stats")

    # Graceful degradation: return 200 with default values
    assert resp.status_code == 200
    data = resp.json()
    assert data["query_count_24h"] == 0
    assert data["cache_hit_rate"] == 0.0
    assert data["avg_retrieval_latency_ms"] == 0.0
    # Document counts should come from vector store
    assert "total_indexed_docs" in data
    assert "total_chunks" in data


@pytest.mark.asyncio
async def test_get_recent_queries_redis_error():
    """When Redis raises an exception, returns 200 with empty list (graceful degradation)."""
    mock_redis = AsyncMock()
    mock_redis.lrange = AsyncMock(side_effect=ConnectionError("timeout"))

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/queries/recent")

    # Graceful degradation: return 200 with empty list
    assert resp.status_code == 200
    data = resp.json()
    assert "queries" in data
    assert data["queries"] == []
