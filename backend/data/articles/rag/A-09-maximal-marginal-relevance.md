# MMR 多样性检索：平衡相关性与新颖性

## 多样性检索的必要性

传统检索系统按相关性排序返回结果，但这可能导致**信息冗余**——排名靠前的文档内容高度相似，用户只能看到同一信息的不同表述。Maximal Marginal Relevance（MMR）由 Carbonell 和 Goldstein 于 1998 年提出，旨在解决这一问题，在相关性和多样性之间取得平衡。

## MMR 算法原理

### 核心公式

MMR 采用贪心策略，每次选择使以下目标函数最大化的文档：

```
MMR(d) = λ · Sim(d, q) - (1 - λ) · max_{d'∈S} Sim(d, d')
```

其中：
- `Sim(d, q)`：文档 d 与查询 q 的相关性
- `Sim(d, d')`：文档 d 与已选文档 d' 的相似度
- `S`：已选文档集合
- `λ`：相关性-多样性权衡参数，取值 [0, 1]

### 参数 λ 的影响

| λ 值 | 倾向 | 效果 |
|------|------|------|
| 1.0 | 纯相关性 | 退化为标准排序 |
| 0.7-0.8 | 偏相关性 | 适度去重，保留最相关结果 |
| 0.5 | 平衡 | 相关性与多样性等权 |
| 0.3 | 偏多样性 | 强调新颖性，可能牺牲相关性 |
| 0.0 | 纯多样性 | 完全忽略相关性 |

## MMR 实现

### 基础实现

```python
import numpy as np

def maximal_marginal_relevance(
    query_embedding: np.ndarray,
    doc_embeddings: np.ndarray,
    lambda_param: float = 0.7,
    k: int = 10,
) -> list[int]:
    """MMR 多样性检索

    Args:
        query_embedding: 查询嵌入向量 [dim]
        doc_embeddings: 文档嵌入矩阵 [n_docs, dim]
        lambda_param: 相关性-多样性权衡参数
        k: 返回文档数

    Returns:
        选中的文档索引列表
    """
    n_docs = doc_embeddings.shape[0]
    selected_indices = []
    remaining_indices = list(range(n_docs))

    # 计算所有文档与查询的相似度
    query_similarities = cosine_similarity_batch(query_embedding, doc_embeddings)

    for _ in range(min(k, n_docs)):
        best_idx = None
        best_score = -float("inf")

        for idx in remaining_indices:
            # 相关性分数
            relevance = query_similarities[idx]

            # 与已选文档的最大相似度
            if selected_indices:
                selected_embeddings = doc_embeddings[selected_indices]
                doc_similarities = cosine_similarity_batch(
                    doc_embeddings[idx], selected_embeddings
                )
                diversity_penalty = max(doc_similarities)
            else:
                diversity_penalty = 0

            # MMR 分数
            mmr_score = lambda_param * relevance - (1 - lambda_param) * diversity_penalty

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)

    return selected_indices


def cosine_similarity_batch(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """批量余弦相似度"""
    if b.ndim == 1:
        b = b.reshape(1, -1)
    return (b @ a) / (np.linalg.norm(b, axis=1) * np.linalg.norm(a) + 1e-8)
```

### 基于 LangChain 的 MMR 检索

```python
from langchain_core.vectorstores import VectorStore

async def mmr_retrieve(
    query: str,
    vectorstore: VectorStore,
    embedder,
    lambda_param: float = 0.7,
    fetch_k: int = 50,
    k: int = 10,
) -> list:
    """基于 MMR 的多样性检索"""
    # 先获取较多候选
    candidates = await vectorstore.asimilarity_search(query, k=fetch_k)

    # 计算嵌入
    query_embedding = await embedder.aembed_query(query)
    doc_embeddings = np.array([
        await embedder.aembed_query(doc.page_content)
        for doc in candidates
    ])

    # MMR 选择
    selected_indices = maximal_marginal_relevance(
        np.array(query_embedding),
        doc_embeddings,
        lambda_param=lambda_param,
        k=k,
    )

    return [candidates[i] for i in selected_indices]
```

## MMR 的优化变体

### 分组 MMR

先按主题分组，再在每组内应用 MMR：

```python
async def grouped_mmr(
    query: str,
    candidates: list,
    embedder,
    lambda_param: float = 0.7,
    n_groups: int = 3,
    k_per_group: int = 3,
) -> list:
    """分组 MMR：确保每个主题都有代表"""
    # 按来源/主题分组
    groups = group_by_topic(candidates, n_groups=n_groups)

    results = []
    for group in groups:
        group_embeddings = np.array([
            await embedder.aembed_query(doc.page_content)
            for doc in group
        ])
        query_embedding = await embedder.aembed_query(query)

        selected = maximal_marginal_relevance(
            np.array(query_embedding),
            group_embeddings,
            lambda_param=lambda_param,
            k=k_per_group,
        )
        results.extend([group[i] for i in selected])

    return results
```

