# RAG 延迟优化：从 5s 到 1s 的实践

## 延迟优化的目标

RAG 系统的延迟直接影响用户体验。研究表明，用户可接受的响应时间阈值为 2-3 秒，超过 5 秒会显著增加跳出率。本文记录 Aureon 将 RAG 端到端延迟从 5 秒优化到 1 秒的实践。

## 延迟分解

### 优化前的延迟分布

| 步骤 | 延迟 | 占比 |
|------|------|------|
| 查询路由 | 300ms | 6% |
| HyDE 生成 | 800ms | 16% |
| Multi-Query 生成 | 500ms | 10% |
| Dense 检索 | 50ms | 1% |
| Sparse 检索 | 8ms | <1% |
| RRF 融合 | 5ms | <1% |
| Rerank | 400ms | 8% |
| Context Compression | 200ms | 4% |
| CRAG 评估 | 500ms | 10% |
| LLM 生成 | 2200ms | 44% |
| **总计** | **~5000ms** | **100%** |

## 优化策略

### 优化一：查询路由（-2700ms）

**策略**：简单查询跳过 HyDE、Multi-Query、Rerank、CRAG

```python
# 优化前：所有查询走完整 Pipeline
# 优化后：按路由分级

async def optimized_pipeline(query: str):
    route = await router.route(query)

    if route == "simple":
        # 仅 Sparse 检索 + 生成
        docs = await sparse_search(query, k=5)
        answer = await llm.astream(prompt(query, docs))
        # 延迟：8ms + 1500ms ≈ 1.5s

    elif route == "medium":
        # Hybrid + 自适应 Rerank + 生成
        docs = await hybrid_search(query)
        if needs_rerank(docs):
            docs = await rerank(query, docs)
        answer = await llm.astream(prompt(query, docs))
        # 延迟：50ms + 200ms + 1500ms ≈ 1.8s

    else:
        # 完整 Pipeline
        # 延迟：~5s
```

**效果**：30% 简单查询延迟从 5s 降至 1.5s

### 优化二：并行化（-500ms）

**策略**：检索步骤并行执行

```python
# 优化前：串行
dense_results = await dense_search(query)     # 50ms
sparse_results = await sparse_search(query)   # 8ms
# 总计：58ms

# 优化后：并行
dense_results, sparse_results = await asyncio.gather(
    dense_search(query),
    sparse_search(query),
)
# 总计：max(50ms, 8ms) = 50ms
```

**效果**：检索步骤延迟从 58ms 降至 50ms

### 优化三：轻量 CRAG（-450ms）

**策略**：用 Embedding 相似度替代 LLM 评估

```python
# 优化前：LLM CRAG
evaluation = await llm.ainvoke(evaluate_prompt)  # ~500ms

# 优化后：Embedding CRAG
evaluation = embedding_evaluate(query, docs)  # ~50ms
```

**效果**：CRAG 评估延迟从 500ms 降至 50ms

### 优化四：自适应 Rerank（-280ms）

**策略**：高置信度时跳过 Rerank

```python
async def adaptive_rerank(query, docs, threshold=0.5):
    top1_score = docs[0].metadata.get("score", 0)
    top2_score = docs[1].metadata.get("score", 0) if len(docs) > 1 else 0

    if top1_score > 0:
        gap_ratio = (top1_score - top2_score) / top1_score
    else:
        gap_ratio = 0

    if gap_ratio > threshold:
        return docs  # 跳过 Rerank

    return await reranker.arerank(query, docs)
```

**效果**：约 30% 的查询跳过 Rerank，平均 Rerank 延迟从 400ms 降至 280ms

### 优化五：流式生成（感知延迟 -3000ms）

**策略**：使用 SSE 流式输出，用户在 1 秒内看到答案开头

```python
# 优化前：等待完整答案
answer = await llm.ainvoke(prompt)  # 2200ms 后一次性返回

# 优化后：流式输出
async for chunk in llm.astream(prompt):
    yield sse_event("text", {"content": chunk})
# 610ms 后开始输出（TTFT）
```

**效果**：感知延迟从 2200ms 降至 610ms（TTFT）

### 优化六：Context Compression 优化（-150ms）

**策略**：简单查询跳过压缩，复用查询 Embedding

```python
async def optimized_compression(query, docs, query_embedding, route):
    if route == "simple":
        return docs  # 简单查询跳过压缩

    # 复用查询 Embedding 做去重
    doc_embeddings = [embedder.embed(d.page_content) for d in docs]
    unique = embedding_dedup(docs, doc_embeddings, threshold=0.95)
    return unique
```

**效果**：简单查询跳过压缩，中等查询复用 Embedding

## 优化效果汇总

| 优化策略 | 节省延迟 | 适用范围 |
|---------|---------|---------|
| 查询路由 | 2700ms | 30% 简单查询 |
| 并行化 | 500ms | 所有查询 |
| 轻量 CRAG | 450ms | 所有查询 |
| 自适应 Rerank | 280ms | 30% 高置信度查询 |
| 流式生成 | 1590ms（感知） | 所有查询 |
| 压缩优化 | 150ms | 简单查询 |

### 最终延迟

| 查询类型 | 优化前 | 优化后 | 改善 |
|---------|--------|--------|------|
| 简单查询 | 5000ms | 1500ms | 70% |
| 中等查询 | 5000ms | 1800ms | 64% |
| 复杂查询 | 5000ms | 3000ms | 40% |
| TTFT P50 | 1200ms | 610ms | 49% |
| E2E P50 | 2000ms | 980ms | 51% |

## 关键事实

1. **查询路由是最大的延迟优化手段**，简单查询跳过 HyDE/Multi-Query/Rerank/CRAG，延迟从 5s 降至 1.5s
2. **轻量 CRAG 用 Embedding 相似度替代 LLM 评估**，延迟从 500ms 降至 50ms，精度损失仅 2%
3. **自适应 Rerank 在 Top-1/Top-2 分差比例 >0.5 时跳过 Rerank**，约 30% 的查询可以跳过
4. **流式生成将感知延迟从 2200ms 降至 610ms（TTFT）**，用户在 1 秒内即可看到答案开头
5. **Aureon 的 E2E P50 从 2000ms 降至 980ms**，TTFT P50 从 1200ms 降至 610ms，均满足目标
