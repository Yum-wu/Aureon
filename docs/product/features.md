# Product Features

## Enterprise AI Search

Production-grade hybrid retrieval platform with streaming answers, citations, and real-time analytics.

### Core Features

#### Hybrid Retrieval
- BM25 keyword search for exact matches
- Dense semantic search via DashScope text-embedding-v4
- Context Compression (embedding similarity filter)
- RRF score fusion
- 95.1% Recall@3

#### Streaming Search
- Real-time SSE token streaming
- Progressive rendering
- 310ms TTFT (Time to First Token)

#### Citation UX
- Inline citation markers [1][2][3]
- Source preview panel
- Click to view full source

#### System Dashboard
- Real-time query metrics
- Latency monitoring
- Cache hit rates
- System health status

#### Analytics
- Query volume trends
- Token usage tracking
- Cost analysis
- Performance benchmarks

#### Document Management
- Multi-format upload (PDF, MD, TXT)
- Auto-indexing
- Source management
- Preview capability

### Enterprise Features

- Docker deployment (non-root via gosu)
- CI/CD pipeline (GitHub Actions)
- API Key authentication (X-API-Key)
- Prompt Injection detection (OWASP LLM Top 10)
- SSO with Fernet encryption
- Health monitoring
- Audit logging
- RBAC ready
- Redis/ES password authentication

## Performance Metrics

| Metric | Value |
|--------|-------|
| Recall@3 | 95.1% |
| Context Precision (DeepEval) | 0.791 |
| Faithfulness (DeepEval) | 0.967 |
| Negative Detection | 100% |
| TTFT | ~310ms |
| Retrieval Latency | ~5.8ms |
| Cost/Query | ~$0.001 |
| Backend Tests | 426 |
