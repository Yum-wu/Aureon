"""Regression tests for the incremental ingest indexer."""

from unittest.mock import patch

from app.rag.indexer import run_incremental_index


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
