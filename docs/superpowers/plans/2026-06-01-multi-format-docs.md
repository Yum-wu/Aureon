# Multi-Format Docs + Language Filter + Production Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support PDF/DOCX/Excel uploads, auto-filter by language, fix production stale-chunk error, optimize cold-start UX.

**Architecture:** Add format-specific parsers to `loader.py` (pypdf, python-docx, openpyxl), wire existing `lang_filter` through API layer (already in qa_chain/vector_store), fix deployment by triggering fresh Railway build, add BGE model preload in startup.

**Tech Stack:** pypdf, python-docx, openpyxl, FastAPI, React, i18next

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/requirements.txt` | Modify | Add pypdf, python-docx, openpyxl |
| `backend/app/rag/loader.py` | Modify | Add load_pdf(), load_docx(), load_excel() |
| `backend/app/routers/rag.py` | Modify | Expand allowed upload extensions |
| `backend/app/rag/models.py` | Modify | Add language field to RAGQueryRequest |
| `backend/app/rag/qa_chain.py` | Modify | Add filter_lang to rag_query_with_cache |
| `backend/app/api/rag_stats.py` | Modify | Add language field to DocumentItem, file_type for docx/xlsx |
| `backend/tests/test_loaders.py` | Create | Unit tests for new loaders |
| `backend/tests/test_language_filter.py` | Create | Integration test for language filtering |
| `src/components/documents/DocumentUpload.tsx` | Modify | Accept .pdf,.docx,.xlsx |
| `src/pages/Documents.tsx` | Modify | Add type badges for docx/xlsx, language filter |
| `src/services/rag.ts` | Modify | Pass language param in query stream |
| `src/i18n/en.json` | Modify | Add docx/xlsx/i18n keys |
| `src/i18n/zh.json` | Modify | Add docx/xlsx/i18n keys |

---

### Task 1: Install Python Dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add dependencies to requirements.txt**

Append at end of `backend/requirements.txt`:
```
# Document format parsers
pypdf>=4.0,<6.0
python-docx>=1.1,<2.0
openpyxl>=3.1,<4.0
```

- [ ] **Step 2: Install and verify**

Run: `cd backend && pip install pypdf python-docx openpyxl && python3 -c "import pypdf; import docx; import openpyxl; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: add pypdf, python-docx, openpyxl for multi-format support"
```

---

### Task 2: Add PDF/DOCX/Excel Loaders with Tests

**Files:**
- Create: `backend/tests/test_loaders.py`
- Modify: `backend/app/rag/loader.py`

- [ ] **Step 1: Write failing tests for each loader**

Create `backend/tests/test_loaders.py`:
```python
"""Tests for multi-format document loaders."""
import os
import tempfile
import pytest


