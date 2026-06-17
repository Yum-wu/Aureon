# BGE-M3 架构解析：dense + sparse + colbert 三合一

## BGE-M3 概述

BGE-M3 由 BAAI（北京智源人工智能研究院）发布，是首个同时支持 dense、sparse 和 ColBERT 三种检索模式的统一嵌入模型。M3 代表 **M**ulti-lingual（多语言）、**M**ulti-function（多功能）、**M**ulti-granularity（多粒度）。

### 核心创新

1. **三合一输出**：一次推理同时生成 dense、sparse、ColBERT 三种向量
2. **多语言支持**：100+ 语言，跨语言检索效果优异
3. **长文本支持**：最大 8192 Token 输入
4. **混合检索**：三种向量可以独立或组合使用

## 架构详解

### 整体架构

```
输入文本 → XLM-RoBERTa Encoder → Token 级别表示
                                        ├── Dense: [CLS] + Mean Pooling → 1024 维向量
                                        ├── Sparse: Linear + ReLU + Log → 词项权重
                                        └── ColBERT: Linear Projection → Token 级别 1024 维向量
```

### Dense 向量生成

```python
# Dense 向量：[CLS] Token + Mean Pooling
# 与标准 Bi-Encoder 相同的流程

def generate_dense(token_outputs, attention_mask):
    """生成 Dense 向量"""
    # 方法 1：[CLS] Token
    cls_embedding = token_outputs[:, 0, :]

    # 方法 2：Mean Pooling（推荐）
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_outputs.size()).float()
    mean_pooled = torch.sum(token_outputs * input_mask_expanded, 1) / torch.clamp(
        input_mask_expanded.sum(1), min=1e-9
    )

    # 归一化
    dense_vector = F.normalize(mean_pooled, p=2, dim=1)
    return dense_vector  # [batch, 1024]
```

### Sparse 向量生成

```python
# Sparse 向量：词项级别的权重
# 通过 Linear + ReLU + Log 激活得到稀疏权重

def generate_sparse(token_outputs, vocabulary_size: int = 250002):
    """生成 Sparse 向量"""
    # Linear 投影到词表空间
    logits = linear_layer(token_outputs)  # [batch, seq_len, vocab_size]

    # ReLU + Log(1 + exp(x)) 激活
    weights = torch.log1p(torch.relu(logits))

    # Max Pooling：每个词项取所有位置的最大权重
    sparse_weights = weights.max(dim=1).values  # [batch, vocab_size]

    # 只保留非零权重
    # sparse_weights 是高维稀疏向量，大部分为 0
    return sparse_weights
```

### ColBERT 向量生成

```python
# ColBERT 向量：Token 级别的嵌入
# 通过 Linear Projection 降维

def generate_colbert(token_outputs, colbert_dim: int = 1024):
    """生成 ColBERT 向量"""
    # Linear Projection
    colbert_vectors = colbert_linear(token_outputs)  # [batch, seq_len, 1024]

    # L2 归一化
    colbert_vectors = F.normalize(colbert_vectors, p=2, dim=-1)

    return colbert_vectors  # [batch, seq_len, 1024]
```

## 训练方法

### 多目标训练

BGE-M3 同时优化三种检索模式的损失：

```python
def bge_m3_loss(
    query_outputs,
    doc_outputs,
    labels,
    dense_weight: float = 1.0,
    sparse_weight: float = 0.2,
    colbert_weight: float = 0.5,
):
    """BGE-M3 多目标损失"""
    # Dense 损失（InfoNCE）
    dense_loss = info_nce_loss(query_outputs["dense"], doc_outputs["dense"], labels)

    # Sparse 损失
    sparse_loss = sparse_contrastive_loss(
        query_outputs["sparse"], doc_outputs["sparse"], labels
    )

    # ColBERT 损失（MaxSim + InfoNCE）
    colbert_scores = compute_maxsim_scores(
        query_outputs["colbert"], doc_outputs["colbert"]
    )
    colbert_loss = F.cross_entropy(colbert_scores / 0.05, labels)

    # 加权总损失
    total_loss = (
        dense_weight * dense_loss
        + sparse_weight * sparse_loss
        + colbert_weight * colbert_loss
    )

    return total_loss
```

### 训练数据

