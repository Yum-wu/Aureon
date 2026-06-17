# Late Interaction 模型：ColBERT 与其变体

## 从 Bi-Encoder 到 Late Interaction

在检索模型的发展中，Bi-Encoder（双编码器）和 Cross-Encoder（交叉编码器）代表了两种极端：

- **Bi-Encoder**：查询和文档独立编码，速度快但精度有限
- **Cross-Encoder**：查询和文档联合编码，精度高但速度慢

Late Interaction（延迟交互）模型试图在两者之间找到平衡点，**保留 Token 级别的细粒度交互，同时支持预计算和高效检索**。

## ColBERT 模型

### 核心思想

ColBERT（Contextual Late Interaction over BERT）由 Khattab 和 Zaharia 于 2020 年提出。其核心创新是：

1. **保留 Token 级别嵌入**：不像 Bi-Encoder 那样将整个查询/文档压缩为单一向量，而是保留每个 Token 的嵌入
2. **延迟交互**：在检索时才计算查询和文档 Token 之间的交互，而非在编码阶段
3. **MaxSim 操作**：用查询每个 Token 与文档所有 Token 的最大相似度之和作为相关性分数

### MaxSim 机制

```
ColBERT_score(Q, D) = Σ_{q∈Q} max_{d∈D} sim(q, d)
```

对于查询 Q 中的每个 Token q，找到文档 D 中与之最相似的 Token d，取最大相似度，然后对所有查询 Token 求和。

```python
import torch

def colbert_maxsim(query_embeddings: torch.Tensor, doc_embeddings: torch.Tensor) -> float:
    """计算 ColBERT MaxSim 分数

    Args:
        query_embeddings: [query_len, dim] 查询 Token 嵌入
        doc_embeddings: [doc_len, dim] 文档 Token 嵌入

    Returns:
        MaxSim 分数
    """
    # 计算所有 query-doc token 对的相似度
    # similarity_matrix: [query_len, doc_len]
    similarity_matrix = query_embeddings @ doc_embeddings.T

    # 对每个 query token，取与所有 doc token 的最大相似度
    max_similarities = similarity_matrix.max(dim=1).values  # [query_len]

    # 求和得到最终分数
    return max_similarities.sum().item()
```

### ColBERT 的检索流程

```
1. 离线阶段：将文档编码为 Token 级别嵌入，存入向量库
2. 在线阶段：
   a. 将查询编码为 Token 级别嵌入
   b. 用查询嵌入检索候选文档（ANN 初筛）
   c. 对候选文档计算 MaxSim 精排
```

### ColBERT 的存储挑战

ColBERT 的主要挑战是存储开销。一个 512 Token 的文档，使用 128 维嵌入，需要存储 512 × 128 = 65,536 个浮点数，远大于 Bi-Encoder 的单一 128 维向量。

```python
# 存储开销对比（假设 128 维嵌入）
# Bi-Encoder: 每个文档 128 个浮点数 = 512 bytes
# ColBERT: 每个文档 512 * 128 = 65,536 个浮点数 = 262,144 bytes
# 比率: 512x

# 压缩策略
# 1. 降维：128 → 64 维，存储减半
# 2. 量化：FP32 → INT8，存储减 4x
# 3. 剪枝：移除停用词 Token 嵌入
```

## ColBERTv2

ColBERTv2 在原始 ColBERT 基础上引入了残差压缩：

### 残差压缩

```python
def residual_compression(token_embeddings: torch.Tensor, n_bits: int = 8):
    """ColBERTv2 残差压缩

    将每个 Token 嵌入表示为质心 ID + 残差量化码
    """
    # 1. K-Means 聚类找到质心
    centroids = kmeans(token_embeddings, n_clusters=256)

    # 2. 每个 Token 找最近质心
    assignments = assign_to_centroids(token_embeddings, centroids)

    # 3. 计算残差
    residuals = token_embeddings - centroids[assignments]

    # 4. 残差量化
    quantized_residuals = quantize(residuals, n_bits=n_bits)

    return assignments, quantized_residuals, centroids
```

ColBERTv2 的压缩效果：
- 存储压缩约 10x（相比原始 ColBERT）
- 检索精度损失 < 2%
- 支持数十亿文档规模

