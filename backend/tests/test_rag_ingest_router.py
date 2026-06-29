"""Regression tests for RAG upload router ingest behavior."""

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only")

from app.main import app


@pytest.mark.asyncio
async def test_upload_rejects_legacy_xls_until_explicitly_supported():
    with patch("app.routers.rag.settings") as mock_settings, \
         patch("app.routers.rag.run_incremental_index", return_value={
             "status": "ok",
             "filename": "legacy.xls",
             "documents_indexed": 1,
             "chunks_created": 2,
             "elapsed_seconds": 0.1,
             "metadata": {"source": "legacy.xls", "language": "en"},
         }) as mock_index:
        mock_settings.blog_sync_api_key = ""
        mock_settings.api_auth_key = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/rag/upload",
                files={
                    "file": (
                        "legacy.xls",
                        b"fake-xls-content",
                        "application/vnd.ms-excel",
                    )
                },
            )

    assert resp.status_code == 400
    assert "Unsupported format: .xls" in resp.json()["detail"]
    mock_index.assert_not_called()
