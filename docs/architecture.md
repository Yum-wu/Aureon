# Aureon Architecture

This document is the public technical overview for Aureon. It describes the runtime architecture, major subsystems, and the core request flow without exposing internal planning notes.

## Overview

Aureon is a full-stack enterprise AI knowledge base platform:

- Frontend: React 19, TypeScript, Vite, Tailwind CSS 4
- Backend: FastAPI, LangGraph, LangChain
- Retrieval: Qdrant hybrid search with sparse + dense retrieval
- Cache: Redis
- Deployment: Docker + GitHub Actions + Railway

## High-Level Architecture

```text
Browser UI
  -> FastAPI API
  -> LangGraph workflow
  -> Retrieval pipeline
     -> sparse retrieval
     -> dense retrieval
     -> reranking
  -> LLM response generation
  -> SSE streaming back to UI
```

## Main Subsystems

### Frontend

- Landing and demo entry
- Search interface
- Documents management
- Analytics views
- Admin and settings surfaces
- English and Chinese UI

### Backend

- Chat and RAG APIs
- SSE streaming responses
- Document upload and indexing
- Authentication and RBAC
- Audit logging and security controls
- Cost and reliability endpoints

### Retrieval

- Qdrant as the vector backend
- Hybrid sparse + dense retrieval
- Query routing based on query complexity
- Reranking before answer generation
- Citation-aware answer generation

## Request Flow

1. User submits a question from the UI.
2. FastAPI receives the request.
3. LangGraph coordinates the retrieval and response flow.
4. The query router selects the retrieval strategy.
5. Qdrant returns candidate chunks.
6. Reranking filters and reorders the candidates.
7. The LLM generates an answer grounded in retrieved context.
8. The backend streams the answer and citations to the frontend.

## Security Model

- API key support for protected routes
- JWT-based authentication
- RBAC with role checks
- Multi-tenant isolation
- Audit logging
- PII masking
- Prompt injection guardrails

## Core Public Data Concepts

### Document

A source file uploaded to the knowledge base.

Key fields:

- filename
- source
- language
- upload status

### Chunk

A retrieval unit derived from a document.

Key fields:

- text
- parent document
- language
- source metadata

### Query

A user question submitted from chat or search.

Key fields:

- query text
- session or user context
- selected retrieval path

### Answer

A generated response returned to the user.

Key fields:

- response text
- cited sources
- stream events

## Deployment Model

- Source code hosted on GitHub
- CI runs on GitHub Actions
- Application deployed to Railway
- Demo served from the public production URL

## Related Docs

- [README.md](../README.md)
- [README.zh-CN.md](../README.zh-CN.md)
- [SECURITY.md](../SECURITY.md)