def _tmp(content_bytes: bytes, suffix: str) -> str:
    """Write bytes to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, content_bytes)
    os.close(fd)
    return path


class TestLoadPdf:
    def test_load_text_pdf(self, tmp_path):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        # pypdf can't add text easily; test with a real .pdf
        # Instead, test the function directly with a minimal PDF
        from app.rag.loader import load_pdf
        # Create minimal PDF with text
        pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>\nstream\nBT /F1 12 Tf 100 700 Td (Hello World) Tj ET\nendstream\nendobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n0000000362 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n434\n%%EOF"
        path = _tmp(pdf_bytes, ".pdf")
        result = load_pdf(path)
        assert "content" in result
        assert "metadata" in result
        assert result["metadata"]["language"] in ("zh", "en")

    def test_load_docx(self, tmp_path):
        from docx import Document
        doc = Document()
        doc.add_paragraph("This is a test document with English content.")
        path = str(tmp_path / "test.docx")
        doc.save(path)
        from app.rag.loader import load_docx
        result = load_docx(path)
        assert "test document" in result["content"].lower()
        assert result["metadata"]["language"] == "en"

    def test_load_excel(self, tmp_path):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["Name", "Age", "City"])
        ws.append(["Alice", 30, "Beijing"])
        ws.append(["Bob", 25, "Shanghai"])
        path = str(tmp_path / "test.xlsx")
        wb.save(path)
        from app.rag.loader import load_excel
        result = load_excel(path)
        assert "Name" in result["content"]
        assert "Alice" in result["content"]
        assert "Beijing" in result["content"]

    def test_load_single_document_dispatches_pdf(self, tmp_path):
        from docx import Document
        doc = Document()
        doc.add_paragraph("Test content for dispatch.")
        path = str(tmp_path / "dispatch.docx")
        doc.save(path)
        from app.rag.loader import load_single_document
        result = load_single_document(path)
        assert result["metadata"]["source"] == "dispatch.docx"

    def test_unsupported_extension_raises(self, tmp_path):
        path = str(tmp_path / "test.csv")
        with open(path, "w") as f:
            f.write("a,b,c")
        from app.rag.loader import load_single_document
        with pytest.raises(ValueError, match="Unsupported"):
            load_single_document(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_loaders.py -v 2>&1 | tail -15`
Expected: FAIL (ImportError or AttributeError — load_pdf/load_docx/load_excel don't exist yet)

- [ ] **Step 3: Implement the loaders**

In `backend/app/rag/loader.py`, add imports at top:
```python
import io
```

Add these functions after `load_single_document` (before `load_markdown_files`):

```python
def load_pdf(filepath: str) -> Dict[str, Any]:
    """Load a PDF file, extract text from all pages.

    Returns dict with keys: text, metadata
    """
    from pypdf import PdfReader
    fpath = Path(filepath)
    reader = PdfReader(str(fpath))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    content = "\n\n".join(pages)
    lang = _detect_text_language(content[:500]) if content else "en"
    return {
        "content": content,
        "metadata": {
            "source": fpath.name,
            "title": fpath.stem,
            "language": lang,
            "file_type": "pdf",
        },
    }


def load_docx(filepath: str) -> Dict[str, Any]:
    """Load a .docx file, extract paragraph text.

    Returns dict with keys: text, metadata
    """
    from docx import Document
    fpath = Path(filepath)
    doc = Document(str(fpath))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    content = "\n\n".join(paragraphs)
    lang = _detect_text_language(content[:500]) if content else "en"
    return {
        "content": content,
        "metadata": {
            "source": fpath.name,
            "title": fpath.stem,
            "language": lang,
            "file_type": "docx",
        },
    }


def load_excel(filepath: str) -> Dict[str, Any]:
    """Load an Excel file, convert rows to 'col: value' text lines.

    Returns dict with keys: text, metadata
    """
    from openpyxl import load_workbook
    fpath = Path(filepath)
    wb = load_workbook(str(fpath), read_only=True, data_only=True)
    lines = []
    for ws in wb.worksheets:
        headers = []
        for row in ws.iter_rows(values_only=True):
            if not headers:
                headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(row)]
                continue
            parts = []
            for h, v in zip(headers, row):
                if v is not None:
                    parts.append(f"{h}: {v}")
            if parts:
                lines.append(", ".join(parts))
    content = "\n".join(lines)
    lang = _detect_text_language(content[:500]) if content else "en"
    wb.close()
    return {
        "content": content,
        "metadata": {
            "source": fpath.name,
            "title": fpath.stem,
            "language": lang,
            "file_type": "xlsx",
        },
    }
```

Update `load_single_document` to dispatch to new loaders. Replace the function body:
```python
def load_single_document(filepath: str) -> Dict[str, Any]:
    """Load a single document and return {metadata, content}.

    Supports: .md, .txt, .pdf, .docx, .xlsx
    Args:
        filepath: Absolute path to file.
    Returns:
        dict with keys: metadata, content
    """
    fpath = Path(filepath)
    suffix = fpath.suffix.lower()

    if suffix == ".md":
        content = fpath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)
        lang = detect_doc_language(body, metadata.get("lang"))
        return {
            "metadata": {
                "source": fpath.name,
                "title": metadata.get("title", fpath.stem),
                "slug": metadata.get("slug", fpath.stem),
                "tags": metadata.get("tags", []),
                "category": metadata.get("category", ""),
                "filepath": str(fpath),
                "language": lang,
                "uploaded": True,
            },
            "content": body,
        }
    elif suffix == ".txt":
        content = fpath.read_text(encoding="utf-8")
        return {
            "metadata": {
                "source": fpath.name,
                "title": fpath.stem,
                "slug": fpath.stem,
                "tags": [],
                "category": "upload",
                "filepath": str(fpath),
                "language": _detect_text_language(content[:500]),
                "uploaded": True,
            },
            "content": content,
        }
    elif suffix == ".pdf":
        result = load_pdf(filepath)
        return {
            "metadata": {**result["metadata"], "slug": fpath.stem, "tags": [], "category": "upload", "filepath": str(fpath), "uploaded": True},
            "content": result["content"],
        }
    elif suffix == ".docx":
        result = load_docx(filepath)
        return {
            "metadata": {**result["metadata"], "slug": fpath.stem, "tags": [], "category": "upload", "filepath": str(fpath), "uploaded": True},
            "content": result["content"],
        }
    elif suffix in (".xlsx", ".xls"):
        result = load_excel(filepath)
        return {
            "metadata": {**result["metadata"], "slug": fpath.stem, "tags": [], "category": "upload", "filepath": str(fpath), "uploaded": True},
            "content": result["content"],
        }
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_loaders.py -v 2>&1 | tail -15`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/loader.py backend/tests/test_loaders.py
git commit -m "feat: add PDF/DOCX/Excel loaders with auto language detection"
```

---

### Task 3: Expand Upload API to Accept New Formats

**Files:**
- Modify: `backend/app/routers/rag.py:288-293`
- Modify: `backend/app/api/rag_stats.py:248-295`

- [ ] **Step 1: Expand allowed extensions in rag.py**

In `backend/app/routers/rag.py`, line 288, change:
```python
    allowed = {".md", ".txt"}
```
to:
```python
    allowed = {".md", ".txt", ".pdf", ".docx", ".xlsx"}
```

Also update the docstring at line 259:
```python
    """Upload a document (.md, .txt, .pdf, .docx, .xlsx) and incrementally index it.
