# Aureon Architecture

This document is the technical architecture overview for Aureon. It describes the runtime architecture, major subsystems, and the core request flow.

## Overview

Aureon is a full-stack enterprise AI knowledge base platform:

- Frontend: React 19, TypeScript, Vite, Tailwind CSS 4
- Backend: FastAPI, LangGraph, LangChain
- Retrieval: Qdrant hybrid search with sparse + dense retrieval
- Cache: Redis
- Deployment: Docker + GitHub Actions + Railway

## High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                  Browser (React 19)                          │
│   Landing  Search  Chat  Documents  Analytics  Admin         │
│   Tailwind CSS 4  ·  i18n (en/zh)  ·  Zustand state mgmt   │
└──────────┬──────────────────────────────────────────────────┘
           │  HTTP/SSE /ws
           ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI API Layer (ASGI)                        │
│                                                              │
│  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Auth/MW    │ │ Middleware  │ │ Routers  │ │ SSE Stream │ │
│  │ JWT + API  │ │ CORS/Tenant│ │ chat/rag │ │ zero-buffer │ │
│  │ Key + RBAC │ │ Rate Limit │ │ crew/... │ │ push       │ │
│  └────────────┘ └────────────┘ └─────┬────┘ └────────────┘ │
└──────────────────────────────────────┼──────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│              LangGraph Workflow Engine                        │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Agent Layer   │  │ Tool Layer    │  │ Graph Orchestration│  │
│  │ LLM Factory   │  │ @tool decorator│  │ Stateful Graph    │  │
│  │ Multi-model   │  │ Composable    │  │ Conditional Routes │  │
│  │ Qwen3/GLM4/  │  │ sandboxed     │  │ Loops / Interrupt  │  │
│  │ Reasoning    │  │              │  │ Resume            │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└──────────────────────────────────────┬──────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    RAG Retrieval Pipeline                      │
│                                                              │
│  ┌──────────┐  ┌────────────┐  ┌────────────┐ ┌──────────┐  │
│  │Query     │→ │ Hybrid      │→ │ Post-      │→│ Answer    │  │
│  │Router    │  │ Retrieval   │  │ retrieval  │ │ Generation│  │
│  │simple→   │  │             │  │            │ │(QA Chain) │  │
│  │ sparse   │  │ Dense Vec   │  │ Reranking  │ │ HyDE     │  │
│  │medium→   │  │ BGE-M3      │  │ CRAG eval  │ │ Prompt   │  │
│  │ hybrid   │  │ 1024d       │  │ Negative   │ │ enhancer │  │
│  │complex→  │  │ Sparse Vec  │  │ Detection  │ │ Cite src │  │
│  │HyDE/MQ   │  │ BM25-like   │  │ Ctx Comp   │ │          │  │
│  └──────────┘  └────────────┘  └────────────┘ └──────────┘  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Qdrant Vector Database (SaaS Cloud)                   │    │
│  │  HNSW m=32 · INT8 quant · Sparse+Dense hybrid (RRF)   │    │
│  │  Ingestion Pipeline: Extractor→Normalizer→Chunk→QC    │    │
│  │  ParentChildSplitter (1500/512) · Contextual Prefix   │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────┬──────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   Infrastructure & Support Layer               │
│                                                              │
│  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ Memory    │ │ Cache    │ │ Security  │ │ Observability │  │
│  │ L0 raw    │ │ Redis    │ │ PII mask  │ │ LangFuse     │  │
│  │ L1 atoms  │ │ mem ttl  │ │ Prompt    │ │ full-trace   │  │
│  │ L2 summary│ │ semantic │ │ Inj.      │ │ latency/cost │  │
│  │ L3 persona│ │ de-dup   │ │ Guardrails│ │ quality met  │  │
│  │ offload   │ │          │ │ SSO/JWT   │ │              │  │
│  └───────────┘ └──────────┘ └───────────┘ └──────────────┘  │
│                                                              │
│  ┌───────────┐ ┌────────────┐ ┌───────────┐                │
│  │ Multi-    │ │ Reliability│ │ Cost      │                │
│  │ Tenant    │ │ Circuit    │ │ Redis TS  │                │
│  │ JWT signed│ │ Breaker    │ │ Budget    │                │
│  │ Tenant    │ │ Event Src  │ │ Throttle  │                │
│  │ Isolation │ │ SLO Monitor│ │          │                │
│  └───────────┘ └────────────┘ └───────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Main Subsystems

### Frontend

React 19 user interface covering:

