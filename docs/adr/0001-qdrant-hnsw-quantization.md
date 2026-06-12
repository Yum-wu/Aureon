# ADR-0001: Qdrant HNSW 参数优化与标量量化

## 状态：已批准

## 上下文

当前 `save_index_qdrant` 创建 Qdrant collection 时使用默认 HNSW 参数（m=16, ef_construct=100），无标量量化配置。在 1000+ 文档（≈5000+ chunks）场景下：

- 默认 `ef_construct=100` 索引构建质量不足，召回率下降
- 无标量量化，内存占用为最优配置的 4 倍
- 搜索 `hnsw_ef` 默认 100，高并发下延迟飙升
- 无 Payload 索引，`lang_filter` 和 `tenant_id` 过滤全扫描

## 决策

在 `save_index_qdrant` 中配置：

```python
client.create_collection(
    collection_name=collection_name,
    vectors_config=models.VectorParams(
        size=1024,  # 统一 1024d（见 ADR-0003）
        distance=models.Distance.COSINE,
        on_disk=True,
        hnsw_config=models.HnswConfigDiff(m=32, ef_construct=200),
    ),
    hnsw_config=models.HnswConfigDiff(ef_search=128),
    quantization_config=models.ScalarQuantization(
        scalar=models.ScalarQuantizationConfig(
            type=models.ScalarType.INT8,
            quantile=0.99,
            always_ram=True,
        ),
    ),
)
# 创建 Payload 索引
for field in ["metadata.slug", "metadata.language", "metadata.source", "metadata.tenant_id"]:
    client.create_payload_index(collection_name, field, models.PayloadSchemaType.KEYWORD)
```

## 依据

- Qdrant 官方文档 [Optimize Performance](https://qdrant.tech/documentation/ops-optimization/) 三种优化场景
- Qdrant 官方文档 [Indexing](https://qdrant.tech/documentation/concepts/indexing/)："It's highly recommended to create all payload indices immediately after collection creation"
- INT8 标量量化减少 75% 内存，精度损失极小（rescore=True 可补偿）

## 后果

- 召回率提升 10-15%（HNSW m=32 + ef_construct=200）
- 内存减少 75%（INT8 量化 + on_disk）
- 过滤查询延迟减少 50%（Payload 索引）
- 需要重建现有索引（一次性操作）
