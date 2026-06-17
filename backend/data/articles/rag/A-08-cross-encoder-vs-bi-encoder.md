# Cross-Encoder vs Bi-Encoder：检索精度与速度的权衡

## 编码器架构概述

在信息检索和 RAG 系统中，编码器架构决定了检索的精度和速度。两种主流架构——Bi-Encoder（双编码器）和 Cross-Encoder（交叉编码器）——代表了精度与速度的两端权衡。

## Bi-Encoder（双编码器）

### 架构原理

Bi-Encoder 将查询和文档分别通过独立的编码器（或共享权重的同一编码器）映射为固定维度的向量，然后计算向量间的相似度：

```
Query → Encoder → q_vector ─┐
                              ├─ cosine_sim(q, d)
Document → Encoder → d_vector ─┘
```

### 核心特性

1. **独立编码**：查询和文档分别编码，互不影响
2. **预计算**：文档向量可以离线预计算并索引
3. **ANN 检索**：支持 HNSW、IVF 等近似最近邻算法，毫秒级检索
4. **无交互**：查询和文档的 Token 之间没有交叉注意力

### 实现示例

```python
from sentence_transformers import SentenceTransformer

# 使用 Bi-Encoder 编码
model = SentenceTransformer("BAAI/bge-large-zh-v1.5")

# 独立编码查询和文档
query_embedding = model.encode("什么是 RAG？")
doc_embedding = model.encode("RAG 是检索增强生成技术...")

# 计算相似度
from numpy import dot
from numpy.linalg import norm

similarity = dot(query_embedding, doc_embedding) / (
    norm(query_embedding) * norm(doc_embedding)
)
```

### Bi-Encoder 的优势与局限

**优势**：
- 检索速度极快（ANN 索引，<10ms）
- 文档向量可预计算，支持大规模文档库
- 存储开销低（每文档一个向量）

**局限**：
- 无 Token 级别交互，精度受限
- 难以捕捉查询和文档之间的细粒度语义关系
- 对同义词、多义词处理能力有限

## Cross-Encoder（交叉编码器）

### 架构原理

Cross-Encoder 将查询和文档拼接为单一输入，通过 Transformer 的全注意力机制计算相关性分数：

```
[CLS] Query Tokens [SEP] Document Tokens [SEP] → Transformer → Score
```

查询和文档的每个 Token 都可以相互注意，实现完全的交叉交互。

### 核心特性

1. **联合编码**：查询和文档作为一个整体输入
2. **全交互**：所有 Token 之间都有交叉注意力
3. **高精度**：能捕捉细粒度的语义匹配关系
4. **不可预计算**：每次查询需要与每个候选文档联合编码

### 实现示例

```python
from sentence_transformers import CrossEncoder

# 使用 Cross-Encoder 重排序
reranker = CrossEncoder("BAAI/bge-reranker-large")

# 对查询-文档对打分
pairs = [
    ("什么是 RAG？", "RAG 是检索增强生成技术..."),
    ("什么是 RAG？", "机器学习是人工智能的分支..."),
    ("什么是 RAG？", "RAG 通过检索外部知识减少幻觉..."),
]

scores = reranker.predict(pairs)
# 输出：[0.92, 0.15, 0.88]
```

### Cross-Encoder 的优势与局限

**优势**：
- 精度最高，能捕捉细粒度语义匹配
- 对同义词、否定、条件关系理解更好
- 适合作为 Rerank 精排层

**局限**：
- 速度慢（O(n) 复杂度，n 为候选文档数）
- 无法预计算文档表示
- 不适合大规模初筛

## 两阶段检索架构

实际系统中通常采用两阶段架构：Bi-Encoder 召回 + Cross-Encoder 精排

```
Query → Bi-Encoder 召回（Top-100）→ Cross-Encoder 精排（Top-10）→ 最终结果
```

```python
async def two_stage_retrieve(
    query: str,
    bi_encoder,
    cross_encoder,
    vectorstore,
    recall_k: int = 100,
    rerank_k: int = 10,
) -> list:
    # 阶段 1：Bi-Encoder 召回
    candidates = await vectorstore.asimilarity_search(query, k=recall_k)

    # 阶段 2：Cross-Encoder 精排
    pairs = [(query, doc.page_content) for doc in candidates]
    scores = cross_encoder.predict(pairs)

    # 按分数排序
    scored_docs = list(zip(candidates, scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    return [doc for doc, _ in scored_docs[:rerank_k]]
```

