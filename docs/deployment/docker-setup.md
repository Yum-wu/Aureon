# Docker Deployment Guide

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM

## Quick Start

```bash
# Clone repository
git clone https://github.com/Yum-wu/Aureon.git
cd Aureon

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

# Start services
docker-compose up -d

# Access application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| frontend | 3000 | React app via Nginx |
| backend | 8000 | FastAPI server (non-root via gosu) |
| redis | 6379 | Cache layer (password auth) |

## Environment Variables

```env
# backend/.env
LLM_API_KEY=your_deepseek_api_key
LLM_MODEL=deepseek-v4-flash

# Embedding: DashScope (Singapore)
DASHSCOPE_API_KEY=your_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
DASHSCOPE_DIMENSIONS=1024
EMBEDDING_DIM=1024
SKIP_LOCAL_EMBED=true

# Reranker: DashScope qwen3-rerank (different endpoint than embedding!)
DASHSCOPE_RERANK_URL=https://dashscope-intl.aliyuncs.com/compatible-api/v1
RERANK_ENABLED=true
RERANK_BACKEND=api
RERANK_PROVIDER=dashscope

# Observability: LangFuse
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

# Query Routing (Adaptive-RAG)
QUERY_ROUTER_ENABLED=true

# Vector store: Qdrant Cloud
VECTOR_BACKEND=qdrant
QDRANT_URL=https://your-qdrant-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key

# Authentication (production)
API_AUTH_KEY=your_secure_api_key_here
JWT_SECRET=your_jwt_secret_here
ENCRYPTION_KEY=your_fernet_key_here

# Redis auth
REDIS_PASSWORD=your_redis_password

```

> ?? **Important**: DashScope Embedding and Rerank use different base URLs:
> - Embedding: `compatible-mode/v1`
> - Rerank: `compatible-api/v1` (with `reranks` endpoint, plural)

## Security

- Backend runs as non-root user (gosu appuser)
- Redis/ES require password authentication
- API Key auth available via API_AUTH_KEY
- SSO secrets encrypted with Fernet

## Production Checklist

- [ ] Set API_AUTH_KEY for endpoint protection
- [ ] Set JWT_SECRET for JWT token signing
- [ ] Set ENCRYPTION_KEY for SSO secret encryption
- [ ] Configure Redis password
- [ ] Set strong SECRET_KEY
- [ ] Configure CORS allowed origins
- [ ] Enable HTTPS
- [ ] Set up log aggregation
- [ ] Configure monitoring
- [ ] Set resource limits
