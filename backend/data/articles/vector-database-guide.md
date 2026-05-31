---
title: "向量数据库完全指南"
slug: "vector-database-guide"
language: "zh"
source: "vector-database-guide.md"
---

# 向量数据库完全指南

## 什么是向量数据库

向量数据库是专门用于存储和检索高维向量数据的数据库。与传统关系型数据库按字段精确匹配不同，向量数据库通过计算向量间的**相似度**（如余弦相似度、欧氏距离）来查找最近邻，是 RAG、推荐系统、图像检索等应用的基础设施。

核心能力：给定一个查询向量，快速找到数据库中与其最相似的 Top-K 个向量。

## 为什么需要向量数据库

**传统数据库的局限**：
- SQL 只能做精确匹配或范围查询，无法理解语义
- 全文搜索依赖关键词，"猫科动物"搜不到"老虎"

**向量数据库的优势**：
- 语义搜索：理解含义而非关键词
- 高维检索：支持数百到数千维度的向量
- 相似度排序：返回最相关的 K 个结果
- 扩展性：支持百万到十亿级向量

## 索引算法原理

### Flat（暴力搜索）

逐一计算查询向量与所有存储向量的距离，精确但慢。

```
时间复杂度：O(n × d)，n 为向量数，d 为维度
适用：数据量 < 10 万
```

### IVF（Inverted File Index）

将向量空间用 K-Means 聚类划分为若干区域（Voronoi cells），检索时只在最近的几个区域内搜索。

```
流程：向量 → 聚类分配 → 检索时只搜索 Top-N 个最近聚类中心的区域
时间复杂度：O(n/k × d)，k 为聚类数
适用：中等规模（10万-1000万），需要平衡精度和速度
```

### HNSW（Hierarchical Navigable Small World）

构建多层图结构，底层包含所有向量，上层是稀疏的"高速公路"。检索时从顶层开始逐层下降，快速定位目标区域。

```
流程：构建多层图 → 从顶层入口点开始 → 逐层贪心搜索 → 底层精确搜索
特点：查询速度快，内存占用高
适用：对延迟敏感的场景（实时搜索）
```

### 三种算法对比

| 算法 | 查询速度 | 内存占用 | 精度 | 适用规模 |
|------|---------|---------|------|---------|
| Flat | 慢 | 低 | 100% | < 10万 |
| IVF | 中等 | 中等 | 95%+ | 10万-1000万 |
| HNSW | 快 | 高 | 98%+ | 10万-1亿 |

## 主流向量数据库对比

### ChromaDB

**特点**：轻量级、嵌入式、开发者友好，适合原型和小中型项目。

```python
# 安装
# pip install chromadb

import chromadb

# 方式 1：内存模式（开发测试）
client = chromadb.Client()

# 方式 2：持久化存储
client = chromadb.PersistentClient(path="./chroma_db")

# 创建集合
collection = client.get_or_create_collection(
    name="my_docs",
    metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
)

# 添加文档
collection.add(
    documents=["LangChain 是 LLM 应用框架", "RAG 是检索增强生成"],
    metadatas=[{"source": "doc1"}, {"source": "doc2"}],
    ids=["id1", "id2"]
)

# 查询
results = collection.query(
    query_texts=["什么是 LLM 框架？"],
    n_results=5,
    include=["documents", "distances", "metadatas"]
)
print(results)
```

ChromaDB 默认使用 HNSW 索引，适合 100 万以下向量的场景。

### Pinecone

**特点**：全托管云服务，开箱即用，无需运维。

```python
from pinecone import Pinecone

pc = Pinecone(api_key="your-api-key")
index = pc.Index("my-index")

# 写入向量
index.upsert(vectors=[
    {"id": "doc1", "values": [0.1, 0.2, ...], "metadata": {"source": "wiki"}}
])

# 查询
results = index.query(
    vector=[0.1, 0.2, ...],
    top_k=5,
    include_metadata=True
)
```

适合不想自己运维、预算充足的团队。

### Qdrant

**特点**：开源、Rust 编写、性能优秀、支持丰富的过滤条件。

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(host="localhost", port=6333)

# 创建集合
client.create_collection(
    collection_name="my_docs",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
)

# 插入向量
client.upsert(
    collection_name="my_docs",
    points=[
        PointStruct(id=1, vector=[0.1]*1536, payload={"source": "doc1"})
    ]
)

# 带过滤的查询
from qdrant_client.models import Filter, FieldCondition, MatchValue

results = client.query_points(
    collection_name="my_docs",
    query=[0.1]*1536,
    limit=5,
    query_filter=Filter(
        must=[FieldCondition(key="source", match=MatchValue(value="doc1"))]
    )
)
```

### Weaviate

**特点**：支持混合搜索（向量 + BM25）、GraphQL API、内置向量化模块。

### Milvus

**特点**：开源分布式向量数据库，支持十亿级向量，国产项目。

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://localhost:19530")

# 创建集合
client.create_collection(
    collection_name="my_docs",
    dimension=1536,
    metric_type="COSINE"
)

# 插入数据
client.insert(
    collection_name="my_docs",
    data=[
        {"id": 1, "vector": [0.1]*1536, "text": "RAG 是检索增强生成"}
    ]
)

# 查询
results = client.search(
    collection_name="my_docs",
    data=[[0.1]*1536],
    limit=5
)
```

### pgvector

**特点**：PostgreSQL 扩展，适合已有 PG 基础设施的团队。

```sql
-- 启用扩展
CREATE EXTENSION vector;

-- 创建表
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1536)
);

-- 创建 HNSW 索引
CREATE INDEX ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 语义查询
SELECT content, 1 - (embedding <=> '[0.1, 0.2, ...]') AS similarity
FROM documents
ORDER BY embedding <=> '[0.1, 0.2, ...]'
LIMIT 5;
```

## 选型建议

| 场景 | 推荐 | 原因 |
|------|------|------|
| 原型开发 | ChromaDB | 零配置，Python 原生 |
| 小型项目（<10万） | ChromaDB / pgvector | 简单够用 |
| 中型项目（10万-1000万） | Qdrant / Milvus | 性能优秀，可自托管 |
| 大型项目（>1000万） | Milvus / Pinecone | 分布式支持 |
| 已有 PostgreSQL | pgvector | 无需额外基础设施 |
| 不想运维 | Pinecone | 全托管 |
| 需要混合搜索 | Weaviate | 内置 BM25 + 向量 |

## 性能优化要点

1. **维度选择**：768 维（BGE-small）比 1536 维（OpenAI）快一倍，精度损失有限时优先选低维
2. **索引参数**：HNSW 的 M 和 ef_construction 参数影响精度/速度权衡
3. **批量操作**：插入和查询尽量批量执行，减少网络往返
4. **元数据过滤**：先用元数据缩小范围，再做向量检索
5. **内存管理**：向量数据库的内存消耗与向量数量和维度成正比，注意容量规划
