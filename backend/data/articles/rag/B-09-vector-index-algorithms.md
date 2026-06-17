# 向量索引算法：HNSW vs IVF vs ScaNN

## 向量索引的必要性

暴力搜索（Brute-Force）计算查询向量与所有文档向量的相似度，复杂度 O(N)，在百万级文档时延迟不可接受。向量索引算法通过空间划分或图结构实现近似最近邻（ANN）搜索，在可接受的精度损失下实现毫秒级检索。

## HNSW（分层可导航小世界图）

### 算法原理

HNSW（Hierarchical Navigable Small World）由 Malkov 和 Yashunin 于 2018 年提出，基于图结构的 ANN 算法：

1. **多层图结构**：类似跳表（Skip List），上层稀疏、下层稠密
2. **贪心搜索**：从最高层入口点开始，每层贪心移动到最近邻
3. **逐层下降**：到达当前层最近邻后，下降到下一层继续搜索

```
Layer 2:  A ──────────────── Z        （稀疏连接）
          │                    │
Layer 1:  A ──── D ──── M ──── Z      （中等连接）
          │      │      │      │
Layer 0:  A─B─C─D─E─F─G─M─N─O─Z       （稠密连接）
```

### 关键参数

| 参数 | 含义 | 推荐值 | 影响 |
|------|------|--------|------|
| m | 每层最大连接数 | 16-64 | 越大精度越高，内存越大 |
| ef_construct | 构建时搜索宽度 | 100-400 | 越大构建越慢，质量越高 |
| ef_search | 查询时搜索宽度 | 50-512 | 越大查询越慢，精度越高 |

### 构建过程

```python
def hnsw_insert(graph, vector, m=32, ef_construct=200):
    """HNSW 插入新向量"""
    # 1. 从最高层入口点开始
    entry_point = graph.entry_point
    current_layer = graph.max_layer

    # 2. 贪心搜索到向量所在层
    while current_layer > vector.layer:
        nearest = greedy_search(graph, entry_point, vector, current_layer)
        entry_point = nearest
        current_layer -= 1

    # 3. 从向量层到第 0 层，每层找 ef_construct 个最近邻
    for layer in range(vector.layer, -1, -1):
        neighbors = beam_search(graph, entry_point, vector, layer, ef_construct)

        # 4. 选择 m 个最近邻建立连接
        selected = select_neighbors(neighbors, m)
        for neighbor in selected:
            graph.add_edge(vector, neighbor, layer)
            # 反向连接（如果邻居连接数超过 m，需要修剪）
            if neighbor.connections(layer) > m:
                prune_connections(graph, neighbor, layer, m)
```

### 查询过程

```python
def hnsw_search(graph, query_vector, k=10, ef_search=128):
    """HNSW 查询"""
    # 1. 从最高层入口点开始
    entry_point = graph.entry_point
    current_layer = graph.max_layer

    # 2. 高层贪心搜索
    while current_layer > 0:
        nearest = greedy_search(graph, entry_point, query_vector, current_layer)
        entry_point = nearest
        current_layer -= 1

    # 3. 第 0 层 Beam Search
    candidates = beam_search(graph, entry_point, query_vector, 0, ef_search)

    # 4. 返回 Top-K
    return sorted(candidates, key=lambda x: x.distance)[:k]
```

## IVF（倒排文件索引）

### 算法原理

IVF（Inverted File Index）将向量空间划分为多个 Voronoi 单元，每个单元维护一个倒排列表：

1. **K-Means 聚类**：将所有向量聚类为 nlist 个簇
2. **倒排索引**：每个簇维护属于该簇的向量列表
3. **查询时**：先找最近的 nprobe 个簇，再在这些簇内搜索

```python
from faiss import IndexIVFFlat, IndexFlatL2

# 创建 IVF 索引
quantizer = IndexFlatL2(1024)  # 1024 维
index = IndexIVFFlat(quantizer, 1024, nlist=1000)  # 1000 个簇

# 训练（K-Means 聚类）
index.train(training_vectors)

# 添加向量
index.add(vectors)

# 查询
index.nprobe = 50  # 搜索 50 个簇
distances, indices = index.search(query_vector, k=10)
```

