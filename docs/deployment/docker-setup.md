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
| elasticsearch | 9200 | BM25 search (password auth) |

## Environment Variables

```env
# backend/.env
LLM_API_KEY=your_deepseek_api_key
LLM_MODEL=deepseek-v4-flash
DASHSCOPE_API_KEY=your_dashscope_api_key  # Embedding

# Authentication (production)
API_AUTH_KEY=your_secure_api_key_here

# Redis auth
REDIS_PASSWORD=your_redis_password

# Elasticsearch auth
ES_PASSWORD=your_es_password
```

## Security

- Backend runs as non-root user (gosu appuser)
- Redis/ES require password authentication
- API Key auth available via API_AUTH_KEY
- SSO secrets encrypted with Fernet

## Production Checklist

- [ ] Set API_AUTH_KEY for endpoint protection
- [ ] Set ENCRYPTION_KEY for SSO secret encryption
- [ ] Configure Redis/ES passwords
- [ ] Set strong SECRET_KEY
- [ ] Configure CORS allowed origins
- [ ] Enable HTTPS
- [ ] Set up log aggregation
- [ ] Configure monitoring
- [ ] Set resource limits