## BGE-M3 的 ColBERT 模式

BGE-M3 是 BAAI 发布的多功能嵌入模型，同时支持 dense、sparse 和 ColBERT 三种模式：

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

# 生成 ColBERT 向量
output = model.encode(
    ["什么是 RAG？"],
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=True
)

# ColBERT 向量：[seq_len, dim] 的 Token 级别嵌入
colbert_vectors = output["colbert_vecs"][0]  # shape: [seq_len, 1024]
```

### 在 Qdrant 中使用 ColBERT

```python
# Qdrant 支持多向量存储，可用于 ColBERT
from qdrant_client.models import VectorParams

client.create_collection(
    collection_name="colbert_docs",
    vectors_config={
        "colbert": VectorParams(
            size=1024,
            distance="Cosine",
            multivector_config=MultiVectorConfig(
                comparator="max_sim"  # 使用 MaxSim 相似度
            )
        )
    }
)
```

## PLAID：高效 ColBERT 检索

PLAID（Performance-oriented Late Interaction Driver）是 ColBERT 的高效检索引擎：

### 核心优化

1. **质心预筛选**：用查询 Token 匹配质心，快速过滤不相关文档
2. **两阶段检索**：先粗筛候选文档，再精确计算 MaxSim
3. **GPU 加速**：MaxSim 计算在 GPU 上并行执行

```python
# PLAID 检索流程
async def plaid_retrieve(query_tokens, index, k=10):
    # 阶段 1：质心匹配，获取候选文档
    candidate_ids = index.get_candidates_by_centroids(query_tokens, n_centroids=5)

    # 阶段 2：精确 MaxSim 排序
    scores = []
    for doc_id in candidate_ids:
        doc_tokens = index.get_doc_tokens(doc_id)
        score = colbert_maxsim(query_tokens, doc_tokens)
        scores.append((doc_id, score))

    # 返回 Top-K
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:k]
```

## ColBERT vs Bi-Encoder vs Cross-Encoder

| 维度 | Bi-Encoder | ColBERT | Cross-Encoder |
|------|-----------|---------|---------------|
| **交互粒度** | 无交互 | Token 级别 | 全交互 |
| **精度** | 中 | 高 | 最高 |
| **检索速度** | 快（ANN） | 中（需 MaxSim） | 慢（需逐对计算） |
| **存储开销** | 低 | 高 | 无（无预计算） |
| **可预计算** | 是 | 部分（文档 Token 嵌入） | 否 |
| **适用阶段** | 召回 | 精排 | 精排/Rerank |
| **延迟** | <10ms | 10-50ms | 100-500ms |

## 实践建议

### 何时使用 ColBERT

1. **需要 Token 级别匹配**：如法律文档、技术规范等精确匹配场景
2. **作为 Rerank 层**：在 Bi-Encoder 召回后用 ColBERT 精排
3. **多语言场景**：ColBERT 对多语言查询表现优异

### 何时不用 ColBERT

1. **大规模文档库**：存储开销可能不可接受（>1M 文档）
2. **延迟敏感场景**：MaxSim 计算比 Bi-Encoder 慢 5-10x
3. **简单查询**：关键词匹配即可的场景，ColBERT 收益有限

## 关键事实

1. **ColBERT 由 Khattab 和 Zaharia 于 2020 年提出**，核心创新是 MaxSim 机制：对查询每个 Token 取文档中最大相似度，然后求和
2. **ColBERT 保留 Token 级别嵌入而非压缩为单一向量**，存储开销是 Bi-Encoder 的约 512 倍，但精度显著提升
3. **ColBERTv2 引入残差压缩**，将存储压缩约 10 倍，精度损失 < 2%，支持数十亿文档规模
4. **BGE-M3 同时输出 dense + sparse + ColBERT 三种向量**，一次推理获得三种检索能力，在 Qdrant 中可通过 MultiVector 配置存储 ColBERT 向量
5. **ColBERT 适合作为 Rerank 层使用**，在 Bi-Encoder 召回后精排，延迟约 10-50ms，比 Cross-Encoder 快 5-10 倍