```

- [ ] **Step 2: Update DocumentItem to include language + new file types**

In `backend/app/api/rag_stats.py`, update `DocumentItem` class (line 248-253):
```python
class DocumentItem(BaseModel):
    title: str
    source: str
    file_type: str
    language: str = "unknown"
    chunk_count: int
    status: str
```

Update the `get_documents` endpoint (line 268-282) to detect language and more file types:
```python
        doc_map: dict[str, dict] = defaultdict(lambda: {
            "title": "", "source": "", "file_type": "md", "language": "unknown", "chunk_count": 0
        })
        for meta in all_data.get("metadatas", []):
            if not meta or not isinstance(meta, dict):
                continue
            src = meta.get("source") or meta.get("title", "unknown")
            doc = doc_map[src]
            doc["source"] = src
            doc["title"] = meta.get("title", src.replace(".md", "").replace("_", " "))
            doc["chunk_count"] += 1
            doc["language"] = meta.get("language", "unknown")
            if src.endswith(".pdf"):
                doc["file_type"] = "pdf"
            elif src.endswith(".docx"):
                doc["file_type"] = "docx"
            elif src.endswith(".xlsx") or src.endswith(".xls"):
                doc["file_type"] = "xlsx"
            elif src.endswith(".txt"):
                doc["file_type"] = "txt"
```

- [ ] **Step: Commit**

```bash
git add backend/app/routers/rag.py backend/app/api/rag_stats.py
git commit -m "feat: expand upload API for PDF/DOCX/Excel + add language to document list"
```

---

### Task 4: Wire Language Filter Through API Layer

**Files:**
- Modify: `backend/app/rag/models.py`
- Modify: `backend/app/rag/qa_chain.py:411-461`
- Modify: `backend/app/routers/rag.py:68-108, 111-241`

- [ ] **Step 1: Add language field to RAGQueryRequest**

In `backend/app/rag/models.py`, add `language` field to `RAGQueryRequest`:
```python
class RAGQueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="RAG 查询内容",
    )
    top_k: int = Field(default=3, ge=1, le=20)
    use_mmr: bool = True
    language: Optional[str] = Field(default=None, description="Filter results by language: 'zh' or 'en'")
```

Add `from typing import Optional` at top if not already imported.

- [ ] **Step 2: Add filter_lang to rag_query_with_cache**

In `backend/app/rag/qa_chain.py`, update `rag_query_with_cache` signature (line 411):
```python
async def rag_query_with_cache(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    use_mmr: bool = True,
    lang: str | None = None,
    filter_lang: str | None = None,
) -> RAGQueryResponse:
```

Update the call to `rag_query` on line 447:
```python
    result = rag_query(query, llm_call_fn, top_k, use_mmr, lang, filter_lang)
```

- [ ] **Step 3: Pass language from router to query functions**

In `backend/app/routers/rag.py`, update `rag_query_endpoint` (line 94-96):
```python
        result = await rag_query_with_cache(
            req.query, _llm_call, top_k=req.top_k, use_mmr=req.use_mmr,
            filter_lang=req.language,
        )
```

Update `rag_query_stream_endpoint` — the `rag_query_astream` call (line 205-206):
```python
            raw_gen = rag_query_astream(
                req.query, llm, top_k=req.top_k, use_mmr=req.use_mmr,
                filter_lang=req.language,
            )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/models.py backend/app/rag/qa_chain.py backend/app/routers/rag.py
