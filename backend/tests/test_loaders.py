"""Tests for multi-format document loaders (PDF, DOCX, Excel)."""
import pytest


class TestLoadPdf:
    def test_load_pdf_extracts_text(self, tmp_path):
        """PDF with text content should be extracted."""
        from pypdf import PdfWriter
        from app.rag.loader import load_pdf

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        path = str(tmp_path / "test.pdf")
        with open(path, "wb") as f:
            writer.write(f)

        result = load_pdf(path)
        assert "content" in result
        assert "metadata" in result
        assert result["metadata"]["source"] == "test.pdf"
        assert result["metadata"]["file_type"] == "pdf"

    def test_load_docx_extracts_paragraphs(self, tmp_path):
        """DOCX paragraphs should be extracted as text."""
        from docx import Document
        from app.rag.loader import load_docx

        doc = Document()
        doc.add_paragraph("This is a test document with English content.")
        doc.add_paragraph("Second paragraph here.")
        path = str(tmp_path / "test.docx")
        doc.save(path)

        result = load_docx(path)
        assert "test document" in result["content"].lower()
        assert "second paragraph" in result["content"].lower()
        assert result["metadata"]["language"] == "en"
        assert result["metadata"]["file_type"] == "docx"

    def test_load_docx_chinese_content(self, tmp_path):
        """DOCX with Chinese content should detect language as zh."""
        from docx import Document
        from app.rag.loader import load_docx

        doc = Document()
        doc.add_paragraph("这是一份中文测试文档，用于验证语言检测功能。")
        path = str(tmp_path / "chinese.docx")
        doc.save(path)

        result = load_docx(path)
        assert result["metadata"]["language"] == "zh"

    def test_load_excel_converts_rows(self, tmp_path):
        """Excel rows should be converted to 'col: value' text."""
        from openpyxl import Workbook
        from app.rag.loader import load_excel

        wb = Workbook()
        ws = wb.active
        ws.append(["Name", "Age", "City"])
        ws.append(["Alice", 30, "Beijing"])
        ws.append(["Bob", 25, "Shanghai"])
        path = str(tmp_path / "test.xlsx")
        wb.save(path)

        result = load_excel(path)
        assert "Name" in result["content"]
        assert "Alice" in result["content"]
        assert "Beijing" in result["content"]
        assert result["metadata"]["file_type"] == "xlsx"

    def test_load_single_document_dispatches_docx(self, tmp_path):
        """load_single_document should handle .docx files."""
        from docx import Document
        from app.rag.loader import load_single_document

        doc = Document()
        doc.add_paragraph("Test content for dispatch.")
        path = str(tmp_path / "dispatch.docx")
        doc.save(path)

        result = load_single_document(path)
        assert result["metadata"]["source"] == "dispatch.docx"
        assert "dispatch" in result["content"].lower() or "test content" in result["content"].lower()
        assert result["metadata"]["uploaded"] is True

    def test_load_single_document_dispatches_xlsx(self, tmp_path):
        """load_single_document should handle .xlsx files."""
        from openpyxl import Workbook
        from app.rag.loader import load_single_document

        wb = Workbook()
        ws = wb.active
        ws.append(["Col1", "Col2"])
        ws.append(["A", "B"])
        path = str(tmp_path / "data.xlsx")
        wb.save(path)

        result = load_single_document(path)
        assert result["metadata"]["source"] == "data.xlsx"
        assert "A" in result["content"]

    def test_unsupported_extension_raises(self, tmp_path):
        """Unsupported file types should raise ValueError."""
        from app.rag.loader import load_single_document

        path = str(tmp_path / "test.csv")
        with open(path, "w") as f:
            f.write("a,b,c")

        with pytest.raises(ValueError, match="Unsupported"):
            load_single_document(path)
