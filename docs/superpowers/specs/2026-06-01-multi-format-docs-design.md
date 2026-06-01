# Multi-Format Document Support & Production Fix

Date: 2026-06-01
Status: Approved

## Overview

Extend RAG system to support PDF, DOCX, Excel uploads with automatic language detection and filtering. Fix production stale-chunk rendering error. Optimize cold-start UX.

## 1. Multi-Format Document Support

### Format Parsers

| Format | Library | Method |
|--------|---------|--------|
| PDF | `pypdf` | Extract text per page, join with `\n` |
| DOCX | `python-docx` | Extract paragraph text |
| Excel (.xlsx/.xls) | `openpyxl` | Each row → `col: value` text lines |

### Files to Change

- `backend/app/rag/loader.py` — add `load_pdf()`, `load_docx()`, `load_excel()`, update `load_single_document()`
- `backend/app/routers/rag.py` — expand `allowed` set to `{".md", ".txt", ".pdf", ".docx", ".xlsx"}`
- `backend/requirements.txt` — add `pypdf`, `python-docx`, `openpyxl`
- `src/pages/Documents.tsx` — update file accept filter and type badges

### Language Detection

- Auto-detect language from extracted text using existing `detect_language()` utility
- Store `language` field in chunk metadata during indexing
- User can override via upload form `language` parameter

## 2. Language-Aware Filtering

### Backend

- `POST /api/rag/query` — accept optional `language` param, filter search results by metadata
- `GET /api/rag/documents` — return `language` field in response

### Frontend

- `useRAG` / search hook — pass `i18n.language` as `language` param to query API
- Document list — filter displayed documents by current i18n language

## 3. Production Deployment Fix

### Root Cause

Railway container serving old image. Production HTML references `index-CFpTM4Im.js` (old hash), local dist has `index-CIfGABNw.js` (new hash).

### Fix

Push any commit → GitHub Actions CI → Railway auto-deploy with fresh image.

## 4. Cold-Start Optimization

### Backend

- In `startup()`, spawn background thread to pre-load BGE model
- Add `X-Warming-Up` response header on first query while model loads

### Frontend

- On `X-Warming-Up: true` response, show toast: "System warming up, please wait..."

### Documentation

- Recommend UptimeRobot (free) for keep-alive pings every 5 minutes

## Testing

- Unit tests for each new loader function
- Integration test: upload PDF → search → verify results
- Verify language filtering returns correct subset