### 关键参数

| 参数 | 含义 | 推荐值 | 影响 |
|------|------|--------|------|
| nlist | 聚类数 | sqrt(N) ~ 4*sqrt(N) | 越大精度越高，内存越大 |
| nprobe | 查询搜索簇数 | 10-100 | 越大精度越高，速度越慢 |

## ScaNN（可扩展最近邻）

### 算法原理

ScaNN 由 Google Research 于 2020 年提出，结合了 IVF 和各向异性量化（Anisotropic Quantization）：

1. **IVF 划分**：与标准 IVF 类似，先聚类划分
2. **各向异性量化**：考虑量化误差的方向性，优先保持与查询方向一致的精度
3. **两阶段搜索**：粗筛 + 精排

```python
from scann import scann_builder

# 构建 ScaNN 索引
builder = scann_builder(
    db=vectors,
    num_neighbors=10,
    dimensions_per_block=2,
).score_ah(
    dimensions_per_block=2,
    anisotropic_quantization_threshold=0.2,
).reorder(
    100,  # 精排候选数
).build()

# 查询
indices, distances = builder.search_batched(query_vectors, final_num_neighbors=10)
```

## 三种算法对比

### 性能对比（1M 文档，1024 维）

| 算法 | Recall@10 | 查询延迟 | 构建时间 | 内存占用 |
|------|-----------|---------|---------|---------|
| HNSW (m=32, ef=128) | 99.2% | 2ms | 30min | 4.8GB |
| IVF (nlist=1000, nprobe=50) | 97.5% | 1ms | 5min | 4.2GB |
| ScaNN | 99.0% | 1.5ms | 15min | 4.0GB |
| Brute-Force | 100% | 500ms | 0 | 4.0GB |

### 特性对比

| 特性 | HNSW | IVF | ScaNN |
|------|------|-----|-------|
| 增量更新 | 支持 | 需重建 | 需重建 |
| 内存效率 | 中 | 高 | 最高 |
| 查询延迟 | 低 | 最低 | 低 |
| 精度 | 最高 | 中 | 高 |
| 构建速度 | 慢 | 最快 | 中 |
| 参数调优 | 简单 | 中等 | 复杂 |
| GPU 支持 | 部分 | 完整 | 完整 |

## Qdrant 中的 HNSW 配置

### 生产环境推荐配置

```python
from qdrant_client.models import VectorParams, HnswConfigDiff

# 创建集合
client.create_collection(
    collection_name="production_docs",
    vectors_config=VectorParams(
        size=1024,
        distance="Cosine",
        hnsw_config=HnswConfigDiff(
            m=32,              # 每层 32 个连接
            ef_construct=200,  # 构建时搜索宽度
        ),
        on_disk=True,  # 原始向量存磁盘
    ),
    hnsw_config=HnswConfigDiff(
        ef_search=128,  # 查询时搜索宽度
    ),
)
```

### 参数调优指南

```python
# 精度优先
precision_config = {"m": 64, "ef_construct": 400, "ef_search": 256}

# 延迟优先
latency_config = {"m": 16, "ef_construct": 100, "ef_search": 64}

# 平衡（推荐）
balanced_config = {"m": 32, "ef_construct": 200, "ef_search": 128}

# 内存优先
memory_config = {"m": 16, "ef_construct": 100, "ef_search": 64}
# + INT8 量化 + on_disk=True
```

## 关键事实

1. **HNSW 是当前最流行的 ANN 算法**，基于分层图结构，Recall@10 可达 99.2%，查询延迟约 2ms
2. **HNSW 的三个关键参数**：m（连接数，推荐 32）、ef_construct（构建宽度，推荐 200）、ef_search（查询宽度，推荐 128）
3. **IVF 通过 K-Means 聚类划分向量空间**，查询时只搜索最近的 nprobe 个簇，延迟最低但精度略低
4. **ScaNN 的各向异性量化**优先保持与查询方向一致的精度，在相同内存下精度优于标准 IVF
5. **Qdrant 默认使用 HNSW**，支持增量更新和在线构建，是生产环境的首选向量索引
