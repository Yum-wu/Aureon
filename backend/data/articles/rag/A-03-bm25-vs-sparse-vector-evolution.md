# BM25 vs 稀疏向量：RAG 关键词检索演进

## 关键词检索的演进历程

关键词检索是信息检索的基础能力。从早期的 TF-IDF 到 BM25，再到基于神经网络学习的稀疏向量，关键词检索经历了从统计方法到学习方法的重要演进。理解这一演进对于构建高质量的 RAG 系统至关重要。

## BM25：经典关键词检索

### 算法原理

BM25（Best Matching 25）由 Robertson 和 Zaragoza 于 2009 年正式提出，是 Okapi BM25 的改进版本。其核心公式：

```
score(D, Q) = Σ IDF(qi) · f(qi, D) · (k1 + 1) / (f(qi, D) + k1 · (1 - b + b · |D| / avgdl))
```

其中：
- `f(qi, D)`：词 qi 在文档 D 中的词频
- `|D|`：文档长度
- `avgdl`：平均文档长度
- `k1`：词频饱和参数，通常取 1.2-2.0
- `b`：文档长度归一化参数，通常取 0.75
- `IDF(qi)`：逆文档频率，`log((N - n(qi) + 0.5) / (n(qi) + 0.5) + 1)`

### BM25 的优势

1. **无需训练**：纯统计方法，开箱即用
2. **计算高效**：倒排索引 + 词频统计，毫秒级响应
3. **可解释性强**：每个词的贡献可以精确计算
4. **精确匹配**：对关键词精确匹配场景效果优异

### BM25 的局限

1. **词汇鸿沟**：无法处理同义词、近义词（"手机" vs "移动电话"）
2. **分词依赖**：中文需要 jieba 等分词器，分词质量直接影响检索效果
3. **无语义理解**：无法理解词序和上下文
4. **固定权重**：IDF 基于语料统计，无法针对特定查询调整

## 稀疏向量：学习型关键词检索

### 核心思想

稀疏向量（Sparse Vector）将文本映射到高维稀疏空间，每个维度对应一个词项（token），权重由神经网络学习得到。与 BM25 的统计权重不同，稀疏向量的权重考虑了上下文语义。

### SPLADE 模型

SPLADE（SParse Lexical AnD Expansion）是代表性的稀疏向量模型：

```python
# SPLADE 的核心思想
# 1. 通过 Transformer 编码器获取 token 表示
# 2. 使用 max-pooling 聚合 token 级别的 logit
# 3. 应用 ReLU + 对数变换得到稀疏权重
# 4. 输出高维稀疏向量（vocab_size 维，大部分为 0）

# SPLADE 权重计算
# w_j = max_j(ReLU(log(1 + exp(transformer_output_j))))
```

SPLADE 的关键特性：
- **查询扩展**：自动为查询添加语义相关词项
- **上下文感知**：同一词在不同上下文中权重不同
- **稀疏性**：大部分维度为 0，存储和计算高效

### BGE-M3 稀疏向量

BGE-M3 模型同时输出 dense、sparse 和 ColBERT 三种向量。其稀疏向量部分：

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

# BGE-M3 可以同时生成 dense + sparse 向量
output = model.encode(
    ["什么是 RAG？"],
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=False
)

# sparse 向量：词项 ID → 权重的字典
sparse_vector = output["lexical_weights"][0]
# 例如：{102: 0.85, 2048: 0.72, 356: 0.63, ...}
```

## Qdrant 原生稀疏向量

### 架构设计

Qdrant 从 1.7.0 版本开始原生支持稀疏向量，无需外部 BM25 服务：

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    SparseVector, SparseIndexParams, PointStruct
)

client = QdrantClient("localhost", port=6333)

# 创建支持稀疏向量的集合
client.create_collection(
    collection_name="hybrid_docs",
    vectors_config={
        "dense": {
            "size": 1024,
            "distance": "Cosine",
            "hnsw_config": {"m": 32, "ef_construct": 200}
        }
    },
    sparse_vectors_config={
        "sparse": {
            "index": SparseIndexParams(
                on_disk=False,
                full_scan_threshold=10000
            )
        }
    }
)

# 插入文档（dense + sparse 联合向量）
point = PointStruct(
    id=1,
    vector={
        "dense": dense_embedding,  # [0.1, 0.2, ..., 0.9] 1024维
        "sparse": SparseVector(
            indices=[102, 2048, 356, 789],  # 词项 ID
            values=[0.85, 0.72, 0.63, 0.41]  # 对应权重
        )
    },
    payload={"text": "文档内容", "source": "knowledge_base"}
)
client.upsert(collection_name="hybrid_docs", points=[point])
```

