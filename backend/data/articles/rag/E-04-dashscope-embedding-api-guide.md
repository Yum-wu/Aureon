# DashScope Embedding API 使用指南

## DashScope 简介

DashScope 是阿里云的 AI 模型服务平台，提供 Embedding、Rerank、LLM 等 API。Aureon 使用 DashScope 新加坡节点作为 Embedding 和 Rerank 的主力 API。

## Embedding API

### 端点配置

```python
# DashScope Embedding 端点（新加坡节点）
EMBEDDING_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# 注意：Embedding 使用 compatible-mode
# Rerank 使用 compatible-api（不是 compatible-mode）
RERANK_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-api/v1"
```

### 调用方式

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=settings.DASHSCOPE_API_KEY,
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)

async def dashscope_embed(
    texts: list[str],
    model: str = "text-embedding-v3",
    dimensions: int = 1024,
) -> list[list[float]]:
    """DashScope Embedding API"""
    response = await client.embeddings.create(
        input=texts,
        model=model,
        dimensions=dimensions,
    )
    return [item.embedding for item in response.data]
```

### 模型选择

| 模型 | 维度 | 中文效果 | 延迟 | 价格 |
|------|------|---------|------|------|
| text-embedding-v3 | 1024 | 优秀 | ~80ms | ¥0.0007/1K tokens |
| text-embedding-v2 | 1536 | 良好 | ~100ms | ¥0.0007/1K tokens |
| text-embedding-v1 | 1536 | 中等 | ~120ms | ¥0.0007/1K tokens |

## Rerank API

### 调用方式

```python
async def dashscope_rerank(
    query: str,
    documents: list[str],
    top_n: int = 10,
    model: str = "gte-rerank-v2",
) -> list[dict]:
    """DashScope Rerank API"""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://dashscope-intl.aliyuncs.com/compatible-api/v1/rerank",
            json={
                "model": model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": True,
            },
            headers={
                "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    result = response.json()
    return result.get("results", [])
```

## 批量 Rerank 优化

```python
async def batch_rerank(
    query: str,
    candidates: list,
    batch_size: int = 20,
    max_concurrency: int = 2,
) -> list:
    """批量 Rerank：分批并发调用 DashScope API"""
    semaphore = asyncio.Semaphore(max_concurrency)
    all_results = []

    async def rerank_batch(batch):
        async with semaphore:
            docs = [d.page_content for d in batch]
            results = await dashscope_rerank(query, docs, top_n=len(batch))
            return [(batch[r["index"]], r["relevance_score"]) for r in results]

    batches = [candidates[i:i+batch_size] for i in range(0, len(candidates), batch_size)]
    batch_results = await asyncio.gather(*[rerank_batch(b) for b in batches])

    for results in batch_results:
        all_results.extend(results)

    all_results.sort(key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in all_results]
```

## 关键事实

1. **DashScope Embedding 使用 `compatible-mode` 端点**，Rerank 使用 `compatible-api` 端点，两者不同
2. **新加坡节点延迟约 80ms**，比 OpenAI API 快 3-5 倍，是亚太地区用户的最优选择
3. **text-embedding-v3 是最新模型**，支持 1024 维输出，中文效果优秀
4. **批量 Rerank 使用 Semaphore 控制并发**，DashScope API 限制建议并发不超过 2
5. **Aureon 的 DashScope 配置**：Embedding 月成本约 ¥15，Rerank 月成本约 ¥30，是性价比最高的 API 方案
