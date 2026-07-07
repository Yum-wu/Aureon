"""Regression tests for upload golden corpus fixtures and metrics."""

from pathlib import Path

from app.rag.ingestion.pipeline import build_chunks
from app.rag.index_manager import _add_to_index_qdrant
from tests.upload_golden_corpus import (
    UPLOAD_GOLDEN_CASES,
    create_upload_golden_files,
    evaluate_upload_search_results,
)


def test_upload_golden_cases_cover_supported_formats():
    assert [case.file_type for case in UPLOAD_GOLDEN_CASES] == [
        "csv",
        "docx",
        "md",
        "pdf",
        "pptx",
        "txt",
        "xlsx",
    ]
    assert len({case.sentinel for case in UPLOAD_GOLDEN_CASES}) == len(UPLOAD_GOLDEN_CASES)


def test_upload_golden_files_are_extractable(tmp_path: Path):
    files = create_upload_golden_files(tmp_path)

    assert set(files) == {case.file_type for case in UPLOAD_GOLDEN_CASES}
    for case in UPLOAD_GOLDEN_CASES:
        path = files[case.file_type]
        assert path.name == case.filename
        assert path.exists()

        chunks = build_chunks(path)
        combined = "\n".join(chunk.text for chunk in chunks)
        assert case.sentinel in combined


def test_evaluate_upload_search_results_requires_rank_one():
    results = {
        "csv": {"sources": [{"slug": "aureon-golden-csv"}]},
        "docx": {"sources": [{"slug": "wrong"}, {"slug": "aureon-golden-docx"}]},
        "md": {"sources": []},
    }
    cases = [case for case in UPLOAD_GOLDEN_CASES if case.file_type in results]

    metrics = evaluate_upload_search_results(cases, results)

    assert metrics["total"] == 3
    assert metrics["matched"] == 2
    assert metrics["rank1"] == 1
    assert metrics["recall_at_k"] == 2 / 3
    assert metrics["rank1_rate"] == 1 / 3
    assert metrics["failures"] == [
        {
            "file_type": "docx",
            "sentinel": "AUREON_GOLDEN_SENTINEL_DOCX_20260706",
            "expected_slug": "aureon-golden-docx",
            "rank": 2,
            "top": "wrong",
        },
        {
            "file_type": "md",
            "sentinel": "AUREON_GOLDEN_SENTINEL_MD_20260706",
            "expected_slug": "aureon-golden-md",
            "rank": None,
            "top": None,
        },
    ]


def test_incremental_qdrant_add_batches_embedding_requests(monkeypatch):
    """Large uploads must not send all chunks to one embedding request."""
    calls = []
    upserts = []

    class DummyClient:
        def upsert(self, *, collection_name, points):
            upserts.append((collection_name, len(points)))

    def fake_embed(texts, *_, **__):
        calls.append(len(texts))

        class Emb:
            def __init__(self, value):
                self.value = value

            def tolist(self):
                return [float(self.value)]

        return [Emb(i) for i, _ in enumerate(texts)]

    monkeypatch.setattr("app.rag.index_manager._get_qdrant", lambda: DummyClient(), raising=False)
    monkeypatch.setattr("app.rag.qdrant_ops._get_qdrant", lambda: DummyClient())
    monkeypatch.setattr("app.rag.qdrant_ops._get_qdrant_collection_name", lambda: "test")
    monkeypatch.setattr("app.rag.index_manager._get_qdrant_collection_name", lambda: "test", raising=False)
    monkeypatch.setattr("app.rag.index_manager.settings.embedding.sparse_enabled", False)
    monkeypatch.setattr("app.rag.index_manager.embed_texts_llm", fake_embed, raising=False)
    monkeypatch.setattr("app.rag.embedding.embed_texts_llm", fake_embed)
    monkeypatch.setattr("app.rag.bm25._build_kw_index", lambda **_: None)

    chunks = [
        {"text": f"row {i} " + ("x" * 1200), "metadata": {"source": "large.csv"}}
        for i in range(25)
    ]

    _add_to_index_qdrant(chunks)

    assert len(calls) > 1
    assert max(calls) <= 10
    assert sum(calls) == len(chunks)
    assert sum(count for _, count in upserts) == len(chunks)
