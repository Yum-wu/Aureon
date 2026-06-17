# HyDE 原理与实践

## 什么是 HyDE

HyDE（Hypothetical Document Embeddings）是一种检索增强技术，由 Gao 等人在 2022 年提出。其核心思想是：**先让大语言模型生成一个"假设性答案文档"，再用该文档的嵌入向量去检索真实文档**。这种方法利用了 LLM 的语言理解能力，将模糊的查询转化为更接近目标文档语义的表示。

### 核心原理

传统检索流程是 `Query → Embedding → 检索`，而 HyDE 的流程是：

```
Query → LLM 生成假设文档 → 假设文档 Embedding → 检索真实文档
```

关键洞察在于：即使 LLM 生成的假设文档包含事实错误，其**语言模式和词汇分布**仍然与真实相关文档高度相似。因此，假设文档的嵌入向量比原始查询的嵌入向量更接近目标文档。

## HyDE 的工作流程

### 第一步：假设文档生成

将用户查询提交给 LLM，要求其生成一个假设性答案。Prompt 模板通常如下：

```python
hyde_prompt = """请根据以下问题，写一段详细的回答。
即使你不确定答案，也请尽量写出一段看起来合理的回答。

问题：{query}

回答："""
```

### 第二步：嵌入与检索

将假设文档通过 Embedding 模型编码为向量，然后在向量库中检索最相似的文档：

```python
from langchain_core.embeddings import Embeddings

async def hyde_retrieve(query: str, llm, embedder: Embeddings, vectorstore, k: int = 5):
    # 生成假设文档
    hypothetical_doc = await llm.ainvoke(hyde_prompt.format(query=query))

    # 用假设文档的嵌入检索
    hyde_embedding = await embedder.aembed_query(hypothetical_doc)
    results = await vectorstore.asimilarity_search_by_vector(hyde_embedding, k=k)

    return results
```

### 第三步：结果融合（可选）

可以将原始查询的检索结果与 HyDE 检索结果进行 RRF 融合，提升鲁棒性：

```python
async def hyde_with_fusion(query: str, llm, embedder, vectorstore, k: int = 5):
    # 原始查询检索
    query_embedding = await embedder.aembed_query(query)
    query_results = await vectorstore.asimilarity_search_by_vector(query_embedding, k=k*2)

    # HyDE 检索
    hyde_results = await hyde_retrieve(query, llm, embedder, vectorstore, k=k*2)

    # RRF 融合
    fused = reciprocal_rank_fusion([query_results, hyde_results], k=60)
    return fused[:k]
```

## HyDE 的优势与局限

### 优势

1. **语义桥接**：将简短查询扩展为完整文档，弥补查询与文档之间的语义鸿沟
2. **无需训练**：不需要额外的训练数据或模型微调，即插即用
3. **通用性强**：适用于各种领域和查询类型
4. **与 RRF 兼容**：可以与原始查询检索结果融合，降低风险

### 局限

1. **额外延迟**：需要一次 LLM 调用生成假设文档，增加约 500ms-2s 延迟
2. **成本增加**：每次查询多消耗约 100-300 tokens
3. **简单查询收益有限**：对于关键词明确的简单查询，HyDE 可能不优于直接检索
4. **幻觉风险**：假设文档可能引入误导性信息，影响检索方向

## 实践中的优化策略

### 条件触发 HyDE

不是所有查询都需要 HyDE。通过查询路由判断查询复杂度，仅对复杂查询启用 HyDE：

```python
async def adaptive_hyde_retrieve(query: str, query_router, llm, embedder, vectorstore, k: int = 5):
    route = await query_router.aroute(query)

    if route == "simple":
        # 简单查询直接检索
        return await vectorstore.asimilarity_search(query, k=k)
    elif route == "complex":
        # 复杂查询使用 HyDE
        return await hyde_retrieve(query, llm, embedder, vectorstore, k=k)
    else:
        # 中等查询使用融合策略
        return await hyde_with_fusion(query, llm, embedder, vectorstore, k=k)
```

### 多假设文档

生成多个假设文档并分别检索，可以提高召回率：

```python
async def multi_hyde(query: str, llm, embedder, vectorstore, n: int = 3, k: int = 5):
    # 生成 n 个假设文档
    tasks = [llm.ainvoke(hyde_prompt.format(query=query)) for _ in range(n)]
    hypothetical_docs = await asyncio.gather(*tasks)

    # 分别检索并融合
    all_results = []
    for doc in hypothetical_docs:
        embedding = await embedder.aembed_query(doc)
        results = await vectorstore.asimilarity_search_by_vector(embedding, k=k*2)
        all_results.append(results)

    # 加上原始查询
    query_embedding = await embedder.aembed_query(query)
    query_results = await vectorstore.asimilarity_search_by_vector(query_embedding, k=k*2)
    all_results.append(query_results)

    return reciprocal_rank_fusion(all_results, k=60)[:k]
```

### 假设文档缓存

对于相似查询，可以缓存假设文档避免重复生成：

```python
import hashlib

def cache_key(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()

async def cached_hyde(query: str, cache, llm, embedder, vectorstore, k: int = 5):
    key = cache_key(query)
    cached_doc = await cache.get(key)

    if cached_doc:
        hypothetical_doc = cached_doc
    else:
        hypothetical_doc = await llm.ainvoke(hyde_prompt.format(query=query))
        await cache.set(key, hypothetical_doc, ttl=3600)

    embedding = await embedder.aembed_query(hypothetical_doc)
    return await vectorstore.asimilarity_search_by_vector(embedding, k=k)
```

## HyDE 在 Aureon 中的应用

Aureon 的 RAG Pipeline 中，HyDE 作为复杂查询路径的核心组件：

- **查询路由判断**：Adaptive-RAG 将查询分为简单/中等/复杂三级
- **复杂查询路径**：HyDE → Multi-Query → Hybrid → Ensemble Rerank → CRAG
- **延迟控制**：HyDE 使用轻量模型（如 qwen3.5-flash）生成假设文档，延迟约 300-500ms
- **融合策略**：HyDE 结果与原始查询结果通过 RRF 融合，确保不丢失原始检索信号

## 关键事实

1. **HyDE 由 Gao 等人于 2022 年提出**，核心思想是利用 LLM 生成假设文档来桥接查询与文档之间的语义鸿沟
2. **HyDE 的假设文档即使包含事实错误，其嵌入向量仍比原始查询更接近目标文档**，因为语言模式和词汇分布相似
3. **HyDE 会增加约 500ms-2s 的延迟和 100-300 tokens 的成本**，因此建议通过查询路由仅对复杂查询启用
4. **多假设文档策略**通过生成多个假设文档并融合检索结果，可以显著提高召回率
5. **HyDE 与 RRF 融合策略**可以将原始查询检索与 HyDE 检索结果合并，兼顾简单查询和复杂查询的检索效果
