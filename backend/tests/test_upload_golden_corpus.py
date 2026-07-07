"""Regression tests for upload golden corpus fixtures and metrics."""

from pathlib import Path

from app.rag.ingestion.pipeline import build_chunks
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
