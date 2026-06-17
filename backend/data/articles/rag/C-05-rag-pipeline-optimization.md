# RAG Pipeline 优化：从串行到并行

## 串行 Pipeline 的瓶颈

传统 RAG Pipeline 是串行执行的：查询理解 → 检索 → Rerank → 压缩 → 生成，每一步等待上一步完成。这导致延迟累积，端到端延迟往往超过 5 秒。

### 串行延迟分析

```
查询路由:  300ms  ████████
检索:      50ms   ██
Rerank:   200ms   █████
压缩:     100ms   ███
生成:    1000ms   ██████████████████████
───────────────────────────────────────
总计:    1650ms
```

## 并行化策略

### 策略一：检索并行化

多路检索可以并行执行：

```python
import asyncio

async def parallel_retrieve(
    query: str,
    dense_retriever,
    sparse_retriever,
    k: int = 20,
) -> list:
    """并行执行 Dense 和 Sparse 检索"""
    # 并行执行两路检索
    dense_task = dense_retriever.aretrieve(query, k=k)
    sparse_task = sparse_retriever.aretrieve(query, k=k)

    dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)

    # RRF 融合
    fused = reciprocal_rank_fusion([dense_results, sparse_results])
    return fused

# 延迟对比：
# 串行：50ms (dense) + 8ms (sparse) = 58ms
# 并行：max(50ms, 8ms) = 50ms
# 节省：8ms（sparse 检索免费）
```

### 策略二：Multi-Query 并行检索

```python
async def parallel_multi_query(
    query: str,
    llm,
    retriever,
    n_queries: int = 3,
    k: int = 20,
) -> list:
    """Multi-Query 并行检索"""
    # 1. 生成子查询（串行，约 300ms）
    sub_queries = await generate_sub_queries(query, llm, n=n_queries)

    # 2. 并行检索所有子查询
    tasks = [retriever.aretrieve(sq, k=k) for sq in sub_queries]
    # 加上原始查询
    tasks.append(retriever.aretrieve(query, k=k))

    all_results = await asyncio.gather(*tasks)

    # 3. RRF 融合
    return reciprocal_rank_fusion(all_results)

# 延迟对比：
# 串行：4 × 50ms = 200ms
# 并行：max(50ms, 50ms, 50ms, 50ms) = 50ms
# 节省：150ms
```

### 策略三：HyDE + 原始查询并行

```python
async def parallel_hyde_retrieve(
    query: str,
    llm,
    embedder,
    vectorstore,
    k: int = 20,
) -> list:
    """HyDE 与原始查询并行检索"""
    # 1. 并行：生成假设文档 + 原始查询检索
    hyde_task = generate_hypothetical_doc(query, llm)
    original_task = vectorstore.asimilarity_search(query, k=k)

    hypothetical_doc, original_results = await asyncio.gather(hyde_task, original_task)

    # 2. HyDE 检索
    hyde_embedding = await embedder.aembed_query(hypothetical_doc)
    hyde_results = await vectorstore.asimilarity_search_by_vector(hyde_embedding, k=k)

    # 3. RRF 融合
    return reciprocal_rank_fusion([original_results, hyde_results])

# 延迟对比：
# 串行：300ms (HyDE) + 50ms (检索) + 50ms (HyDE 检索) = 400ms
# 并行：max(300ms, 50ms) + 50ms = 350ms
# 节省：50ms
```

### 策略四：Rerank 批量化

```python
async def batch_rerank(
    query: str,
    candidates: list,
    reranker_api,
    batch_size: int = 20,
    max_concurrency: int = 3,
) -> list:
    """批量并发 Rerank"""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def rerank_batch(batch):
        async with semaphore:
            return await reranker_api.arerank(query, batch)

    # 分批
    batches = [candidates[i:i+batch_size] for i in range(0, len(candidates), batch_size)]

    # 并发 Rerank
    batch_results = await asyncio.gather(*[rerank_batch(b) for b in batches])

    # 合并结果
    all_results = []
    for results in batch_results:
        all_results.extend(results)

    all_results.sort(key=lambda x: x.score, reverse=True)
    return all_results

# 延迟对比（35 候选）：
# 串行：1 × 200ms = 200ms
# 批量并发（2 批）：max(200ms, 200ms) = 200ms（但 API 限制放宽时更快）
```

