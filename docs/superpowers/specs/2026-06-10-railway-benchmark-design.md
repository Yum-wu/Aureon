# Railway Production Benchmark Design

**Author:** Aureon Team
**Date:** 2026-06-10
**Status:** Approved
**Version:** v1.0

---

## Overview

Design a comprehensive benchmark system to evaluate Aureon RAG performance in Railway production environment with 100 concurrent connections support. Tests retrieval quality, latency, cost efficiency, and resource consumption.

## Goals

1. **Comprehensive Evaluation** — Multi-dimensional testing (quality + latency + cost + resources)
2. **Railway Production Testing** — Real deployment environment validation
3. **100-Concurrent Support** — Handle high-throughput scenarios
4. **Multi-Format Output** — Terminal + JSON + Markdown reports

---

## Architecture

### System Flow

```
run_benchmark.py (main entry)
├── Phase 1: Environment Detection & Health Check
│   ├── Local mode: direct function calls
│   └── Railway mode: HTTP API calls
├── Phase 2: Retrieval Quality Test
│   ├── Recall@K (3, 5, 10)
│   ├── Precision@K
│   ├── MRR (Mean Reciprocal Rank)
│   └── nDCG@10
├── Phase 3: Latency Test
│   ├── Single query latency
│   ├── P50/P90/P99 distribution
│   └── Concurrent QPS at different levels
├── Phase 4: Concurrency Test (100 concurrent)
│   ├── Gradual scaling: 1 → 10 → 25 → 50 → 75 → 100
│   ├── Bottleneck analysis
│   └── API rate limit detection
├── Phase 5: Cost Efficiency Test
│   ├── Token usage statistics
│   ├── API call counts
│   └── Cost per query estimation
└── Phase 6: Report Generation
    ├── Terminal colored output
    ├── JSON (data/results-{timestamp}.json)
    └── Markdown (data/reports-{timestamp}.md)
```

### Component Diagram

```
┌─────────────────────────────────────┐
│      Benchmark Controller           │
│  (run_benchmark.py)                │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
┌─────────────┐  ┌──────────────────┐
│ Local Mode  │  │ Railway Mode     │
│ (direct)    │  │ (HTTP client)    │
└─────────────┘  └──────────────────┘
       │               │
       └───────┬───────┘
               ▼
┌─────────────────────────────────────┐
│      Concurrency Manager            │
│  (dynamic semaphores)              │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
┌─────────────┐  ┌──────────────────┐
│ LLM APIs    │  │ Vector Store     │
│ DeepSeek    │  │ Qdrant Cloud     │
│ DashScope   │  │ ChromaDB         │
└─────────────┘  └──────────────────┘
```

---

## Components

### 1. Benchmark Configuration

**File:** `backend/app/benchmark_config.py`

**Purpose:** Central configuration management for benchmark environments.

**Key Features:**
- Auto-detect environment (local vs Railway)
- Dynamic semaphore configuration
- HTTP pool settings
- Cost pricing tables

**Data Structure:**

```python
@dataclass
class BenchmarkEnv:
    mode: str  # "local" | "railway"
    base_url: Optional[str]
    api_key: Optional[str]
    vector_backend: str  # "chroma" | "qdrant"
    embedding_provider: str  # "local" | "dashscope" | "siliconflow"
    rerank_provider: str  # "api" | "local"

@dataclass
class ConcurrencyConfig:
    http_pool_limit: int = 100
    semaphores: Dict[str, int] = field(default_factory=dict)
    timeout_seconds: int = 30
```

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| BENCHMARK_MODE | local | "local" or "railway" |
| RAILWAY_API_URL | - | Railway service URL |
| RAILWAY_API_KEY | - | API authentication key |
| LLM_SEMAPHORE_DEEPSEEK | 30 (local) / 80 (railway) | DeepSeek concurrency |
| LLM_SEMAPHORE_EMBEDDING | 50 (local) / 80 (railway) | Embedding concurrency |
| RAG_SEMAPHORE | 40 (local) / 80 (railway) | RAG pipeline concurrency |
| HTTP_POOL_LIMIT | 100 | HTTP connection pool |

---

### 2. HTTP Client (Railway Mode)

**File:** `backend/app/benchmark/http_client.py`

**Purpose:** Handle API calls to Railway-deployed services.

