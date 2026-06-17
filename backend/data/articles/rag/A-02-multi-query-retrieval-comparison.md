# Multi-Query 检索策略对比

## 什么是 Multi-Query 检索

Multi-Query 检索是一种查询扩展技术，通过将用户原始查询改写为多个不同角度的子查询，分别检索后合并结果，从而提高召回率和覆盖度。与 HyDE 生成假设文档不同，Multi-Query 生成的是**多个查询变体**，每个变体从不同语义角度表达相同的信息需求。

### 核心思想

用户查询往往表达模糊或角度单一，单一检索容易遗漏相关文档。Multi-Query 通过 LLM 生成多个语义等价但表述不同的查询，从多个角度检索，最终融合为更全面的结果集。

## Multi-Query 的主要策略

### 策略一：LLM 改写（Query Rewriting）

让 LLM 将原始查询改写为多个不同表述：

```python
multi_query_prompt = """你是一个查询改写助手。请将以下查询改写为 {n} 个不同角度的版本，
保持核心意图不变，但使用不同的词汇和表述方式。

原始查询：{query}

改写版本："""

async def generate_multi_queries(query: str, llm, n: int = 3) -> list[str]:
    response = await llm.ainvoke(multi_query_prompt.format(n=n, query=query))
    # 解析 LLM 输出为多个查询
    queries = [line.strip() for line in response.split("\n") if line.strip()]
    return [query] + queries  # 保留原始查询
```

### 策略二：Step-Back Prompting

让 LLM 从更高层次抽象原始查询，生成更宽泛的"后退"查询：

```python
stepback_prompt = """你是一个查询抽象助手。请将以下具体查询抽象为更一般性的问题，
关注背后的概念和原理，而非具体细节。

原始查询：{query}

抽象问题："""

async def stepback_query(query: str, llm) -> list[str]:
    abstract = await llm.ainvoke(stepback_prompt.format(query=query))
    return [query, abstract]
```

### 策略三：Query Decomposition

将复杂查询分解为多个子问题，分别检索：

```python
decomposition_prompt = """你是一个查询分解助手。请将以下复杂查询分解为 {n} 个简单的子问题，
每个子问题可以独立回答，组合起来能回答原始查询。

原始查询：{query}

子问题："""

async def decompose_query(query: str, llm, n: int = 3) -> list[str]:
    response = await llm.ainvoke(decomposition_prompt.format(n=n, query=query))
    sub_queries = [line.strip() for line in response.split("\n") if line.strip()]
    return sub_queries
```

## 三种策略对比

| 维度 | Query Rewriting | Step-Back | Decomposition |
|------|----------------|-----------|---------------|
| **适用场景** | 查询表述模糊 | 需要背景知识 | 复杂多步推理 |
| **改写方向** | 同层同义替换 | 向上抽象 | 向下分解 |
| **检索覆盖** | 横向扩展 | 纵向扩展 | 结构化覆盖 |
| **LLM 调用次数** | 1 次 | 1 次 | 1 次 |
| **结果融合难度** | 低（RRF 即可） | 中（需权重调整） | 高（需答案合成） |
| **延迟影响** | +300-800ms | +300-800ms | +300-800ms + 合成 |

## 检索结果融合方法

### Reciprocal Rank Fusion (RRF)

最常用的融合方法，基于排名的倒数加权：

```python
def reciprocal_rank_fusion(
    result_lists: list[list], k: int = 60, weights: list[float] | None = None
) -> list:
    """RRF 融合多个检索结果列表

    Args:
        result_lists: 多个检索结果列表
        k: RRF 参数，防止排名靠前的结果权重过大
        weights: 各列表的权重，默认等权
    """
    if weights is None:
        weights = [1.0] * len(result_lists)

    scores = {}
    for results, weight in zip(result_lists, weights):
        for rank, doc in enumerate(results):
            doc_id = doc.metadata.get("id", hash(doc.page_content))
            if doc_id not in scores:
                scores[doc_id] = {"score": 0, "doc": doc}
            scores[doc_id]["score"] += weight / (k + rank + 1)

    sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return [item["doc"] for item in sorted_results]
```

### 加权分数融合

对于有相似度分数的检索结果，可以直接加权融合：

```python
def weighted_score_fusion(
    result_lists: list[list[tuple]], weights: list[float]
) -> list:
    """加权分数融合

    Args:
        result_lists: 每个元素为 (doc, score) 列表
        weights: 各列表的权重
    """
    scores = {}
    for results, weight in zip(result_lists, weights):
        for doc, score in results:
            doc_id = doc.metadata.get("id", hash(doc.page_content))
            if doc_id not in scores:
                scores[doc_id] = {"score": 0, "doc": doc}
            scores[doc_id]["score"] += weight * score

    sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return [item["doc"] for item in sorted_results]
```

## Multi-Query 的性能考量

### 延迟优化

Multi-Query 的主要延迟来自两个方面：LLM 改写调用和多次检索。优化策略：

1. **并行检索**：多个子查询并行执行，延迟取 max 而非 sum
2. **轻量改写模型**：使用 flash 级别模型进行改写，延迟约 200-400ms
3. **条件触发**：仅对中等/复杂查询启用 Multi-Query

```python
async def parallel_multi_query_retrieve(
    queries: list[str], embedder, vectorstore, k: int = 5
) -> list[list]:
    """并行执行多个查询的检索"""
    tasks = [
        vectorstore.asimilarity_search(q, k=k*2)
        for q in queries
    ]
    results = await asyncio.gather(*tasks)
    return results
```

### 召回率 vs 精度权衡

- **更多子查询** → 更高召回率，但精度可能下降（噪声增加）
- **更少子查询** → 更高精度，但可能遗漏相关文档
- **经验值**：3-5 个子查询通常是最优平衡点

## Multi-Query 与 HyDE 的组合

在 Aureon 的复杂查询路径中，Multi-Query 与 HyDE 组合使用：

```
复杂查询 → HyDE 生成假设文档 → Multi-Query 生成子查询
→ 所有查询并行 Hybrid 检索 → RRF 融合 → Ensemble Rerank → CRAG
```

这种组合策略在 Aureon 的 Benchmark 中表现优异：
- Recall@5 从 87% 提升到 92.4%
- MRR 从 0.82 提升到 0.888
- 代价是复杂查询延迟从 ~3s 增加到 ~5s

## 关键事实

1. **Multi-Query 检索通过 LLM 将原始查询改写为多个语义等价的子查询**，从不同角度检索以提高召回率
2. **三种主要策略**：Query Rewriting（同义改写）、Step-Back（抽象后退）、Decomposition（分解子问题），分别适用于不同场景
3. **RRF（Reciprocal Rank Fusion）是最常用的结果融合方法**，公式为 `score = Σ(1/(k+rank))`，k 通常取 60
4. **3-5 个子查询是最优平衡点**，更多子查询提高召回但增加噪声和延迟
5. **Multi-Query 与 HyDE 组合使用**可在复杂查询场景下将 Recall@5 提升约 5 个百分点，但延迟增加约 2s