## 完整并行 Pipeline

### 架构图

```
查询 → 查询路由 ──────────────────────────────────────────────────┐
  │                                                               │
  ├── 简单 ──→ 纯 Sparse ──────────────────────────────→ 生成     │
  │                                                               │
  ├── 中等 ──→ ┌ Dense ──┐                                      │
  │           └ Sparse ─┘ → RRF → 自适应 Rerank ──→ 生成        │
  │                                                               │
  └── 复杂 ──→ ┌ HyDE 生成 ─┐ → ┌ Dense ──┐                    │
               └ 原始查询  ─┘   └ Sparse ─┘ → RRF               │
                                                   │              │
               ┌ Multi-Query 1 ─┐                 │              │
               │ Multi-Query 2 ─┤ → RRF ──────────┤              │
               └ Multi-Query 3 ─┘                 │              │
                                                   ↓              │
                              Rerank → CRAG → 压缩 → 生成 ←──────┘
```

### 实现

```python
class ParallelRAGPipeline:
    """并行 RAG Pipeline"""

    async def run(self, query: str, k: int = 5) -> dict:
        # 1. 查询路由
        route = await self.router.route(query)

        if route == "simple":
            return await self._simple_pipeline(query, k)
        elif route == "medium":
            return await self._medium_pipeline(query, k)
        else:
            return await self._complex_pipeline(query, k)

    async def _complex_pipeline(self, query: str, k: int) -> dict:
        """复杂查询并行 Pipeline"""
        # 阶段 1：并行生成 HyDE + 子查询
        hyde_task = self._generate_hyde(query)
        multi_query_task = self._generate_sub_queries(query)
        route_result = await asyncio.gather(hyde_task, multi_query_task)
        hypothetical_doc, sub_queries = route_result

        # 阶段 2：并行检索所有查询
        all_queries = [query, hypothetical_doc] + sub_queries
        retrieve_tasks = [
            self._hybrid_retrieve(q) for q in all_queries
        ]
        all_results = await asyncio.gather(*retrieve_tasks)

        # 阶段 3：RRF 融合
        fused = reciprocal_rank_fusion(all_results)

        # 阶段 4：Rerank
        reranked = await self.reranker.arerank(query, fused, top_k=k*2)

        # 阶段 5：CRAG + 压缩（并行）
        crag_task = self._crag_evaluate(query, reranked)
        compress_task = self._compress(query, reranked)
        crag_result, compressed = await asyncio.gather(crag_task, compress_task)

        # 阶段 6：生成
        answer = await self._generate(query, compressed[:k])

        return {"answer": answer, "route": "complex"}

    async def _hybrid_retrieve(self, query: str) -> list:
        """并行 Hybrid 检索"""
        dense_task = self.vectorstore.asimilarity_search(query, k=20)
        sparse_task = self.sparse_search(query, k=20)
        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)
        return reciprocal_rank_fusion([dense_results, sparse_results])
```

## 延迟优化效果

### 优化前后对比

| Pipeline | 串行延迟 | 并行延迟 | 节省 |
|----------|---------|---------|------|
| 简单查询 | 58ms | 8ms | 86% |
| 中等查询 | 350ms | 120ms | 66% |
| 复杂查询 | 5000ms | 3000ms | 40% |

### Aureon 实测

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| TTFT P50 | 1200ms | 610ms |
| E2E P50 | 2000ms | 980ms |
| 复杂查询 E2E | 8s | 5s |

## 关键事实

1. **串行 RAG Pipeline 的延迟是各步骤之和**，而并行化可以将延迟降为关键路径上步骤的最大值
2. **Dense + Sparse 并行检索是最基本的并行优化**，将延迟从 sum(dense, sparse) 降为 max(dense, sparse)
3. **Multi-Query 并行检索**将多个子查询的检索延迟从 n×50ms 降为 max(50ms) ≈ 50ms
4. **HyDE + 原始查询并行**可以在生成假设文档的同时执行原始查询检索，节省约 50ms
5. **Aureon 的并行 Pipeline 将 TTFT P50 从 1200ms 降至 610ms**，E2E P50 从 2000ms 降至 980ms