**Key Features:**
- Connection pool for 100 concurrent requests
- Timeout handling (30s default)
- Retry logic for transient failures
- Latency measurement

**Interface:**

```python
class RailwayBenchmarkClient:
    def __init__(self, base_url: str, api_key: str, pool_limit: int = 100):
        ...

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Call RAG query API endpoint."""
        ...

    async def health_check(self) -> bool:
        """Verify API is reachable."""
        ...

    async def close(self):
        """Close connection pool."""
        ...
```

**Dependencies:**
- httpx (async HTTP client)

---

### 3. Concurrency Test Suite

**File:** `backend/app/benchmark/concurrency_test.py`

**Purpose:** Test system under 100 concurrent connections.

**Key Features:**
- Gradual concurrency scaling (1 → 100)
- Dynamic semaphore adjustment
- Bottleneck detection (rate limits, timeouts, queue delays)
- P99 latency tracking

**Test Levels:**

| Level | Concurrency | Expected QPS | Target P99 |
|-------|-------------|--------------|------------|
| Baseline | 1 | 10-15 | < 200ms |
| Low | 10 | 40-60 | < 500ms |
| Medium | 50 | 70-100 | < 1.5s |
| High | 100 | 80-120 | < 3s |

**Performance Thresholds:**

```python
THRESHOLDS = {
    "min_qps_at_100": 50,           # Minimum QPS at 100 concurrent
    "max_p99_at_100_ms": 3000,      # Max P99 latency at 100 concurrent
    "min_success_rate": 0.95,       # 95% success rate
    "max_timeout_rate": 0.05,       # 5% timeout threshold
    "max_429_rate": 0.01,           # 1% rate limit errors
}
```

**Output:**

```python
{
    "concurrency": 100,
    "total_queries": 100,
    "successes": 97,
    "failures": 3,
    "elapsed_seconds": 1.2,
    "qps": 83.3,
    "avg_latency_ms": 1200,
    "p99_latency_ms": 2100,
    "bottlenecks": ["rate_limit: 2", "timeout: 1"]
}
```

---

### 4. Cost Tracker

**File:** `backend/app/benchmark/cost_tracker.py`

**Purpose:** Track API usage and estimate costs.

**Pricing Table:**

| Service | Pricing (per 1000 tokens) | Notes |
|---------|---------------------------|-------|
| DashScope Embedding | $0.00007 | $0.07/1M tokens |
| DashScope Rerank | $0.0001 | $0.1/1M tokens |
| DeepSeek Chat | $0.00028 | $0.28/1M input |
| Qdrant Cloud | - | Fixed monthly cost |

**Output:**

```python
{
    "total_tokens": 125000,
    "embedding_tokens": 80000,
    "rerank_tokens": 30000,
    "llm_tokens": 15000,
    "estimated_cost_usd": 0.012,
    "queries": 97,
    "avg_tokens_per_query": 1289,
    "cost_per_query_usd": 0.000124
}
```

---

### 5. Report Generator

**File:** `backend/app/benchmark/report_generator.py`

**Purpose:** Generate multi-format benchmark reports.

**Output Formats:**

#### Terminal Output (Colored)

```
═══════════════════════════════════════════════════════════════════
  AUREON RAG - Railway Production Benchmark
═══════════════════════════════════════════════════════════════════

> Environment
  Mode:          Railway Production
  Vector:        Qdrant Cloud
  Embedding:     DashScope text-embedding-v4
  Rerank:        DashScope qwen3-rerank

> Retrieval Quality
  Recall@5:      96.2%  ✅ (target: ≥95%)
  MRR:           0.847  ✅ (target: ≥0.80)
  nDCG@10:       0.892  ✅ (target: ≥0.80)

> Latency
  P50:           18.5ms ✅ (target: ≤20ms)
  P90:           45.2ms ✅
  P99:           125.3ms

> Concurrency (100 concurrent)
  QPS:           83.5   ✅ (target: ≥50)
  Success rate:  97.5%  ✅ (target: ≥95%)
  Avg latency:   1.2s
  P99 latency:   2.1s   ✅ (target: ≤3s)

> Cost Analysis
  Total tokens:  125,000
  Cost/query:    $0.000124
  Total cost:    $0.012

═══════════════════════════════════════════════════════════════════
```

#### JSON Report

