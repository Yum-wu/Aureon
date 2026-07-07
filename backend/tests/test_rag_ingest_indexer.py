"""Regression tests for the incremental ingest indexer."""

from unittest.mock import patch

import pytest

from app.rag.indexer import run_incremental_index
from app.rag.ingestion.models import ChunkRecord


def test_run_incremental_index_rejects_blank_pdf_without_indexing(tmp_path):
    from pypdf import PdfWriter

    pdf_file = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(pdf_file, "wb") as f:
        writer.write(f)

    with patch("app.rag.vector_store.delete_from_index") as mock_delete, \
         patch("app.rag.vector_store.add_to_index") as mock_add:
        result = run_incremental_index(str(pdf_file))

    assert result["status"] == "error"
    assert result["chunks_created"] == 0
    assert result["warnings"] == [
        "PDF contains little or no extractable text; it may be scanned or image-based."
    ]
    mock_delete.assert_not_called()
    mock_add.assert_not_called()


def test_run_incremental_index_rejects_zero_chunks(tmp_path):
    md_file = tmp_path / "pipeline.md"
    md_file.write_text("---\ntitle: Pipeline\n---\n\nBody content.", encoding="utf-8")

    with patch("app.rag.loader.load_single_document") as mock_load, \
         patch("app.rag.ingestion.pipeline.build_chunks", return_value=[]) as mock_build, \
         patch("app.rag.vector_store.delete_from_index"), \
         patch("app.rag.vector_store.add_to_index") as mock_add:
        mock_load.return_value = {
            "metadata": {
                "source": "pipeline.md",
                "title": "Pipeline",
                "slug": "pipeline",
                "tags": [],
                "category": "upload",
                "filepath": str(md_file),
                "language": "en",
                "uploaded": True,
            },
            "content": "Body content.",
        }

        result = run_incremental_index(str(md_file))

    assert result["status"] == "error"
    assert result["chunks_created"] == 0
    assert "No indexable chunks" in result["message"]
    mock_load.assert_called_once()
    mock_build.assert_called_once()
    mock_add.assert_not_called()


def test_run_incremental_index_applies_metadata_overrides_before_indexing(tmp_path):
    md_file = tmp_path / "tenant.md"
    md_file.write_text("Tenant upload content.", encoding="utf-8")
    chunk = ChunkRecord(
        text="Tenant upload content for indexing.",
        metadata={"source": "tenant.md", "file_type": "md", "language": "unknown"},
    )

    with patch("app.rag.loader.load_single_document") as mock_load, \
         patch("app.rag.ingestion.pipeline.build_chunks", return_value=[chunk]), \
         patch("app.rag.vector_store.delete_from_index"), \
         patch("app.rag.vector_store.add_to_index") as mock_add:
        mock_load.return_value = {
            "metadata": {"source": "tenant.md", "title": "Tenant"},
            "content": "Tenant upload content.",
        }

        result = run_incremental_index(
            str(md_file),
            metadata_overrides={
                "tenant_id": "demo-tenant",
                "title": "Tenant Upload",
                "language": "en",
            },
        )

    assert result["status"] == "ok"
    indexed_chunks = mock_add.call_args.args[0]
    metadata = indexed_chunks[0]["metadata"]
    assert metadata["tenant_id"] == "demo-tenant"
    assert metadata["title"] == "Tenant Upload"
    assert metadata["language"] == "en"


def test_run_incremental_index_falls_back_when_contextual_prefix_fails(tmp_path):
    md_file = tmp_path / "fallback.md"
    md_file.write_text("Fallback upload content.", encoding="utf-8")
    chunk = ChunkRecord(
        text="Fallback upload content for indexing.",
        metadata={"source": "fallback.md", "file_type": "md"},
    )

    with patch("app.rag.loader.load_single_document") as mock_load, \
         patch("app.rag.ingestion.pipeline.build_chunks", return_value=[chunk]), \
         patch("app.rag.vector_store.delete_from_index"), \
         patch("app.rag.vector_store.add_to_index") as mock_add:
        mock_load.return_value = {
            "metadata": {"source": "fallback.md", "title": "Fallback"},
            "content": "Fallback upload content.",
        }

        result = run_incremental_index(
            str(md_file),
            llm_call_fn=lambda _: (_ for _ in ()).throw(RuntimeError("llm failed")),
        )

    assert result["status"] == "ok"
    assert result["contextual_prefixes"] == 0
    indexed_chunks = mock_add.call_args.args[0]
    assert indexed_chunks[0]["text"] == "Fallback upload content for indexing."


@pytest.mark.asyncio
async def test_run_incremental_index_skips_contextual_prefix_inside_running_loop(tmp_path):
    md_file = tmp_path / "async.md"
    md_file.write_text("Async upload content.", encoding="utf-8")
    chunk = ChunkRecord(
        text="Async upload content for indexing.",
        metadata={"source": "async.md", "file_type": "md"},
    )

    with patch("app.rag.loader.load_single_document") as mock_load, \
         patch("app.rag.ingestion.pipeline.build_chunks", return_value=[chunk]) as mock_build, \
         patch("app.rag.vector_store.delete_from_index"), \
         patch("app.rag.vector_store.add_to_index") as mock_add:
        mock_load.return_value = {
            "metadata": {"source": "async.md", "title": "Async"},
            "content": "Async upload content.",
        }

        result = run_incremental_index(str(md_file), llm_call_fn=lambda _: "prefix")

    assert result["status"] == "ok"
    assert result["chunks_created"] == 1
    assert result["contextual_prefixes"] == 0
    mock_build.assert_called_once()
    mock_add.assert_called_once()