### Hybrid Search（混合检索）

Qdrant 原生支持 dense + sparse 的混合检索，使用 RRF 融合：

```python
from qdrant_client.models import SearchRequest, FusionQuery, Query

# Hybrid Search：dense + sparse 联合检索
results = client.query_points(
    collection_name="hybrid_docs",
    prefetch=[
        # Dense 检索
        Query(
            vector_name="dense",
            vector=dense_query_embedding,
            limit=20,
        ),
        # Sparse 检索
        Query(
            vector_name="sparse",
            vector=SparseVector(
                indices=sparse_query_indices,
                values=sparse_query_values
            ),
            limit=20,
        )
    ],
    query=FusionQuery(fusion="rrf"),  # RRF 融合
    limit=10
)
```

## BM25 vs 稀疏向量对比

| 维度 | BM25 | 稀疏向量（SPLADE/BGE-M3） |
|------|------|--------------------------|
| **语义理解** | 无 | 有（上下文感知权重） |
| **查询扩展** | 无 | 自动扩展相关词项 |
| **分词依赖** | 强依赖（中文需 jieba） | 弱（子词分词器） |
| **训练需求** | 无 | 需预训练模型 |
| **推理延迟** | <5ms | 10-50ms（需模型推理） |
| **存储开销** | 倒排索引（小） | 稀疏向量（中等） |
| **精确匹配** | 优秀 | 良好 |
| **同义词处理** | 不支持 | 支持 |
| **部署复杂度** | 低（Elasticsearch） | 中（需 GPU/CPU 推理） |

## 在 Aureon 中的实践

Aureon 采用 Qdrant 原生稀疏向量替代传统 BM25：

1. **统一架构**：不再需要 Elasticsearch + Qdrant 双系统，Qdrant 一个系统同时支持 dense + sparse
2. **BGE-M3 联合编码**：一次推理同时生成 dense 和 sparse 向量，无额外推理开销
3. **查询路由优化**：简单查询走纯 sparse 检索（<10ms），复杂查询走 hybrid 检索
4. **RRF 融合**：Qdrant 原生 RRF 融合 dense + sparse 结果，无需应用层处理

### 性能对比（Aureon 实测）

| 指标 | BM25 (jieba) | Qdrant Sparse (BGE-M3) |
|------|-------------|------------------------|
| 简单查询延迟 | 8ms | 6ms |
| Recall@5 | 78% | 88% |
| 同义词召回率 | 45% | 82% |
| 运维复杂度 | 高（双系统） | 低（单系统） |

## 关键事实

1. **BM25 是基于词频统计的经典关键词检索算法**，通过 IDF 和词频饱和函数计算相关性，对精确匹配场景效果优异但无法处理同义词
2. **稀疏向量（如 SPLADE、BGE-M3）通过神经网络学习词项权重**，实现上下文感知和自动查询扩展，弥补了 BM25 的语义鸿沟
3. **Qdrant 从 1.7.0 版本原生支持稀疏向量**，可以在同一集合中存储 dense + sparse 向量，并通过 RRF 融合进行混合检索
4. **BGE-M3 一次推理同时输出 dense + sparse + ColBERT 三种向量**，在 Aureon 中替代了 jieba BM25，Recall@5 从 78% 提升到 88%
5. **稀疏向量的推理延迟（10-50ms）高于 BM25（<5ms）**，但通过查询路由让简单查询走纯 sparse 路径，可以将延迟控制在 10ms 以内