```json
{
  "metadata": {
    "timestamp": "2026-06-10T15:30:00Z",
    "commit_hash": "f1a0aea",
    "environment": "railway",
    "vector_backend": "qdrant",
    "embedding_provider": "dashscope"
  },
  "quality": {
    "recall_at_3": 0.945,
    "recall_at_5": 0.962,
    "recall_at_10": 0.978,
    "precision_at_3": 0.887,
    "mrr": 0.847,
    "ndcg_at_10": 0.892
  },
  "latency": {
    "single_query_ms": 185.3,
    "p50_ms": 18.5,
    "p90_ms": 45.2,
    "p99_ms": 125.3
  },
  "concurrency": [
    {"level": 1, "qps": 12.5, "p99_ms": 180},
    {"level": 10, "qps": 45.2, "p99_ms": 450},
    {"level": 50, "qps": 78.3, "p99_ms": 1200},
    {"level": 100, "qps": 83.5, "p99_ms": 2100}
  ],
  "cost": {
    "total_tokens": 125000,
    "embedding_tokens": 80000,
    "rerank_tokens": 30000,
    "llm_tokens": 15000,
    "estimated_cost_usd": 0.012,
    "cost_per_query_usd": 0.000124
  }
}
```

#### Markdown Report

See Section 6 for full template.

---

## Test Cases

### Retrieval Quality Test

**File:** `backend/app/rag/test_data.py` (existing)

**Test Cases:**
- 97 QA pairs covering:
  - Factual queries (60%)
  - Reasoning queries (20%)
  - Synthesis queries (10%)
  - Negative queries (10%)
  - Cross-article queries (complex)

**Metrics:**

| Metric | Target | Excellent |
|--------|--------|-----------|
| Recall@3 | ≥90% | ≥95% |
| Recall@5 | ≥95% | ≥97% |
| Recall@10 | ≥97% | 100% |
| Precision@3 | ≥80% | ≥90% |
| MRR | ≥0.80 | ≥0.90 |
| nDCG@10 | ≥0.80 | ≥0.90 |

### Concurrency Test

**Concurrency Levels:** 1, 10, 25, 50, 75, 100

**Test Duration:** 30 seconds per level

**Metrics:**

| Level | QPS Target | P99 Target | Success Rate |
|-------|------------|------------|--------------|
| 1 | ≥10 | ≤200ms | 100% |
| 10 | ≥40 | ≤500ms | ≥99% |
| 50 | ≥70 | ≤1.5s | ≥98% |
| 100 | ≥50 | ≤3s | ≥95% |

---

## Configuration

### Railway Environment Variables

```bash
# Benchmark Mode
BENCHMARK_MODE=railway
RAILWAY_API_URL=https://your-service.up.railway.app
RAILWAY_API_KEY=your-api-key

# Concurrency Optimization
LLM_SEMAPHORE_DEEPSEEK=80
LLM_SEMAPHORE_EMBEDDING=80
RAG_SEMAPHORE=80
RERANK_SEMAPHORE=40
QUEUE_TIMEOUT_SECONDS=60

# HTTP Optimization
HTTP_POOL_LIMIT=100
HTTP_KEEPALIVE=true
HTTP_TIMEOUT=30

# Vector Backend
VECTOR_BACKEND=qdrant
QDRANT_URL=https://your-qdrant.cloud
QDRANT_API_KEY=your-qdrant-key

# Embedding
EMBEDDING_PROVIDER=dashscope
DASHSCOPE_API_KEY=your-dashscope-key
```

### Railway Service Configuration

```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "numReplicas": 1,
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

---

## Error Handling

### Timeouts

```python
# Queue timeout (semaphore wait)
QUEUE_TIMEOUT_SECONDS = 60  # Railway environment

# HTTP request timeout
HTTP_TIMEOUT = 30  # seconds

# Health check timeout
HEALTH_CHECK_TIMEOUT = 10  # seconds
```

### Rate Limiting (429 Errors)

```python
async def handle_rate_limit(retry_after: int):
    """Handle API rate limit with exponential backoff."""
    if retry_after:
        await asyncio.sleep(retry_after)
    else:
        # Exponential backoff
        await asyncio.sleep(2 ** retry_count)
```

### Graceful Degradation

```python
if failures > total * 0.1:  # More than 10% failures
    print("⚠️  High failure rate detected")
    print("   Recommendations:")
    print("   - Reduce concurrency level")
    print("   - Check API rate limits")
    print("   - Verify network connectivity")
