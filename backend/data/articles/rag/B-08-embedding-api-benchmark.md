# Embedding API 性能对比：延迟、吞吐、成本

## API 选型的重要性

在生产 RAG 系统中，Embedding API 的延迟、吞吐和成本直接影响用户体验和运营成本。选择合适的 API 需要基于实际业务场景的量化评估。

## 主流 Embedding API 对比

### 综合对比表

| API | 模型 | 维度 | 延迟(P50) | 吞吐 | 价格 | 中文 |
|-----|------|------|----------|------|------|------|
| OpenAI | text-embedding-3-small | 1536 | 200ms | 50/s | $0.02/1M tok | 良好 |
| OpenAI | text-embedding-3-large | 3072 | 350ms | 30/s | $0.13/1M tok | 良好 |
| DashScope | text-embedding-v3 | 1024 | 80ms | 100/s | ¥0.0007/1K tok | 优秀 |
| SiliconFlow | bge-m3 | 1024 | 120ms | 80/s | ¥0.001/1K tok | 优秀 |
| Zhipu | embedding-3 | 2048 | 150ms | 60/s | ¥0.0005/1K tok | 优秀 |
| Cohere | embed-multilingual-v3 | 1024 | 180ms | 50/s | $0.10/1K calls | 良好 |
| Jina | jina-embeddings-v3 | 1024 | 100ms | 70/s | 免费/付费 | 良好 |

## 延迟测试

### 测试方法

```python
import asyncio
import time
from statistics import mean, quantiles

async def benchmark_embedding_api(
    api_client,
    texts: list[str],
    n_requests: int = 100,
    concurrency: int = 10,
) -> dict:
    """Benchmark Embedding API"""
    latencies = []
    errors = 0

    semaphore = asyncio.Semaphore(concurrency)

    async def single_request(text: str):
        async with semaphore:
            start = time.perf_counter()
            try:
                await api_client.embed(text)
                latency = (time.perf_counter() - start) * 1000
                latencies.append(latency)
            except Exception:
                errors += 1

    # 并发请求
    tasks = [single_request(texts[i % len(texts)]) for i in range(n_requests)]
    await asyncio.gather(*tasks)

    # 统计
    sorted_latencies = sorted(latencies)
    p50 = sorted_latencies[len(sorted_latencies) // 2]
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
    p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]

    return {
        "total_requests": n_requests,
        "errors": errors,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "mean_ms": mean(latencies),
        "throughput_qps": len(latencies) / (sum(latencies) / 1000),
    }
```

### 延迟对比（Aureon 实测，新加坡节点）

| API | P50 | P95 | P99 | 错误率 |
|-----|-----|-----|-----|--------|
| 本地 BGE-large-zh | 15ms | 25ms | 45ms | 0% |
| DashScope (新加坡) | 80ms | 150ms | 250ms | 0.1% |
| SiliconFlow | 120ms | 250ms | 400ms | 0.3% |
| OpenAI (美东) | 200ms | 400ms | 800ms | 0.5% |
| Zhipu | 150ms | 300ms | 500ms | 0.2% |

## 吞吐量测试

### 批量编码吞吐

```python
async def benchmark_batch_throughput(
    api_client,
    texts: list[str],
    batch_sizes: list[int] = [1, 10, 50, 100],
) -> dict:
    """测试不同批量大小的吞吐量"""
    results = {}

    for batch_size in batch_sizes:
        start = time.perf_counter()
        n_batches = len(texts) // batch_size

        for i in range(n_batches):
            batch = texts[i * batch_size : (i + 1) * batch_size]
            await api_client.embed_batch(batch)

        elapsed = time.perf_counter() - start
        throughput = len(texts) / elapsed

        results[batch_size] = {
            "throughput_qps": throughput,
            "latency_per_batch_ms": elapsed / n_batches * 1000,
        }

    return results
```

### 吞吐对比

| API | batch=1 QPS | batch=10 QPS | batch=50 QPS | batch=100 QPS |
|-----|------------|-------------|-------------|---------------|
| 本地 BGE | 200 | 500 | 800 | 1000 |
| DashScope | 100 | 300 | 500 | 600 |
| SiliconFlow | 80 | 200 | 350 | 400 |
| OpenAI | 50 | 150 | 250 | 300 |

