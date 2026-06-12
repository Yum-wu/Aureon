"""Tests for RAG router (POST /api/rag/query, POST /api/rag/query/stream,
GET /api/rag/health, GET /api/rag/benchmark)."""

import os
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only")

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture(autouse=True)
def _bypass_rbac():
    """Bypass all require_role RBAC checks during tests.

    Iterates over every router on the FastAPI app, finds Depends() that
    reference require_role(...) closures, and replaces them with a mock
    that always returns an ADMIN user.
    """
    from app.security import UserRole
    mock_user = {"sub": "test-user", "role": "ADMIN", "_role": UserRole.ADMIN}

    # Collect all dependency overrides needed
    overrides = {}
    for route in app.routes:
        if not hasattr(route, "dependant"):
            continue
        for dep in route.dependant.dependencies:
            call = dep.call
            # require_role returns a _role_checker closure
            if getattr(call, "__name__", "") == "_role_checker":
                async def _mock_admin(_original_call=call):
                    return mock_user
                overrides[call] = _mock_admin

    # Apply overrides
    for dep_func, mock_func in overrides.items():
        app.dependency_overrides[dep_func] = mock_func

    yield

    # Clean up
    for dep_func in overrides:
        app.dependency_overrides.pop(dep_func, None)


@pytest.mark.asyncio
async def test_rag_query_returns_response():
    """POST /api/rag/query returns RAG query response with answer and sources."""
    mock_result = MagicMock()
    mock_result.answer = "This is a test answer"
    mock_result.sources = []

    # Mock the actual settings module that the endpoint imports
    with patch("app.routers.rag.rag_query_with_cache", new_callable=AsyncMock, return_value=mock_result), \
         patch("app.agent.llm.create_llm", return_value=MagicMock()), \
         patch("app.routers.rag.record_query", new_callable=AsyncMock), \
         patch("app.routers.rag._ensure_index_ready", new_callable=AsyncMock, return_value=True), \
         patch("app.config.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.fallback_api_key = None
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

    async def fake_astream(query, llm, top_k=3, use_mmr=True, filter_lang=None):
        yield {"type": "sources", "sources": []}
        yield {"type": "text", "content": "streamed answer"}
        yield {"type": "done"}

    # Mock the actual settings module that the endpoint imports
    with patch("app.routers.rag.rag_query_astream", side_effect=fake_astream), \
         patch("app.agent.llm.create_llm", return_value=MagicMock()), \
         patch("app.routers.rag.record_query", new_callable=AsyncMock), \
         patch("app.routers.rag._ensure_index_ready", new_callable=AsyncMock, return_value=True), \
         patch("app.cache.redis_client.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.cache.redis_client.set_cached", new_callable=AsyncMock), \
         patch("app.config.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.fallback_api_key = None
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


@pytest.mark.asyncio
async def test_upload_requires_api_key_when_configured():
    """When BLOG_SYNC_API_KEY is set, upload requires valid API key."""
    import io
    import os

    # Mock file upload
    mock_file = MagicMock()
    mock_file.filename = "test.md"
    mock_file.read = AsyncMock(return_value=b"# Test content")

    # Mock the actual settings module — must patch where it's used
    with patch("app.routers.rag.settings") as mock_settings, \
         patch("app.routers.rag.run_incremental_index") as mock_index, \
         patch("app.routers.rag.os.makedirs"), \
         patch("app.routers.rag.os.path.join", return_value="/tmp/test.md"), \
         patch("builtins.open", MagicMock()):
        mock_settings.llm_api_key = "test-key"
        mock_settings.api_auth_key = None  # Skip API key auth in test
        mock_index.return_value = {
            "status": "ok",
            "chunks_created": 1,
            "filename": "test.md",
            "elapsed_seconds": 0.5,
        }

        transport = ASGITransport(app=app)

        # Test 1: No API key when required → 401
        mock_settings.blog_sync_api_key = "secret-key"
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/rag/upload",
                files={"file": ("test.md", b"# Test", "text/markdown")},
                data={"language": "en", "title": "Test"},
            )
        assert resp.status_code == 401
        assert "Invalid API key" in resp.json()["detail"]

        # Test 2: Wrong API key → 401
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/rag/upload",
                files={"file": ("test.md", b"# Test", "text/markdown")},
                data={"language": "en", "title": "Test", "api_key": "wrong-key"},
            )
        assert resp.status_code == 401

        # Test 3: Correct API key → 200
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/rag/upload",
                files={"file": ("test.md", b"# Test", "text/markdown")},
                data={"language": "en", "title": "Test", "api_key": "secret-key"},
            )
        assert resp.status_code == 200

        # Test 4: No API key required → 200 (backward compatible)
        mock_settings.blog_sync_api_key = ""
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/rag/upload",
                files={"file": ("test.md", b"# Test", "text/markdown")},
                data={"language": "en", "title": "Test"},
            )
        assert resp.status_code == 200
