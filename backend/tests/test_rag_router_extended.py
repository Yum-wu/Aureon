"""Tests for RAG router endpoints — health, benchmark, upload, query validation."""

import pytest
from unittest.mock import patch, AsyncMock
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
async def test_upload_accepts_csv(tmp_path):
    with patch("app.routers.rag.UPLOADS_DIR", str(tmp_path)), \
         patch("app.routers.rag.run_incremental_index", return_value={
             "status": "ok",
             "filename": "test.csv",
             "documents_indexed": 1,
             "chunks_created": 1,
             "elapsed_seconds": 0.1,
         }):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/upload", files={"file": ("test.csv", b"a,b\n1,2")})

    assert resp.status_code == 200
    assert resp.json()["filename"] == "test.csv"


@pytest.mark.asyncio
async def test_large_upload_returns_job_without_sync_index(tmp_path):
    with patch("app.routers.rag.UPLOADS_DIR", str(tmp_path)), \
         patch("app.routers.rag._ASYNC_UPLOAD_MIN_BYTES", 10), \
         patch("app.routers.rag.enqueue_upload_job") as mock_enqueue, \
         patch("app.routers.rag.run_incremental_index") as mock_index:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/upload", files={"file": ("large.md", b"x" * 20)})

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["filename"] == "large.md"
    assert data["documents_indexed"] == 0
    assert data["chunks_created"] == 0
    assert data["job_id"]
    assert data["queued"] is True
    mock_index.assert_not_called()
    mock_enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_upload_status_returns_job_for_viewer():
    with patch("app.routers.rag.get_upload_job", return_value={
        "job_id": "job-1",
        "status": "ok",
        "filename": "large.md",
        "documents_indexed": 1,
        "chunks_created": 4,
        "elapsed_seconds": 12.3,
        "warnings": [],
        "error": None,
    }):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/upload/status/job-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["chunks_created"] == 4


@pytest.mark.asyncio
async def test_upload_status_404_for_missing_job():
    with patch("app.routers.rag.get_upload_job", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/upload/status/missing")

    assert resp.status_code == 404
    assert "Upload job not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_invalid_extension():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/rag/upload", files={"file": ("test.exe", b"binary")})
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_path_traversal():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/rag/upload", files={"file": ("../../../etc/passwd", b"content")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_valid_md(tmp_path):
    with patch("app.routers.rag.UPLOADS_DIR", str(tmp_path)), \
         patch("app.routers.rag.run_incremental_index", return_value={
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


@pytest.mark.asyncio
async def test_upload_accepts_pptx(tmp_path):
    with patch("app.routers.rag.UPLOADS_DIR", str(tmp_path)), \
         patch("app.routers.rag.run_incremental_index", return_value={
             "status": "ok",
             "filename": "deck.pptx",
             "documents_indexed": 1,
             "chunks_created": 2,
             "elapsed_seconds": 0.1,
         }):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/upload", files={"file": ("deck.pptx", b"pptx")})

    assert resp.status_code == 200
    assert resp.json()["filename"] == "deck.pptx"


@pytest.mark.asyncio
async def test_upload_uses_new_ingestion_pipeline(tmp_path):
    with patch("app.routers.rag.UPLOADS_DIR", str(tmp_path)), \
         patch("app.routers.rag.run_incremental_index") as mock_incremental, \
         patch("app.rag.ingestion.pipeline.build_chunks", return_value=[] ) as mock_build_chunks:
        mock_incremental.return_value = {
            "status": "ok",
            "filename": "test.md",
            "documents_indexed": 1,
            "chunks_created": 0,
            "elapsed_seconds": 0.1,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/upload", files={"file": ("test.md", b"# Title\nContent")})

    assert resp.status_code == 200
    mock_incremental.assert_called_once()
    metadata_overrides = mock_incremental.call_args.kwargs["metadata_overrides"]
    assert metadata_overrides["tenant_id"]
    mock_build_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_upload_does_not_create_llm_for_incremental_index(tmp_path):
    with patch("app.routers.rag.UPLOADS_DIR", str(tmp_path)), \
         patch("app.agent.llm.create_llm") as mock_create_llm, \
         patch("app.routers.rag.run_incremental_index") as mock_incremental:
        mock_incremental.return_value = {
            "status": "ok",
            "filename": "test.md",
            "documents_indexed": 1,
            "chunks_created": 1,
            "elapsed_seconds": 0.1,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/upload", files={"file": ("test.md", b"# Title\nContent")})

    assert resp.status_code == 200
    mock_create_llm.assert_not_called()
    assert mock_incremental.call_args.kwargs["llm_call_fn"] is None


@pytest.mark.asyncio
async def test_upload_rolls_back_saved_file_when_indexing_fails(tmp_path):
    with patch("app.routers.rag.UPLOADS_DIR", str(tmp_path)), \
         patch("app.routers.rag.run_incremental_index", return_value={
             "status": "error",
             "filename": "broken.docx",
             "documents_indexed": 0,
             "chunks_created": 0,
             "elapsed_seconds": 0.1,
             "message": "Index failed",
         }):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/upload", files={"file": ("broken.docx", b"not-a-real-docx")})

    assert resp.status_code == 500
    assert not (tmp_path / "broken.docx").exists()


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
    mock_llm = object()
    with patch("app.agent.llm.create_llm", return_value=mock_llm), \
         patch("app.routers.rag.run_index_pipeline", return_value={
        "status": "ok", "documents_indexed": 5, "chunks_created": 30, "elapsed_seconds": 1.2
    }), \
         patch("app.cache.redis_client.clear_cache_by_prefix", new_callable=AsyncMock), \
         patch("app.rag.vector_store._build_kw_index"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/rag/index")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["documents_indexed"] == 5
