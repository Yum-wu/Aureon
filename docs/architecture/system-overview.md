# System Architecture Overview

## High-Level Architecture

```
User → React Frontend → FastAPI Backend → LangGraph Orchestrator
                                           ├── Query Router (Adaptive-RAG)
                                           ├── Hybrid Search (Sparse + Dense + RRF)
                                           ├── Lightweight CRAG (embedding-based, ~50ms)
                                           ├── Adaptive Re-ranking (DashScope qwen3-rerank)
                                           ├── LLM Generation (qwen3.6-flash / DeepSeek / Claude)
                                           ├── Cache (Redis + Semantic Cache)
                                           ├── LangFuse Observability
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
- RAG Pipeline: Hybrid retrieval + Sparse vectors (BGE-M3) + RRF fusion + Lightweight CRAG
- Security: Prompt Injection detection (guardrails.py), Fernet encryption
- Cache: Redis + Semantic Cache (Exact + Semantic)
- Storage: Qdrant cloud vector store (primary, native sparse + dense)
- Embedding: DashScope text-embedding-v4 / BGE-M3 (Singapore), unified 1024d
- Reranker: DashScope qwen3-rerank (compatible-api, separate endpoint)
- Query Router: Adaptive-RAG by query complexity (simple/medium/complex)
- Observability: LangFuse trace + structlog + Prometheus /metrics

## Data Flow

1. User submits query
2. Query router classifies complexity (simple/medium/complex)
3. Route selection:
   - Simple → pure sparse vector search
   - Medium → hybrid search (sparse + dense) + adaptive re-ranking
   - Complex → HyDE → multi-query → hybrid search → ensemble rerank → light CRAG
4. Context compression (embedding similarity filter)
5. Prompt assembly with context
6. Prompt injection guard check
7. LLM generates streaming response (qwen3.6-flash / DeepSeek / Claude)
8. Citation injection from sources
9. LangFuse trace collection
10. SSE delivers tokens to frontend

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Backend | Python 3.12, FastAPI, LangGraph |
| Vector DB | Qdrant (cloud) — primary |
| Sparse Vector | BGE-M3 (Qdrant native) | Built-in, replaces external BM25 |
| Embedding | DashScope text-embedding-v4 / BGE-M3 (compatible-mode API), 1024d unified |
| Reranker | DashScope qwen3-rerank (compatible-api) |
| Query Router | Adaptive-RAG | Simple/Medium/Complex routing |
| Cache | Redis + Semantic Cache (Exact + Semantic) |
| LLM | qwen3.6-flash / DeepSeek / Claude |
| Security | API Key Auth, Prompt Injection Guard, Fernet Encryption |
| Deployment | Docker (non-root), Railway, CI/CD |
| Health | `/health/ready` (Railway) | Qdrant/Redis/index probes |
| Observability | LangFuse + structlog + Prometheus `/metrics` | Full pipeline tracing |

## DashScope API Configuration (Singapore)

| API | Endpoint | Notes |
|-----|----------|-------|
| Embedding | `dashscope-intl.aliyuncs.com/compatible-mode/v1/embeddings` | `compatible-mode` path |
| Rerank | `dashscope-intl.aliyuncs.com/compatible-api/v1/reranks` | `compatible-api` path, `reranks` (plural) |
| Dimension | `DASHSCOPE_DIMENSIONS=1024` | Unified 1024d embedding dimension |

> ⚠️ Embedding and Rerank use different base URLs (`compatible-mode` vs `compatible-api`). Do not mix.
