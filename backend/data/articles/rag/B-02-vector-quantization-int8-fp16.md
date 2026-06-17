# 向量量化：INT8 vs FP16 延迟-精度权衡

## 量化的必要性

向量数据库的存储和检索成本随文档规模线性增长。一个 1024 维的 FP32 向量占用 4KB，百万级文档需要约 4GB 仅存储向量。量化（Quantization）通过降低数值精度来压缩向量，在存储、内存和检索速度之间与精度做权衡。

## 量化方法分类

### 标量量化（Scalar Quantization）

将每个浮点数量化为低位整数：

- **FP32 → FP16**：半精度浮点，2x 压缩
- **FP32 → INT8**：8 位整数，4x 压缩
- **FP32 → INT4**：4 位整数，8x 压缩
- **FP32 → INT1**：二值量化，32x 压缩

### 乘积量化（Product Quantization, PQ）

将向量分成多个子空间，每个子空间独立量化：

```python
import numpy as np

def product_quantize(vectors: np.ndarray, n_subspaces: int = 16, n_bits: int = 8) -> dict:
    """乘积量化

    Args:
        vectors: [n_docs, dim] 原始向量
        n_subspaces: 子空间数量
        n_bits: 每个子空间的量化位数

    Returns:
        量化参数和编码
    """
    n_docs, dim = vectors.shape
    sub_dim = dim // n_subspaces

    codebooks = []
    codes = []

    for i in range(n_subspaces):
        # 提取子空间向量
        sub_vectors = vectors[:, i * sub_dim : (i + 1) * sub_dim]

        # K-Means 聚类
        n_centroids = 2 ** n_bits
        centroids = kmeans(sub_vectors, n_centroids)

        # 编码为质心索引
        assignments = assign_to_centroids(sub_vectors, centroids)

        codebooks.append(centroids)
        codes.append(assignments)

    return {"codebooks": codebooks, "codes": codes, "n_subspaces": n_subspaces}
```

## INT8 标量量化

### 原理

将 FP32 向量的每个分量映射到 [-128, 127] 的整数范围：

```python
def int8_quantize(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """INT8 标量量化

    Returns:
        quantized: 量化后的 INT8 向量
        scales: 每个维度的缩放因子
        offsets: 每个维度的偏移量
    """
    # 计算每个维度的最小值和最大值
    dim_min = vectors.min(axis=0)
    dim_max = vectors.max(axis=0)

    # 缩放因子和偏移量
    scales = (dim_max - dim_min) / 255.0
    offsets = dim_min

    # 量化
    quantized = np.round((vectors - offsets) / scales).astype(np.int8)
    quantized = np.clip(quantized, -128, 127)

    return quantized, scales, offsets


def int8_dequantize(quantized: np.ndarray, scales: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """INT8 反量化"""
    return quantized.astype(np.float32) * scales + offsets
```

### Qdrant 中的 INT8 量化

```python
from qdrant_client.models import ScalarQuantization, ScalarQuantizationConfig, ScalarType

# 创建集合时启用 INT8 量化
client.create_collection(
    collection_name="quantized_docs",
    vectors_config={"size": 1024, "distance": "Cosine"},
    quantization_config=ScalarQuantization(
        type=ScalarType.INT8,
        quantile=0.99,  # 99% 分位数裁剪，减少异常值影响
        always_ram=True,  # 量化向量常驻内存
    ),
)
```

### INT8 量化的精度影响

| 指标 | FP32 | INT8 | 差异 |
|------|------|------|------|
| Recall@5 | 92.4% | 91.8% | -0.6% |
| MRR | 0.888 | 0.875 | -0.013 |
| 存储空间 | 4KB/doc | 1KB/doc | -75% |
| 查询延迟 | 45ms | 25ms | -44% |
| 内存占用 | 4GB/1M docs | 1GB/1M docs | -75% |

## FP16 半精度

### 原理

将 FP32 的 32 位浮点数压缩为 16 位：

