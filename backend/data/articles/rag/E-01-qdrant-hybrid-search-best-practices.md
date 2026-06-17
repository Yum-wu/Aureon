# Qdrant Hybrid Search 最佳实践

## Qdrant 简介

Qdrant 是高性能向量数据库，原生支持 dense + sparse 混合检索、HNSW 索引、标量量化和 Payload 过滤。Aureon 使用 Qdrant Cloud 作为向量后端。

## 集合配置最佳实践

### 生产环境推荐配置

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, SparseVectorParams, SparseIndexParams,
    ScalarQuantization, ScalarQuantizationConfig, ScalarType,
    HnswConfigDiff, OptimizersConfigDiff, PointStruct, SparseVector,
)

client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

client.create_collection(
    collection_name="aureon_docs",
    vectors_config={
        "dense": VectorParams(
            size=1024,
            distance=Distance.COSINE,
            hnsw_config=HnswConfigDiff(m=32, ef_construct=200),
            on_disk=True,  # 原始向量存磁盘
        ),
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams(
            index=SparseIndexParams(on_disk=False, full_scan_threshold=10000),
        ),
    },
    quantization_config=ScalarQuantization(
        type=ScalarType.INT8,
        quantile=0.99,
        always_ram=True,  # 量化向量常驻内存
    ),
    hnsw_config=HnswConfigDiff(ef_search=128),
    optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
)
```

### 关键参数说明

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| m | 32 | HNSW 每层连接数 |
| ef_construct | 200 | 构建时搜索宽度 |
| ef_search | 128 | 查询时搜索宽度 |
| on_disk | True | 原始向量存磁盘 |
| always_ram | True | 量化向量常驻内存 |
| quantile | 0.99 | INT8 量化分位数 |
| full_scan_threshold | 10000 | 稀疏向量全扫描阈值 |

## 文档索引

### BGE-M3 联合编码

```python
async def index_document(
    doc_id: str,
    text: str,
    metadata: dict,
    model,  # BGEM3FlagModel
    client: QdrantClient,
):
    """索引文档：dense + sparse 联合向量"""
    output = model.encode(
        [text],
        return_dense=True,
        return_sparse=True,
    )

    dense_vec = output["dense_vecs"][0].tolist()
    sparse_weights = output["lexical_weights"][0]

    point = PointStruct(
        id=doc_id,
        vector={
            "dense": dense_vec,
            "sparse": SparseVector(
                indices=list(sparse_weights.keys()),
                values=list(sparse_weights.values()),
            ),
        },
        payload={
            "text": text,
            "metadata.slug": metadata.get("slug", ""),
            "metadata.language": metadata.get("language", "zh"),
            "metadata.source": metadata.get("source", ""),
            "metadata.tenant_id": metadata.get("tenant_id", "default"),
        },
    )

    client.upsert(collection_name="aureon_docs", points=[point])
```

### Payload 索引

```python
# 为 Payload 字段创建索引，支持过滤查询
client.create_payload_index(
    collection_name="aureon_docs",
    field_name="metadata.slug",
    field_schema="keyword",
)
client.create_payload_index(
    collection_name="aureon_docs",
    field_name="metadata.language",
    field_schema="keyword",
)
client.create_payload_index(
    collection_name="aureon_docs",
    field_name="metadata.tenant_id",
    field_schema="keyword",
)
```

## Hybrid Search

### 基本查询

```python
from qdrant_client.models import Query, FusionQuery

async def hybrid_search(
    query_text: str,
    model,
    client: QdrantClient,
    k: int = 10,
    tenant_id: str | None = None,
):
    """Hybrid Search：dense + sparse + RRF 融合"""
    output = model.encode(
        [query_text],
        return_dense=True,
        return_sparse=True,
    )

    dense_vec = output["dense_vecs"][0].tolist()
    sparse_weights = output["lexical_weights"][0]

    # 构建过滤条件
    filter_conditions = None
    if tenant_id:
        filter_conditions = {
            "must": [{"key": "metadata.tenant_id", "match": {"value": tenant_id}}]
        }

    results = client.query_points(
        collection_name="aureon_docs",
        prefetch=[
            Query(
                vector_name="dense",
                vector=dense_vec,
                limit=k * 3,
                filter=filter_conditions,
            ),
            Query(
                vector_name="sparse",
                vector=SparseVector(
                    indices=list(sparse_weights.keys()),
                    values=list(sparse_weights.values()),
                ),
                limit=k * 3,
                filter=filter_conditions,
            ),
        ],
        query=FusionQuery(fusion="rrf"),
        limit=k,
    )

    return results.points
```

### 带过滤的查询

```python
# 按语言过滤
results = client.query_points(
    collection_name="aureon_docs",
    prefetch=[...],
    query=FusionQuery(fusion="rrf"),
    limit=k,
    query_filter={
        "must": [
            {"key": "metadata.language", "match": {"value": "zh"}},
        ]
    },
)
```

## 性能优化

### 批量操作

```python
# 批量插入
points = [create_point(doc) for doc in documents]
client.upsert(collection_name="aureon_docs", points=points)

# 批量搜索
results = client.query_batch_points(
    collection_name="aureon_docs",
    requests=[...],
)
```

### 优化器调优

```python
# 调整优化器参数
client.update_collection(
    collection_name="aureon_docs",
    optimizers_config=OptimizersConfigDiff(
        indexing_threshold=20000,  # 累积 20000 点后开始索引
        memmap_threshold=50000,   # 超过 50000 点使用 memmap
    ),
)
```

## 关键事实

1. **Qdrant 原生支持 dense + sparse 混合检索**，通过 RRF 融合两种向量的检索结果，无需外部 BM25 服务
2. **生产环境推荐 HNSW 参数**：m=32、ef_construct=200、ef_search=128，INT8 量化 always_ram=True
3. **BGE-M3 一次推理同时生成 dense 和 sparse 向量**，插入 Qdrant 时使用 PointStruct 的 vector 字段分别存储
4. **Payload 索引**为 slug、language、source、tenant_id 创建 keyword 索引，支持过滤查询
5. **Hybrid Search 使用 Qdrant 原生 RRF 融合**，prefetch 分别指定 dense 和 sparse 查询，最终通过 FusionQuery(fusion="rrf") 融合