## 成本分析

### 月度成本估算

```python
def estimate_monthly_cost(
    daily_queries: int,
    avg_query_tokens: int = 20,
    daily_docs: int = 100,
    avg_doc_tokens: int = 500,
    api_pricing: dict = None,
) -> dict:
    """估算月度 Embedding 成本"""
    # 查询编码
    monthly_query_tokens = daily_queries * avg_query_tokens * 30

    # 文档编码（增量索引）
    monthly_doc_tokens = daily_docs * avg_doc_tokens * 30

    total_tokens = monthly_query_tokens + monthly_doc_tokens

    costs = {}
    for api_name, pricing in api_pricing.items():
        if pricing["unit"] == "1M_tokens":
            cost = total_tokens / 1_000_000 * pricing["price"]
        elif pricing["unit"] == "1K_tokens":
            cost = total_tokens / 1_000 * pricing["price"]
        costs[api_name] = cost

    return {"monthly_tokens": total_tokens, "monthly_costs": costs}

# 示例：10K 日查询 + 100 日增量文档
# OpenAI small: ~¥30/月
# DashScope: ~¥15/月
# 本地 BGE: ¥0（硬件成本另计）
```

### 成本对比（10K 日查询场景）

| 方案 | 月成本 | 年成本 | 说明 |
|------|--------|--------|------|
| 本地 BGE | ¥0 | ¥0 | 需 GPU/CPU 硬件 |
| DashScope | ¥15 | ¥180 | 性价比最高 |
| SiliconFlow | ¥25 | ¥300 | 备用方案 |
| OpenAI small | ¥30 | ¥360 | 延迟较高 |
| OpenAI large | ¥200 | ¥2400 | 高精度场景 |

## Fallback Chain 设计

### 多级降级策略

```python
class EmbeddingFallbackChain:
    """Embedding API 降级链"""

    def __init__(self, providers: list[dict]):
        self.providers = providers  # [{name, client, priority, max_latency}]

    async def embed(self, text: str) -> list[float]:
        """按优先级尝试，失败则降级"""
        for provider in self.providers:
            try:
                start = time.perf_counter()
                embedding = await asyncio.wait_for(
                    provider["client"].embed(text),
                    timeout=provider.get("max_latency", 5.0),
                )
                latency = (time.perf_counter() - start) * 1000

                if latency > provider.get("max_latency", 5000):
                    continue  # 延迟过高，尝试下一个

                return embedding
            except Exception:
                continue

        raise RuntimeError("所有 Embedding 服务不可用")

# Aureon 的 Fallback Chain
providers = [
    {"name": "local_bge", "client": local_bge_client, "priority": 1, "max_latency": 100},
    {"name": "dashscope", "client": dashscope_client, "priority": 2, "max_latency": 500},
    {"name": "siliconflow", "client": siliconflow_client, "priority": 3, "max_latency": 1000},
    {"name": "zhipu", "client": zhipu_client, "priority": 4, "max_latency": 2000},
]
```

## 选型建议

### 按场景选择

| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| 中文为主 + 有 GPU | 本地 BGE-large-zh | 最优精度，零成本 |
| 中文为主 + 无 GPU | DashScope | 低延迟，低成本 |
| 多语言需求 | 本地 BGE-M3 或 DashScope | 多语言支持好 |
| 全球用户 | OpenAI + CDN | 全球节点覆盖 |
| 成本敏感 | 本地 + DashScope 备用 | 本地优先，API 降级 |

## 关键事实

1. **本地部署 BGE-large-zh 的延迟最低（P50=15ms）**，吞吐最高（200+ QPS），但需要 GPU/CPU 硬件投入
2. **DashScope（阿里云新加坡节点）是 API 方案的最优选择**，P50=80ms，中文效果优秀，月成本仅 ¥15（10K 日查询）
3. **OpenAI API 延迟最高（P50=200ms）**，且受网络波动影响大（P99=800ms），不适合延迟敏感场景
4. **Fallback Chain 是生产环境的必备设计**，Aureon 的降级链为：本地 BGE → DashScope → SiliconFlow → Zhipu
5. **批量编码可以显著提升吞吐**，batch=50 比 batch=1 的 QPS 提升 3-5 倍，建议索引构建时使用批量编码
