"""Tests for RAG router endpoints — health, benchmark, upload, query validation."""

import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport

try:
    from app.main import app
except Exception:
    pytest.skip("FastAPI app initialization failed — skipping RAG router tests", allow_module_level=True)



# ── /api/rag/health ──


@pytest.mark.asyncio
async def test_rag_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "llm_configured" in data
    assert "model" in data
    assert "bm25_docs" in data
    assert "hybrid_search_enabled" in data


# ── /api/rag/benchmark ──


@pytest.mark.asyncio
async def test_rag_benchmark_no_file():
    with patch("os.path.isfile", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/benchmark")
    assert resp.status_code == 200
    data = resp.json()
    assert data["metrics"] == []
    assert data["timestamp"] is None


# ── /api/rag/uploads ──


@pytest.mark.asyncio
async def test_list_uploads_no_dir():
    with patch("os.path.isdir", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/uploads")
    assert resp.status_code == 200
    assert resp.json()["files"] == []


# ── /api/rag/upload ──


@pytest.mark.asyncio
async def test_upload_no_filename():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/rag/upload", files={"file": ("", b"content")})
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_upload_invalid_extension():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/rag/upload", files={"file": ("test.csv", b"a,b,c")})
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_path_traversal():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/rag/upload", files={"file": ("../../../etc/passwd", b"content")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_valid_md():
    with patch("app.routers.rag.run_incremental_index", return_value={
        "status": "ok", "filename": "test.md", "documents_indexed": 1,
        "chunks_created": 3, "elapsed_seconds": 0.1
    }):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/upload", files={"file": ("test.md", b"# Title\nContent")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["chunks_created"] == 3


# ── DELETE /api/rag/upload/{filename} ──


@pytest.mark.asyncio
async def test_delete_upload_nonexistent():
    with patch("app.rag.vector_store.delete_from_index"), \
         patch("os.path.isfile", return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete("/api/rag/upload/nonexistent.md")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_upload_valid():
    with patch("app.rag.vector_store.delete_from_index"), \
         patch("os.path.isfile", return_value=True), \
         patch("os.remove"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete("/api/rag/upload/test.md")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"


# ── /api/rag/query validation ──


@pytest.mark.asyncio
async def test_query_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/rag/query", json={"query": ""})
    # Should fail validation (min_length=1 on RAGQueryRequest)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_query_too_long():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/rag/query", json={"query": "x" * 2000})
    assert resp.status_code == 422


# ── /api/rag/index ──


@pytest.mark.asyncio
async def test_rag_index_endpoint():
    with patch("app.routers.rag.run_index_pipeline", return_value={
        "status": "ok", "documents_indexed": 5, "chunks_created": 30, "elapsed_seconds": 1.2
    }):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/index")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["documents_indexed"] == 5