- **Landing page & Demo search**: product showcase
- **Chat interface**: input area, streaming Markdown rendering, citation hover cards, action bar (copy/regenerate/vote)
- **Search**: query manipulation, knowledge exploration views
- **Support Widget**: FAB → chat panel, localStorage persistence, 10s-delayed greeting, unread badge (99+)
- **Document management**: upload, list, search, delete
- **Onboarding**: Viewer 3-step / Editor+ 5-step flow
- **Analytics dashboard**: RAG usage stats, token consumption, latency monitoring
- **Admin & settings**: user management, system configuration
- **i18n**: English + Chinese, 34 support module keys
- **Styling**: Tailwind CSS 4 + tailwindcss-animate, oklch design tokens, Plus Jakarta Sans / Inter / JetBrains Mono

### Backend

FastAPI stateless REST + SSE services:

| Layer | Module | Responsibility |
|---|------|------|
| **API** | `routers/` | chat/rag/crew/support endpoints, SSE streaming |
| **Agent** | `agent/` | LLM factory (multi-model), Agent factory, streaming executor (astream_events v2) |
| **Tools** | `tools/` | `@tool` decorator → `ALL_TOOLS`, typed + documented |
| **Workflow** | `langgraph/` | Stateful graph orchestration, conditional routing, interrupt/resume |
| **RAG** | `rag/` | Retrieval pipeline (HyDE/hybrid/CRAG/rerank), ingestion, query routing, quality gates |
| **Memory** | `memory/` | L0-L3 progressive memory tiers + context offloading |
| **Cache** | `cache/` | Redis + in-memory dual cache, semantic cache dedup |
| **Security** | `security/` | PII detection/masking, prompt injection guardrails, SSO/Fernet encryption |
| **Multi-tenant** | `multi_tenant/` | JWT-signed tenant_id, ASGI middleware isolation |
| **Observability** | `observability/` | LangFuse full-trace (init → handler → shutdown) |
| **Cost** | `cost/` | Token/API cost tracking, Redis time-series budget |
| **Reliability** | `reliability/` | Circuit breaker, event sourcing, SLO monitoring, backups |
| **Audit** | `audit/` | Operation logs, user action trails |
| **Database** | `database/` | PostgreSQL (asyncpg) connection pool, migrations (Alembic) |
| **Middleware** | `middleware/` | CORS, multi-tenant isolation, rate limiting, tenant resolution |

### Retrieval

Multi-strategy adaptive RAG pipeline:

- **Vector Store**: Qdrant Cloud, BGE-M3 1024d dense + sparse hybrid (RRF fusion)
- **Query Router**: three pipelines based on query complexity
  - Simple → pure sparse vector (< 10ms)
  - Medium → hybrid retrieval + reranking
  - Complex → HyDE + Multi-Query + hybrid + CRAG eval
- **Index**: HNSW m=32 ef_construct=200, INT8 quantization, always_ram
- **Reranking**: adaptive — skip when top1/top2 score gap is large
- **CRAG**: lightweight embedding-similarity evaluator (~50ms), 3-way routing: correct/ambiguous/incorrect
- **Ingestion**: `Extractor → Normalizer → Chunk → Quality Gate`
  - ParentChildSplitter: parent 1500 / child 512 / overlap 80
  - Contextual Retrieval prefix enhancement
  - Concurrency Semaphore(5), ~10min/1000 docs
- **Negative Detection**: fast keyword pass + LLM classifier
- **Quality Gates**: Recall + Faithfulness + latency benchmarks

### Memory System

Progressive memory tiers solving long-context loss:

