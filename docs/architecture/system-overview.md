# System Architecture Overview

## High-Level Architecture

```
User → React Frontend → FastAPI Backend → LangGraph Orchestrator
                                            ├── Intent Classifier
                                            ├── Hybrid Retrieval (BM25 + DashScope embedding/Qdrant + Context Compression)
                                            ├── RAG Self-Correction (CRAG)
                                            ├── Adaptive Re-ranking (DashScope qwen3-rerank)
                                            ├── LLM Generation
                                            ├── Cache (Redis + Semantic Cache)
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
- Cache: Redis + Semantic Cache (Exact + Semantic)
- Storage: Qdrant cloud vector store (primary)
- Embedding: DashScope text-embedding-v4 (Singapore, compatible-mode API)
- Reranker: DashScope qwen3-rerank (compatible-api, separate endpoint)

## Data Flow

1. User submits query
2. Intent classifier routes request
3. Hybrid retrieval (BM25 keyword + DashScope text-embedding-v4 semantic via Qdrant)
4. Context compression (embedding similarity filter)
5. Adaptive Re-ranking (query complexity → strategy selection)
6. CRAG self-correction (retry on low quality)
7. Prompt assembly with context
8. Prompt injection guard check
9. LLM generates streaming response
10. Citation injection from sources
11. SSE delivers tokens to frontend

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Backend | Python 3.12, FastAPI, LangGraph |
| Vector DB | Qdrant (cloud) — primary |
| Embedding | DashScope text-embedding-v4 (compatible-mode API) |
| Reranker | DashScope qwen3-rerank (compatible-api) |
| Cache | Redis + Semantic Cache (Exact + Semantic) |
| LLM | DeepSeek / GPT-4o / Claude |
| Security | API Key Auth, Prompt Injection Guard, Fernet Encryption |
| Deployment | Docker (non-root), Railway, CI/CD |
| Health | `/api/health` (Railway) + `/health/ready` (K8s probe) |
| Observability | Prometheus `/metrics` + structlog |

## DashScope API Configuration (Singapore)

| API | Endpoint | Notes |
|-----|----------|-------|
| Embedding | `dashscope-intl.aliyuncs.com/compatible-mode/v1/embeddings` | `compatible-mode` path |
| Rerank | `dashscope-intl.aliyuncs.com/compatible-api/v1/reranks` | `compatible-api` path, `reranks` (plural) |

> ⚠️ Embedding and Rerank use different base URLs (`compatible-mode` vs `compatible-api`). Do not mix.
