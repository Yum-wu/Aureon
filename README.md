# Aureon — Enterprise AI Knowledge Base Platform

> Production-grade enterprise AI search and knowledge intelligence platform.

[![CI](https://github.com/Yum-wu/Aureon/actions/workflows/ci.yml/badge.svg)](https://github.com/Yum-wu/Aureon/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

**Other languages**: [中文](README.zh-CN.md)

## Performance

| Metric | Value |
|--------|-------|
| Recall@3 (Hybrid) | **96.08%** |
| TTFT (Streaming) | **~310ms** |
| Full RAG Latency | **~400ms** |
| Retrieval Latency | **~10ms** |
| Cost per Query | **$0.001** |

## Features

- **Enterprise AI Search** — Streaming answers with progressive citations
- **Hybrid Retrieval** — BM25 keyword + Dense semantic dual-channel fusion
- **Document Management** — Upload, auto-index, preview, source management
- **System Dashboard** — Real-time metrics, health monitoring, usage analytics
- **Analytics** — Latency, token usage, cache performance, query distribution
- **Architecture & Performance** — Interactive architecture diagram, optimization metrics
- **Enterprise Admin** — Workspace management, RBAC, audit logs
- **Feature Flags** — Gradual rollout, lifecycle management
- **Observability** — Query tracing, performance monitoring
- **Security** — PII detection, SSO, rate limiting
- **Cost Governance** — Per-workspace cost tracking, budget management
- **Reliability** — Backup, incident management, SLO, circuit breaker
- **Knowledge Intelligence** — Document version control, export
- **AI Platform** — Multi-LLM router, confidence scoring, session memory
- **Integration** — Enterprise connectors (Google Drive/SharePoint), IM bots

## Architecture

```
User → Web UI (React + Vite) → FastAPI → LangGraph Orchestrator
                                           ├── Intent Classifier
                                           ├── Hybrid Search (BM25 + BGE/Chroma)
                                           ├── LLM (GLM-4-Flash / GPT-4o-mini)
                                           ├── Cache (Redis + In-Memory)
                                           └── SSE Streaming Response
```

## Quick Start

```bash
# Frontend
cd Aureon && npm install && npm run dev

# Backend
cd Aureon/backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Docker (recommended)
docker-compose up
```

## Screenshots

| Landing | Search | Dashboard |
|---------|--------|-----------|
| ![Landing](screenshots/landing.png) | ![Search](screenshots/search.png) | ![Dashboard](screenshots/dashboard.png) |

## Documentation

- [Architecture](docs/architecture/)
- [Benchmarks](docs/benchmarks/)
- [Deployment](docs/deployment/)
- [Product](docs/product/)

## License

MIT

---

Built by [Yum-wu](https://github.com/Yum-wu)