### 自适应 λ

根据查询类型动态调整 λ 值：

```python
def adaptive_lambda(query: str, query_type: str) -> float:
    """根据查询类型自适应调整 λ"""
    if query_type == "factual":
        # 事实型查询：偏相关性，用户需要精确答案
        return 0.8
    elif query_type == "exploratory":
        # 探索型查询：偏多样性，用户需要多角度信息
        return 0.5
    elif query_type == "comparison":
        # 对比型查询：平衡，需要不同观点
        return 0.6
    else:
        return 0.7
```

## MMR vs 其他多样性方法

### 方法对比

| 方法 | 原理 | 计算复杂度 | 效果 |
|------|------|-----------|------|
| MMR | 贪心选择，平衡相关性与新颖性 | O(k·n) | 良好 |
| DPP | 行列式点过程，概率采样 | O(n³) | 最优但慢 |
| k-means 聚类 | 先聚类再从每簇选代表 | O(n·k·iter) | 良好 |
| 阈值去重 | 相似度超过阈值则去重 | O(n²) | 简单但粗糙 |

### DPP（行列式点过程）

DPP 是理论上最优的多样性选择方法：

```python
def dpp_selection(
    query_embedding: np.ndarray,
    doc_embeddings: np.ndarray,
    quality_scores: np.ndarray,
    k: int = 10,
    epsilon: float = 1e-10,
) -> list[int]:
    """DPP 多样性选择

    通过贪心近似 DPP，选择质量高且多样的子集
    """
    n = doc_embeddings.shape[0]
    selected = []
    remaining = list(range(n))

    # 构建核矩阵
    B = doc_embeddings * quality_scores[:, np.newaxis]

    for _ in range(min(k, n)):
        best_idx = None
        best_det = -float("inf")

        for idx in remaining:
            # 计算加入该文档后的行列式增量
            if not selected:
                det = quality_scores[idx] ** 2 + epsilon
            else:
                # 贪心近似
                c = B[selected] @ B[idx]
                det = quality_scores[idx] ** 2 - c @ c + epsilon

            if det > best_det:
                best_det = det
                best_idx = idx

        selected.append(best_idx)
        remaining.remove(best_idx)

    return selected
```

## MMR 在 RAG 中的实践

### 何时使用 MMR

1. **探索型查询**：用户需要多角度信息（如"RAG 的优缺点"）
2. **对比型查询**：需要不同观点或方案（如"BM25 vs 稀疏向量"）
3. **信息冗余严重**：检索结果中大量重复内容

### 何时不使用 MMR

1. **事实型查询**：用户需要精确答案（如"RAG 的全称是什么"）
2. **延迟敏感**：MMR 需要额外计算相似度矩阵
3. **候选数少**：候选文档本身就不多，多样性不是问题

### 与 Rerank 的配合

```python
async def rerank_then_mmr(
    query: str,
    candidates: list,
    reranker,
    embedder,
    rerank_k: int = 20,
    mmr_k: int = 5,
    lambda_param: float = 0.7,
) -> list:
    """先 Rerank 精排，再 MMR 去重"""
    # Rerank 精排
    reranked = await reranker.arerank(query, candidates, top_k=rerank_k)

    # MMR 去重
    query_embedding = await embedder.aembed_query(query)
    doc_embeddings = np.array([
        await embedder.aembed_query(doc.page_content)
        for doc in reranked
    ])

    selected = maximal_marginal_relevance(
        np.array(query_embedding),
        doc_embeddings,
        lambda_param=lambda_param,
        k=mmr_k,
    )

    return [reranked[i] for i in selected]
```

## 关键事实

1. **MMR 由 Carbonell 和 Goldstein 于 1998 年提出**，公式为 `MMR(d) = λ·Sim(d,q) - (1-λ)·max Sim(d,d')`，在相关性和多样性之间取得平衡
2. **λ 参数控制相关性-多样性权衡**，λ=1 退化为纯相关性排序，λ=0 完全忽略相关性只追求多样性，推荐值 0.7-0.8
3. **MMR 的计算复杂度为 O(k·n)**，比 DPP 的 O(n³) 更高效，适合在线检索场景
4. **MMR 适用于探索型和对比型查询**，对于事实型查询（需要精确答案）不建议使用
5. **实践中推荐先 Rerank 精排再 MMR 去重**，确保相关性优先，多样性作为补充
