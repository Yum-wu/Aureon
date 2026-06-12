# ADR-0002: Qdrant 原生稀疏向量替代 jieba BM25

## 状态：已批准

## 上下文

当前 BM25 实现使用内存 jieba 分词 + 全量 scroll 重建：

- 1000 篇文档启动需 30-60s（scroll + jieba 分词）
- 每次 `add_to_index` 都 `force=True` 全量重建
- jieba 不支持英文，英文 BM25 效果极差
- 内存 BM25 无法持久化，重启后需重建
- 云端 500MB 内存限制，无法运行本地 BGE-M3 模型

## 决策

直接迁移到 Qdrant 原生稀疏向量（阶段 B），跳过阶段 A（增量 BM25）：

1. 使用 SiliconFlow BAAI/bge-m3 API 生成 sparse 向量（同时输出 dense + sparse）
2. 存储到 Qdrant 的 named vectors（dense + sparse 两个向量空间）
3. 使用 Qdrant Query API（v1.10+）的 prefetch + RRF 原生融合
4. 移除 jieba BM25 相关代码

```python
# 存储
client.upsert(collection_name, points=[
    PointStruct(
        id=i,
        vector={
            "dense": dense_embedding,
            "sparse": sparse_weights,  # BGE-M3 sparse 输出
        },
        payload={...}
    )
])

# 检索
client.query_points(
    collection_name=collection_name,
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=20),
        models.Prefetch(query=sparse_vector, using="sparse", limit=20),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
)
```

## 依据

- Qdrant v1.7+ 原生支持稀疏向量，[Sparse Vectors 文章](https://qdrant.tech/articles/sparse-vectors/)
- SPLADE/BGE-M3 sparse 在 MS MARCO 上 MRR@10 = 0.368，远超 BM25 的 0.184
- Anthropic Contextual Retrieval 论文："Embeddings+BM25 is better than embeddings on their own"
- SiliconFlow API 支持 BGE-M3 sparse 输出，无需本地模型

## 后果

- 启动时间 60s → <5s（无需 scroll + 分词）
- 英文检索质量大幅提升（BGE-M3 多语言）
- 消除 jieba 依赖，代码简化
- 需要 SiliconFlow API key 支持 BGE-M3 模型
- 需要重建索引（一次性操作）
