# Product Features

## Enterprise AI Search

Production-grade hybrid retrieval platform with streaming answers, citations, and real-time analytics.

### Core Features

#### Hybrid Retrieval
- Sparse vector (BGE-M3) + dense semantic search via Qdrant native hybrid
- Dense semantic search via DashScope text-embedding-v4
- Context Compression (embedding similarity filter)
- Qdrant native sparse vectors replacing external BM25, 100% MRR improvement
- Query routing by complexity (simple/medium/complex)
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

#### Query Routing (Adaptive-RAG)
- Simple queries → pure sparse vector (<10ms)
- Medium queries → hybrid search + adaptive re-ranking
- Complex queries → HyDE → multi-query → ensemble rerank → light CRAG

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
- LangFuse observability integration
- Redis password authentication

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
| Backend Tests | 793 |
| Tests | 793 |
