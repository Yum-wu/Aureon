# 检索质量指标：Recall@K、MRR、nDCG 的选择

## 检索质量评估的重要性

检索是 RAG 系统的基础，检索质量直接决定生成质量。选择合适的检索质量指标对于评估和优化检索系统至关重要。不同的指标关注检索质量的不同方面，适用于不同场景。

## Recall@K

### 定义

Recall@K 衡量在前 K 个检索结果中，有多少比例的相关文档被召回：

```
Recall@K = |相关文档 ∩ 前K结果| / |相关文档总数|
```

### 计算示例

```python
def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """计算 Recall@K"""
    top_k = set(retrieved_ids[:k])
    relevant = set(relevant_ids)

    if not relevant:
        return 0.0

    return len(top_k & relevant) / len(relevant)

# 示例
retrieved = ["doc1", "doc3", "doc5", "doc2", "doc7"]
relevant = ["doc1", "doc2", "doc4"]

recall_at_3 = recall_at_k(retrieved, relevant, 3)  # 1/3 = 0.33（仅 doc1 在前 3）
recall_at_5 = recall_at_k(retrieved, relevant, 5)  # 2/3 = 0.67（doc1, doc2 在前 5）
```

### 适用场景

- 关注**召回完整性**：确保所有相关文档都被找到
- 知识库补全评估：检查是否有遗漏
- RAG 场景：确保 LLM 获得足够的上下文

### 局限

- 不考虑排序位置：第 1 位和第 K 位的贡献相同
- 不区分相关程度：所有相关文档权重相同

## MRR（Mean Reciprocal Rank）

### 定义

MRR 衡量第一个相关文档的排名倒数的平均值：

```
MRR = (1/|Q|) × Σ(1/rank_i)
```

其中 rank_i 是第 i 个查询的第一个相关文档的排名。

### 计算示例

```python
def mrr(queries_results: list[list[str]], queries_relevant: list[list[str]]) -> float:
    """计算 MRR"""
    reciprocal_ranks = []

    for retrieved, relevant in zip(queries_results, queries_relevant):
        relevant_set = set(relevant)
        for rank, doc_id in enumerate(retrieved, start=1):
            if doc_id in relevant_set:
                reciprocal_ranks.append(1 / rank)
                break
        else:
            reciprocal_ranks.append(0)

    return sum(reciprocal_ranks) / len(reciprocal_ranks)

# 示例
results = [
    ["doc3", "doc1", "doc5"],  # 查询1：doc1 在第 2 位 → 1/2
    ["doc2", "doc4", "doc6"],  # 查询2：doc2 在第 1 位 → 1/1
    ["doc7", "doc8", "doc9"],  # 查询3：无相关 → 0
]
relevant = [
    ["doc1", "doc2"],
    ["doc2", "doc5"],
    ["doc1"],
]

mrr_value = mrr(results, relevant)  # (0.5 + 1.0 + 0) / 3 = 0.5
```

### 适用场景

- 关注**第一个正确结果**的位置
- 搜索引擎评估：用户通常只看前几个结果
- 单答案场景：每个查询只有一个正确答案

### 局限

- 只考虑第一个相关文档，忽略后续结果
- 不适合需要多个相关文档的场景

## nDCG（Normalized Discounted Cumulative Gain）

### 定义

nDCG 考虑文档的相关性等级和排名位置，位置越靠前权重越大：

```
DCG@K = Σ_{i=1}^{K} (2^{rel_i} - 1) / log2(i + 1)
nDCG@K = DCG@K / IDCG@K
```

其中 IDCG 是理想排序下的 DCG。

### 计算示例

```python
import math

def ndcg_at_k(retrieved: list[str], relevance: dict[str, int], k: int) -> float:
    """计算 nDCG@K

    Args:
        retrieved: 检索结果 ID 列表
        relevance: {doc_id: relevance_level} 相关性等级（0-3）
        k: 截断位置
    """
    # DCG
    dcg = 0
    for i, doc_id in enumerate(retrieved[:k], start=1):
        rel = relevance.get(doc_id, 0)
        dcg += (2 ** rel - 1) / math.log2(i + 1)

    # IDCG（理想排序）
    ideal_rels = sorted(relevance.values(), reverse=True)[:k]
    idcg = 0
    for i, rel in enumerate(ideal_rels, start=1):
        idcg += (2 ** rel - 1) / math.log2(i + 1)

    return dcg / idcg if idcg > 0 else 0

# 示例
retrieved = ["doc1", "doc3", "doc5", "doc2"]
relevance = {"doc1": 3, "doc2": 2, "doc3": 1, "doc5": 0}

ndcg_4 = ndcg_at_k(retrieved, relevance, 4)
# doc1(3): (2^3-1)/log2(2) = 7/1 = 7
# doc3(1): (2^1-1)/log2(3) = 1/1.585 = 0.631
# doc5(0): 0
# doc2(2): (2^2-1)/log2(5) = 3/2.322 = 1.292
# DCG = 7 + 0.631 + 0 + 1.292 = 8.923
# IDCG = 7 + 3/log2(3) + 1/log2(4) = 7 + 1.893 + 0.5 = 9.393
# nDCG = 8.923/9.393 = 0.950
```

### 适用场景

- 关注**排序质量**和**位置权重**
- 多级相关性：文档有不同相关程度
- 推荐系统评估

### 局限

- 需要定义相关性等级（0-3），主观性强
- 计算比 Recall@K 和 MRR 复杂

## 指标选择指南

| 场景 | 推荐指标 | 理由 |
|------|---------|------|
| RAG 检索评估 | Recall@5 + MRR | 确保召回 + 排序质量 |
| 搜索引擎 | MRR + nDCG | 用户关注前几个结果 |
| 推荐系统 | nDCG | 多级相关性 + 位置权重 |
| 知识库补全 | Recall@10 | 确保不遗漏 |
| 快速评估 | Recall@1 | 最简单的指标 |

## Aureon 的检索指标

| 指标 | 值 | 目标 | 状态 |
|------|-----|------|------|
| Recall@5 | 92.4% | >=95% | 优化中 |
| MRR | 0.888 | >=0.85 | ✅ |
| Context Precision | 85.0% | >=70% | ✅ |

## 关键事实

1. **Recall@K 衡量召回完整性**，公式为 `|相关∩前K|/|相关总数|`，适合 RAG 场景确保 LLM 获得足够上下文
2. **MRR 衡量第一个相关文档的排名**，公式为 `1/rank`，适合搜索引擎和单答案场景
3. **nDCG 考虑相关性等级和位置权重**，位置越靠前权重越大（`1/log2(i+1)`），适合推荐系统
4. **RAG 场景推荐 Recall@5 + MRR 组合**，Recall@5 确保召回，MRR 确保排序质量
5. **Aureon 的 MRR 为 0.888（达标），Recall@5 为 92.4%（略低于 95% 目标）**，正在通过调参优化
