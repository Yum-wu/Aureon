# System Architecture Overview

## High-Level Architecture

```
User → React Frontend → FastAPI Backend → LangGraph Orchestrator
                                            ├── Intent Classifier
                                            ├── Hybrid Retrieval (BM25 + BGE + Context Compression)
                                            ├── RAG Self-Correction (CRAG)
                                            ├── LLM Generation
                                            ├── Prompt Injection Guard
                                            └── SSE Streaming
```

## Components

### Frontend (React + Vite)
- Landing Page: Product showcase
- Search: Enterprise search experience
- Dashboard: System metrics & monitoring
- Architecture: Pipeline visualization
- Analytics: Usage analytics
- Documents: Knowledge base management

### Backend (FastAPI + LangGraph)
- API Layer: RESTful endpoints + Auth Middleware (X-API-Key)
- RAG Pipeline: Hybrid retrieval + Context Compression + CRAG self-correction
- Security: Prompt Injection detection (guardrails.py), Fernet encryption
- Cache: Redis + in-memory + Semantic dedup
- Storage: ChromaDB vector store

## Data Flow

1. User submits query
2. Intent classifier routes request
3. Hybrid retrieval (BM25 keyword + BGE semantic)
4. Context compression (embedding similarity filter)
5. CRAG self-correction (retry on low quality)
6. Prompt assembly with context
7. Prompt injection guard check
8. LLM generates streaming response
9. Citation injection from sources
10. SSE delivers tokens to frontend

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Backend | Python 3.11, FastAPI, LangGraph |
| Vector DB | ChromaDB |
| Cache | Redis + In-Memory |
| LLM | DeepSeek / GPT-4o / Claude |
| Security | API Key Auth, Prompt Injection Guard, Fernet Encryption |
| Deployment | Docker (non-root), Railway, CI/CD |
