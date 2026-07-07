"""Regression tests for RAG document ingest loader behavior."""

import pytest

from app.rag.ingestion.extractors import (
    STRUCTURED_CHUNK_MAX_CHARS,
    STRUCTURED_CHUNK_MAX_ESTIMATED_TOKENS,
    _estimate_embedding_tokens,
    extract_csv_document,
    extract_docx_document,
    extract_markdown_document,
    extract_pdf_document,
    extract_text_document,
    extract_xlsx_document,
)
from app.rag.ingestion.pipeline import build_chunks
from app.rag.ingestion.models import ChunkRecord, IngestedDocument
from app.rag.ingestion.normalizer import normalize_text
from app.rag.ingestion.policy import split_with_policy
from app.rag.ingestion.quality import DEFAULT_MIN_CHUNK_LEN, is_valid_chunk
from app.rag.loader import load_single_document


class TestLoadSingleDocumentMetadataContract:
    def test_markdown_upload_contract(self, tmp_path):
        md_file = tmp_path / "contract.md"
        md_file.write_text(
            "---\ntitle: Contract Title\nslug: contract-slug\ntags: [AI, RAG]\ncategory: docs\n---\n\nBody content.",
            encoding="utf-8",
        )

        result = load_single_document(str(md_file))

        assert result["content"] == "Body content."
        assert result["metadata"] == {
            "source": "contract.md",
            "title": "Contract Title",
            "slug": "contract-slug",
            "tags": ["AI", "RAG"],
            "category": "docs",
            "filepath": str(md_file),
            "language": "en",
            "uploaded": True,
        }

    def test_xls_is_explicitly_unsupported(self, tmp_path):
        xls_file = tmp_path / "legacy.xls"
        xls_file.write_bytes(b"fake-xls")

        with pytest.raises(ValueError, match="Unsupported file type: \\.xls"):
            load_single_document(str(xls_file))