git commit -m "feat: wire language filter through RAG query API endpoint"
```

---

### Task 5: Frontend — Accept New Upload Types + Language Filter

**Files:**
- Modify: `src/components/documents/DocumentUpload.tsx:144`
- Modify: `src/pages/Documents.tsx:7-11, 175, 207`
- Modify: `src/services/rag.ts`
- Modify: `src/i18n/en.json`
- Modify: `src/i18n/zh.json`

- [ ] **Step 1: Update upload accept filter**

In `src/components/documents/DocumentUpload.tsx`, line 144, change:
```tsx
          accept=".md,.txt"
```
to:
```tsx
          accept=".md,.txt,.pdf,.docx,.xlsx"
```

Also update the supported formats text (line ~140 area). Find the i18n key `documents.upload.supported_formats` usage and ensure it mentions the new formats. The key itself is in en.json/zh.json — update in step 4.

- [ ] **Step 2: Add type badges for docx/xlsx in Documents.tsx**

In `src/pages/Documents.tsx`, expand `TYPE_BADGE` (line 7-11):
```tsx
const TYPE_BADGE: Record<string, string> = {
  md: "bg-green-100 text-green-700",
  pdf: "bg-red-100 text-red-700",
  txt: "bg-gray-100 text-gray-600",
  docx: "bg-blue-100 text-blue-700",
  xlsx: "bg-emerald-100 text-emerald-700",
};
```

Update file type emoji logic (lines 175, 207):
```tsx
const fileEmoji = doc.file_type === "pdf" ? "📄" : doc.file_type === "docx" ? "📘" : doc.file_type === "xlsx" ? "📊" : "📝";
```

Replace both occurrences of `{doc.file_type === "pdf" ? "📄" : "📝"}` with `{fileEmoji}`.

- [ ] **Step 3: Pass language to RAG query stream**

In `src/services/rag.ts`, find the function that calls `/api/rag/query/stream` and add `language` to the request body. Read the file first to find the exact location.

After reading, update the fetch body to include language from i18n:
```typescript
import i18n from '../i18n';  // adjust path as needed

// In the fetch body:
body: JSON.stringify({
  query,
  top_k: topK ?? 3,
  use_mmr: true,
  language: i18n.language === 'zh' ? 'zh' : 'en',
})
```

- [ ] **Step 4: Update i18n keys**

In `src/i18n/en.json`, update:
```json
"supported_formats": "Supports .md, .txt, .pdf, .docx, .xlsx formats",
```

In `src/i18n/zh.json`, update:
```json
"supported_formats": "支持 .md、.txt、.pdf、.docx、.xlsx 格式",
```

- [ ] **Step 5: Verify build passes**

Run: `npm run build 2>&1 | tail -5`
Expected: `✓ built in ...`

- [ ] **Step 6: Commit**

```bash
git add src/components/documents/DocumentUpload.tsx src/pages/Documents.tsx src/services/rag.ts src/i18n/en.json src/i18n/zh.json
git commit -m "feat: frontend multi-format upload support + language-aware search"
```

---

### Task 6: Cold-Start BGE Model Preload

**Files:**
- Modify: `backend/app/main.py:139-176`

- [ ] **Step 1: Add BGE model preload to startup**

In `backend/app/main.py`, add after the BM25 warmup block (after line 176):
```python
    # Pre-load BGE embedding model in background (non-blocking)
    def _preload_bge():
        try:
            from app.rag.vector_store import _get_local_model
            _get_local_model()
            logger.info("BGE model preloaded successfully")
        except Exception as e:
            logger.warning("BGE model preload failed (will lazy-load on first query): %s", e)

    loop.run_in_executor(None, _preload_bge)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "perf: preload BGE model during startup to reduce first-query latency"
```

---

### Task 7: Run Full Test Suite + Verify Production

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests PASS

- [ ] **Step 2: Run frontend build**

Run: `npm run build 2>&1 | tail -5`
Expected: `✓ built in ...`

- [ ] **Step 3: Push and verify CI**

```bash
git push origin main
gh run watch
```

Expected: CI passes, Railway auto-deploys fresh image with new chunk hashes.

- [ ] **Step 4: Verify production**

```bash
# Wait for Railway deploy
sleep 120
# Check production
curl -s https://aureon-production-1247.up.railway.app/api/health | python3 -m json.tool
# Rebuild index to include any new uploads
curl -s -X POST https://aureon-production-1247.up.railway.app/api/rag/index | python3 -m json.tool
```

Expected: health OK, index rebuild succeeds.