BGE-M3 的训练数据包括：
- **多语言平行语料**：用于跨语言对齐
- **查询-文档对**：来自搜索日志和人工标注
- **合成数据**：LLM 生成的查询-文档对

## 使用方法

### 基础用法

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

# 一次推理，三种向量
output = model.encode(
    ["什么是检索增强生成？", "RAG 是一种结合检索和生成的技术"],
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=True,
    max_length=8192,  # 支持长文本
)

# Dense 向量
dense_vectors = output["dense_vecs"]  # [2, 1024]

# Sparse 向量（词项权重字典）
sparse_vectors = output["lexical_weights"]  # [{token_id: weight, ...}, ...]

# ColBERT 向量
colbert_vectors = output["colbert_vecs"]  # [2, seq_len, 1024]
```

### 在 Qdrant 中使用

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, SparseVectorParams, SparseIndexParams,
    PointStruct, SparseVector, MultiVectorConfig,
)

client = QdrantClient("localhost", port=6333)

# 创建支持三种向量的集合
client.create_collection(
    collection_name="bge_m3_docs",
    vectors_config={
        "dense": VectorParams(size=1024, distance="Cosine"),
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams(
            index=SparseIndexParams(on_disk=False)
        ),
    },
)

# 插入文档
def encode_and_upsert(text: str, doc_id: int):
    output = model.encode([text], return_dense=True, return_sparse=True)

    point = PointStruct(
        id=doc_id,
        vector={
            "dense": output["dense_vecs"][0].tolist(),
            "sparse": SparseVector(
                indices=list(output["lexical_weights"][0].keys()),
                values=list(output["lexical_weights"][0].values()),
            ),
        },
        payload={"text": text},
    )
    client.upsert(collection_name="bge_m3_docs", points=[point])

# Hybrid Search
results = client.query_points(
    collection_name="bge_m3_docs",
    prefetch=[
        Query(vector_name="dense", vector=dense_query, limit=20),
        Query(vector_name="sparse", vector=sparse_query, limit=20),
    ],
    query=FusionQuery(fusion="rrf"),
    limit=10,
)
```

## 性能对比

### 单模式 vs 混合模式

| 模式 | Recall@5 | MRR | 延迟 |
|------|----------|-----|------|
| 仅 Dense | 89.5% | 0.862 | 45ms |
| 仅 Sparse | 82.3% | 0.780 | 8ms |
| Dense + Sparse (RRF) | 92.4% | 0.888 | 50ms |
| Dense + Sparse + ColBERT | 93.1% | 0.895 | 120ms |

### 与其他模型对比

| 模型 | 中文 Recall@5 | 多语言 Recall@5 | 推理速度 |
|------|-------------|----------------|---------|
| bge-large-zh-v1.5 | 92.4% | N/A | 15ms |
| bge-m3 (dense only) | 91.8% | 88.5% | 22ms |
| bge-m3 (hybrid) | 93.1% | 90.2% | 50ms |
| text-embedding-3-large | 87.5% | 86.8% | 250ms |

## 在 Aureon 中的应用

Aureon 使用 BGE-M3 作为核心 Embedding 模型：

1. **一次推理三种向量**：dense 用于语义检索，sparse 替代 BM25 关键词检索
2. **Qdrant Hybrid Search**：dense + sparse 通过 RRF 融合
3. **查询路由**：简单查询走纯 sparse（<10ms），复杂查询走 hybrid
4. **Fallback Chain**：本地 BGE-M3 → DashScope → SiliconFlow → Zhipu

## 关键事实

1. **BGE-M3 是首个同时支持 dense + sparse + ColBERT 三种检索模式的统一模型**，M3 代表多语言、多功能、多粒度
2. **BGE-M3 基于 XLM-RoBERTa**，支持 100+ 语言和 8192 Token 长文本输入
3. **Sparse 向量通过 Linear + ReLU + Log 激活生成词项权重**，替代传统 BM25，支持查询扩展和上下文感知
4. **Hybrid 模式（Dense + Sparse RRF 融合）的 Recall@5 为 92.4%**，比仅 Dense 高 2.9%，比仅 Sparse 高 10.1%
5. **BGE-M3 的推理延迟约 22ms（单模式）和 50ms（hybrid）**，比 OpenAI API 快 5-10 倍，是本地部署的首选