| Tier | Storage | Content | Capacity |
|---|------|------|------|
| L0 | PostgreSQL conversations | Raw dialogue | Full history |
| L1 | PostgreSQL atoms | Atomic fact triples | Key info |
| L2 | offloads/scenarios/*.md | Scenario-level summaries | ≤3 scenarios |
| L3 | offloads/persona.md | User profile (prefs/style/background) | ≤2KB |

- **Offloading**: long tool outputs externalized to `offloads/refs/*.md`, loaded on demand to prevent attention dilution

## Request Flow

### Chat + RAG Flow

```text
User question ──→ Frontend Chat UI
                     │
                     ▼ POST /api/chat/enhanced/stream
              FastAPI receives request (JWT → tenant → Rate Limit)
                     │
                     ▼
              LangGraph launches stateful graph
                     │
                     ├── Agent selects tools or direct answer
                     │   ├── tool invocation → inject results
                     │   └── direct answer → skip to generation
                     │
                     ├── RAG branch: Query Router classifies
                     │   ├── simple → pure sparse retrieval
                     │   ├── medium → hybrid + Rerank
                     │   └── complex → HyDE + Multi-Query + CRAG
                     │
                     ├── Qdrant hybrid search
                     │   ├── dense vector similarity (BGE-M3)
                     │   ├── sparse vector keyword match
                     │   └── RRF fusion top-k candidates
                     │
                     ├── Post-processing
                     │   ├── Reranking
                     │   ├── CRAG quality check
                     │   ├── Negative detection (out-of-scope rejection)
                     │   └── Context compression filtering
                     │
                     ├── Answer generation (QA Chain)
                     │   ├── HyDE hypothetical document enhancement
                     │   ├── LLM generates grounded answer
                     │   └── Source citation annotation
                     │
                     └── SSE streaming response
                         ├── session → init
                         ├── text → per-token answer
                         ├── tool_start/tool_end → tool call info
                         ├── done → completion signal + citations
                         └── error → error handling
```

### LangGraph Workflow

Directed graph orchestration, not a simple linear pipeline:

- Nodes (Agent, Tool, RAG, Generate) connected by edges
- Conditional routing based on Agent output
- Loops (multi-turn tool calls) and interrupt/resume (human-in-the-loop)
- All edges instrumented with LangFuse traces

### RAG Pipeline Detail

```
Query complexity ──→                          HyDE (hypothetical doc)
                           ┌────────────────────┐
Query Vector ─────────────→│   Dense Retrieval   │─→┐
                           │   BGE-M3 1024d      │  │
                           │   top_k × 12 cand   │  │
                           └────────────────────┘  │  ┌──────────┐
                                                   ├─→│ RRF fuse  │─→ Rerank → QA
                           ┌────────────────────┐  │  │ k=60     │
Sparse Vector ────────────→│   Sparse Retrieval  │─→┘  └──────────┘
                           │   BGE-M3 sparse     │
                           └────────────────────┘
```

## Security Model

Multi-layer defense-in-depth architecture:

| Layer | Measure | Description |
|---|------|------|
| **Transport** | HTTPS | TLS enforced on all API endpoints |
| **Authentication** | API Key / JWT | API Key via `X-API-Key` header (whitelisted: health endpoints), JWT for SSO/RBAC |
| **Authorization** | RBAC | Three-tier roles: VIEWER / EDITOR / ADMIN, per-route middleware checks |
| **Tenant Isolation** | JWT-signed tenant_id | ASGI TenantMiddleware → full-module tenant filtering |
| **Injection** | Prompt Injection Guardrails | User input scanning, suspicious content flagged/blocked |
| **Data Privacy** | PII Masking | Fernet symmetric encryption for sensitive fields, audit logs sanitized |
| **Rate Limiting** | Token Bucket | Redis-based distributed rate limiting, tenant-level isolation |
| **CORS** | Explicit allow_headers | Allowed headers listed explicitly, no wildcard `*` |
| **Audit** | structured audit | user_id + action + resource + timestamp, tamper-evident

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

## Technology Stack

| Category | Components |
|------|------|
| **Runtime** | Python 3.12 / Node.js 20+ / Docker |
| **Web Framework** | FastAPI (ASGI) / React 19 + Vite |
| **AI Framework** | LangChain + LangGraph (stateful Agent orchestration) |
| **LLM** | Qwen3.5-Flash (primary) / GLM-4-Flash (fallback) / Reasoning models |
| **Vector DB** | Qdrant Cloud (BGE-M3 1024d, INT8, RRF) |
| **Embedding** | DashScope (primary) / SiliconFlow / Zhipu (fallback chain) |
| **Cache** | Redis (distributed) + app memory (hot data) |
| **Database** | PostgreSQL + asyncpg |
| **Observability** | LangFuse (trace + Prompt Management) |
| **Styling** | Tailwind CSS 4 + Design Tokens (oklch) |
| **i18n** | react-i18next (en / zh) |

## Deployment Model

- **Source**: GitHub
- **CI/CD**: GitHub Actions — pip-audit + Trivy + hadolint + mypy (continue-on-error) + ruff lint + pytest (1011 tests pass)
- **Platform**: Railway, Southeast Asia region, auto-deploy
- **Container**: Docker `python:3.12-slim`, non-root user
- **Production URL**: `https://aureon-production-659a.up.railway.app`
- **Supporting services**: Railway Redis + Qdrant Cloud (standalone SaaS)
- **Idle sleep**: Railway auto-sleep, cold start ~15s P95

## Related Docs

- [README.md](../README.md)
- [README.zh-CN.md](../README.zh-CN.md)
- [SECURITY.md](../SECURITY.md)