```python
def fp16_quantize(vectors: np.ndarray) -> np.ndarray:
    """FP16 半精度量化"""
    return vectors.astype(np.float16)


def fp16_cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """FP16 余弦相似度计算"""
    a_fp16 = a.astype(np.float16)
    b_fp16 = b.astype(np.float16)
    return np.dot(a_fp16, b_fp16) / (np.linalg.norm(a_fp16) * np.linalg.norm(b_fp16))
```

### FP16 vs INT8 对比

| 维度 | FP16 | INT8 |
|------|------|------|
| 压缩比 | 2x | 4x |
| 精度损失 | <0.1% | 0.5-1% |
| 计算加速 | GPU 原生支持 | 需要反量化 |
| 动态范围 | ±65504 | -128~127 |
| 适用场景 | GPU 推理 | 内存优化 |

## 二值量化

### 原理

将向量二值化，仅保留符号信息：

```python
def binary_quantize(vectors: np.ndarray) -> np.ndarray:
    """二值量化：sign 函数"""
    return (vectors > 0).astype(np.uint8)
```

二值量化的检索使用汉明距离（Hamming Distance），速度极快：

```python
def hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    """汉明距离"""
    xor = np.bitwise_xor(a, b)
    return np.unpackbits(xor).sum()
```

### 二值量化的精度影响

| 指标 | FP32 | Binary | 差异 |
|------|------|--------|------|
| Recall@5 | 92.4% | 75-85% | -7~17% |
| 存储空间 | 4KB/doc | 128B/doc | -97% |
| 查询延迟 | 45ms | 5ms | -89% |

二值量化适合作为**粗筛层**，先快速过滤大量不相关文档，再用高精度向量精排。

## Qdrant 量化配置最佳实践

### 推荐配置

```python
from qdrant_client.models import (
    ScalarQuantization, ScalarQuantizationConfig, ScalarType,
    HnswConfigDiff, OptimizersConfigDiff,
)

# 生产环境推荐配置
client.create_collection(
    collection_name="production_docs",
    vectors_config={
        "size": 1024,
        "distance": "Cosine",
        "hnsw_config": HnswConfigDiff(
            m=32,
            ef_construct=200,
        ),
        "on_disk": True,  # 原始向量存磁盘
    },
    quantization_config=ScalarQuantization(
        type=ScalarType.INT8,
        quantile=0.99,
        always_ram=True,  # 量化向量常驻内存
    ),
    hnsw_config=HnswConfigDiff(
        ef_search=128,
    ),
    optimizers_config=OptimizersConfigDiff(
        indexing_threshold=20000,
    ),
)
```

### 存储策略

- **原始向量**：存磁盘（on_disk=True），用于精确重排
- **量化向量**：常驻内存（always_ram=True），用于快速检索
- **Payload**：按需配置，热数据常驻内存

## 量化选择决策

```
文档规模 < 100K？
├── 是 → FP32（无需量化，内存足够）
└── 否 → 延迟敏感？
    ├── 是 → INT8 + always_ram（4x 压缩，查询快 2x）
    └── 否 → FP16（2x 压缩，精度损失最小）
```

## 关键事实

1. **INT8 标量量化将 FP32 向量压缩 4 倍**，精度损失约 0.5-1%，查询速度提升约 2 倍，是生产环境的首选量化方案
2. **FP16 半精度压缩 2 倍**，精度损失 <0.1%，GPU 原生支持加速计算，适合 GPU 推理场景
3. **Qdrant 的 INT8 量化配置**推荐 quantile=0.99（99% 分位数裁剪）+ always_ram=True（量化向量常驻内存），原始向量存磁盘
4. **二值量化压缩 32 倍**，但精度损失 7-17%，适合作为粗筛层快速过滤大量不相关文档
5. **量化选择取决于文档规模**：<100K 文档无需量化，>100K 文档推荐 INT8，延迟极致敏感场景考虑二值量化粗筛