## 延迟-精度权衡分析

### 不同候选数的 Rerank 延迟

| 候选数 | Cross-Encoder 延迟 | 精度提升 |
|--------|-------------------|---------|
| 5 | ~50ms | +3-5% |
| 10 | ~100ms | +5-8% |
| 20 | ~200ms | +8-12% |
| 50 | ~500ms | +10-15% |
| 100 | ~1s | +12-18% |

### 自适应 Rerank

不是所有查询都需要 Rerank。自适应策略根据检索置信度决定是否 Rerank：

```python
async def adaptive_rerank(
    query: str,
    candidates: list,
    cross_encoder,
    threshold: float = 0.5,
) -> list:
    """自适应 Rerank：高置信度时跳过 Rerank"""
    if not candidates:
        return candidates

    # 计算 Top-1 和 Top-2 的分差比例
    top1_score = candidates[0].metadata.get("score", 0)
    top2_score = candidates[1].metadata.get("score", 0) if len(candidates) > 1 else 0

    if top1_score > 0:
        gap_ratio = (top1_score - top2_score) / top1_score
    else:
        gap_ratio = 0

    # 分差足够大，Top-1 置信度高，跳过 Rerank
    if gap_ratio > threshold:
        return candidates

    # 分差小，需要 Rerank 区分
    pairs = [(query, doc.page_content) for doc in candidates]
    scores = cross_encoder.predict(pairs)

    scored_docs = list(zip(candidates, scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    return [doc for doc, _ in scored_docs]
```

## ColBERT 作为中间方案

ColBERT 的 Late Interaction 机制提供了 Bi-Encoder 和 Cross-Encoder 之间的折中：

| 维度 | Bi-Encoder | ColBERT | Cross-Encoder |
|------|-----------|---------|---------------|
| 交互深度 | 无 | Token-MaxSim | 全注意力 |
| 精度 | 中 | 高 | 最高 |
| 速度 | 最快 | 中 | 最慢 |
| 存储 | 低 | 高 | 无 |
| 可预计算 | 完全 | 部分 | 不可 |

## Reranker API 对比

### 主流 Rerank API

| 服务 | 模型 | 延迟 | 成本 | 中文支持 |
|------|------|------|------|---------|
| Cohere Rerank | rerank-v3 | ~100ms | $0.002/1K tokens | 优秀 |
| DashScope | gte-rerank | ~150ms | ¥0.001/1K tokens | 优秀 |
| Jina Reranker | jina-reranker-v2 | ~80ms | 免费额度 | 良好 |
| SiliconFlow | bge-reranker | ~120ms | ¥0.0005/1K tokens | 优秀 |

### 批量 Rerank 优化

```python
import asyncio

async def batch_rerank(
    query: str,
    candidates: list,
    reranker_api,
    batch_size: int = 20,
) -> list:
    """批量 Rerank：分批并发调用 API"""
    all_scored = []

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        pairs = [(query, doc.page_content) for doc in batch]
        scores = await reranker_api.arerank(pairs)
        all_scored.extend(zip(batch, scores))

    all_scored.sort(key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in all_scored]
```

## 关键事实

1. **Bi-Encoder 独立编码查询和文档**，支持预计算和 ANN 检索（<10ms），但无 Token 级别交互导致精度受限
2. **Cross-Encoder 将查询和文档拼接为单一输入**，全注意力交互实现最高精度，但 O(n) 复杂度使其不适合大规模初筛
3. **两阶段架构（Bi-Encoder 召回 + Cross-Encoder 精排）**是工业界标准做法，兼顾速度和精度
4. **自适应 Rerank 通过 Top-1/Top-2 分差比例判断是否需要 Rerank**，Aureon 中阈值为 0.5，约 30% 的查询可以跳过 Rerank
5. **ColBERT 的 Late Interaction 机制**提供了 Bi-Encoder 和 Cross-Encoder 之间的折中，精度接近 Cross-Encoder，速度接近 Bi-Encoder