class TestIngestionPrimitives:
    def test_normalize_text_collapses_blank_lines_without_flattening_spaces(self):
        text = "A\r\n\r\n\r\nB   \n"
        assert normalize_text(text) == "A\n\nB"

    def test_normalize_text_keeps_code_block_indentation_and_inner_spaces(self):
        text = "```python\r\n  def foo():\r\n      return  1\r\n```\r\n\r\nBody"
        assert normalize_text(text) == "```python\n  def foo():\n      return  1\n```\n\nBody"

    def test_is_valid_chunk_rejects_short_text(self):
        assert is_valid_chunk("hi") is False

    def test_is_valid_chunk_uses_shared_default_threshold(self):
        assert DEFAULT_MIN_CHUNK_LEN == 100

    def test_dataclasses_expose_expected_fields(self):
        doc = IngestedDocument(metadata={"source": "a.md"}, content="Body")
        chunk = ChunkRecord(text="Chunk", metadata={"source": "a.md"})

        assert doc.metadata["source"] == "a.md"
        assert doc.content == "Body"
        assert chunk.text == "Chunk"
        assert chunk.metadata["source"] == "a.md"

    def test_extractors_preserve_expected_metadata(self, tmp_path):
        md_file = tmp_path / "extract.md"
        txt_file = tmp_path / "plain.txt"
        pdf_file = tmp_path / "doc.pdf"
        docx_file = tmp_path / "doc.docx"
        xlsx_file = tmp_path / "doc.xlsx"

        md_file.write_text("---\ntitle: Extract Title\nslug: extract-slug\n---\n\nBody text.", encoding="utf-8")
        txt_file.write_text("Plain text content.", encoding="utf-8")
        pdf_file.write_bytes(b"pdf")
        docx_file.write_bytes(b"docx")
        xlsx_file.write_bytes(b"xlsx")

        md_doc = extract_markdown_document(md_file)
        txt_doc = extract_text_document(txt_file)

        assert md_doc.metadata["title"] == "Extract Title"
        assert md_doc.metadata["slug"] == "extract-slug"
        assert md_doc.metadata["file_type"] == "md"
        assert md_doc.content == "Body text."

        assert txt_doc.metadata["title"] == "plain"
        assert txt_doc.metadata["file_type"] == "txt"
        assert txt_doc.content == "Plain text content."

        with pytest.raises(Exception):
            extract_pdf_document(pdf_file)
        with pytest.raises(Exception):
            extract_docx_document(docx_file)
        with pytest.raises(Exception):
            extract_xlsx_document(xlsx_file)

    def test_split_with_policy_falls_back_to_single_chunk(self):
        doc = IngestedDocument(metadata={"source": "a.md", "file_type": "md"}, content="x" * 150)
        chunks = split_with_policy("md", doc)

        assert len(chunks) == 1
        assert chunks[0].metadata["chunk_idx"] == 0

    def test_build_chunks_keeps_normal_english_upload_text(self, tmp_path):
        txt_file = tmp_path / "customer-feedback.txt"
        txt_file.write_text(
            (
                "Voice of the Customer research captures unsolicited customer feedback "
                "from support conversations, surveys, and social media posts. "
                "Product teams use these signals to prioritize roadmap decisions, "
                "identify churn risk, and improve onboarding for enterprise accounts. "
            )
            * 8,
            encoding="utf-8",
        )

        chunks = build_chunks(txt_file)

        assert chunks
        assert "Voice of the Customer" in chunks[0].text

    def test_csv_extractor_batches_short_rows_by_size_not_fixed_row_count(self, tmp_path):
        csv_file = tmp_path / "sales.csv"
        rows = ["region,customer,product,revenue"]
        rows.extend(
            f"Central,{index},Paseo,{1000 + index}"
            for index in range(120)
        )
        csv_file.write_text("\n".join(rows), encoding="utf-8")

        chunks = extract_csv_document(csv_file)

        assert len(chunks) <= 4
        assert chunks[0].metadata["row_start"] == 2
        assert chunks[-1].metadata["row_end"] == 121
        assert "Columns: region, customer, product, revenue" in chunks[0].text
        assert "Central, 119, Paseo, 1119" in chunks[-1].text
        assert all(_estimate_embedding_tokens(chunk.text) <= STRUCTURED_CHUNK_MAX_ESTIMATED_TOKENS for chunk in chunks)

    def test_csv_extractor_keeps_large_business_csv_chunk_count_bounded(self, tmp_path):
        csv_file = tmp_path / "businesses.csv"
        rows = ["Business Name,Community Board,Council District,BIN,BBL,Latitude,Longitude"]
        rows.extend(
            f"GEM FINANCIAL SERVICES {index},105,03,1014495,1007890005,40.75561,-73.990962"
            for index in range(1000)
        )
        csv_file.write_text("\n".join(rows), encoding="utf-8")

        chunks = extract_csv_document(csv_file)

        assert len(chunks) <= 100
        assert all(len(chunk.text) <= STRUCTURED_CHUNK_MAX_CHARS for chunk in chunks)
        assert all(_estimate_embedding_tokens(chunk.text) <= STRUCTURED_CHUNK_MAX_ESTIMATED_TOKENS for chunk in chunks)
        assert STRUCTURED_CHUNK_MAX_ESTIMATED_TOKENS <= 1800
        assert sum(len(chunk.text) for chunk in chunks) < 120000

    def test_csv_extractor_does_not_merge_provider_sensitive_long_rows(self, tmp_path):
        csv_file = tmp_path / "provider-sensitive.csv"
        row = (
            "Define security requirements for organization-developed software "
            "and maintain these requirements across the SDLC. "
        ) * 7
        csv_file.write_text(
            "id,content\n" + "\n".join(f"{index},{row}" for index in range(5)),
            encoding="utf-8",
        )

        chunks = extract_csv_document(csv_file)

        assert len(chunks) <= 5
        assert all(_estimate_embedding_tokens(chunk.text) <= STRUCTURED_CHUNK_MAX_ESTIMATED_TOKENS for chunk in chunks)

    def test_build_chunks_does_not_index_csv_without_header(self, tmp_path):
        csv_file = tmp_path / "no-header.csv"
        csv_file.write_text("APAC,1200\nEMEA,900\n", encoding="utf-8")

        chunks = build_chunks(csv_file)

        assert chunks == []