```

---

## File Structure

```
backend/
├── app/
│   ├── benchmark/
│   │   ├── __init__.py
│   │   ├── config.py              # BenchmarkEnv, ConcurrencyConfig
│   │   ├── http_client.py         # RailwayBenchmarkClient
│   │   ├── concurrency_test.py    # ConcurrencyTestSuite
│   │   ├── cost_tracker.py        # CostTracker
│   │   └── report_generator.py    # generate_markdown_report()
│   └── ...
└── tests/
    ├── run_benchmark.py           # Main entry (updated)
    ├── benchmark_rag.py           # Quality tests (existing)
    ├── benchmark_enterprise.py    # Enterprise tests (existing)
    └── benchmark_concurrent.py    # Concurrency tests (existing)
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (1 day)

1. Create `backend/app/benchmark/` module
2. Implement `BenchmarkConfig` with environment detection
3. Implement `RailwayBenchmarkClient` with connection pool
4. Add environment variable parsing

### Phase 2: Concurrency Testing (1 day)

1. Implement `ConcurrencyTestSuite`
2. Add gradual scaling logic (1 → 100)
3. Implement bottleneck detection
4. Add P99 latency tracking

### Phase 3: Cost Tracking (0.5 day)

1. Implement `CostTracker`
2. Add pricing tables
3. Integrate with existing benchmark flows

### Phase 4: Report Generation (0.5 day)

1. Implement `generate_markdown_report()`
2. Enhance terminal output with colors
3. Add JSON report format

### Phase 5: Integration & Testing (1 day)

1. Update `run_benchmark.py` with Railway mode
2. Add CLI arguments (--mode, --full, --compare)
3. Test with Railway deployment
4. Validate 100 concurrent performance

---

## Validation Criteria

### Retrieval Quality

- [ ] Recall@5 ≥ 95% on 97 QA test set
- [ ] MRR ≥ 0.80
- [ ] nDCG@10 ≥ 0.80

### Latency

- [ ] Single query P50 < 20ms
- [ ] Hybrid retrieval latency < 50ms
- [ ] No timeout errors in normal load

### Concurrency

- [ ] Support 50 concurrent with QPS ≥ 70
- [ ] Support 100 concurrent with QPS ≥ 50
- [ ] Success rate ≥ 95% at 100 concurrent
- [ ] P99 latency < 3s at 100 concurrent

### Cost Efficiency

- [ ] Cost per query < $0.001
- [ ] Token usage tracking accurate
- [ ] No unnecessary API calls

### Reports

- [ ] Terminal output with colors and emojis
- [ ] JSON report saved to data/
- [ ] Markdown report generated
- [ ] Historical comparison supported (--compare)

---

## Comparison with Existing Implementation

### Changes to Existing Files

| File | Changes |
|------|---------|
| `run_benchmark.py` | Add Railway mode, CLI args, report generation |
| `benchmark_concurrent.py` | Add 100 concurrent test level |
| `benchmark_enterprise.py` | Add Railway environment support |

### New Files

| File | Purpose |
|------|---------|
| `app/benchmark/__init__.py` | Module initialization |
| `app/benchmark/config.py` | Configuration management |
| `app/benchmark/http_client.py` | HTTP client for Railway |
| `app/benchmark/concurrency_test.py` | 100-concurrent test suite |
| `app/benchmark/cost_tracker.py` | Cost tracking |
| `app/benchmark/report_generator.py` | Report generation |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Railway resource limits | Performance degradation | Monitor CPU/memory, adjust concurrency |
| API rate limits | 429 errors | Implement exponential backoff, track limits |
| Network latency | High P99 | Connection pool, keepalive, retry logic |
| Cost overrun | Budget exceeded | Cost tracking, alert thresholds |

---

## References

- [RAGAS Framework](https://docs.ragas.io/)
- [BEIR Benchmark](https://github.com/beir-cellar/beir)
- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
- [NVIDIA Enterprise RAG](https://developer.nvidia.com/blog/building-enterprise-rag-applications/)
- [Railway Performance Optimization](https://docs.railway.com/reference/performance)

---

## Approval

- [ ] Design reviewed by team
- [ ] Performance thresholds validated
- [ ] Cost estimates approved
- [ ] Implementation timeline confirmed

**Next Step:** Proceed to implementation planning with writing-plans skill.
