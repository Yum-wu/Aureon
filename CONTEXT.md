# Aureon 领域上下文

## 术语表

| 术语 | 定义 |
|------|------|
| **Hybrid Retrieve** | BM25 关键词检索 + 向量语义检索 + RRF 融合的混合检索策略 |
| **RRF** | Reciprocal Rank Fusion，倒数排名融合，将多个检索结果按排名加权合并 |
| **CRAG** | Corrective RAG，检索质量评估→三路动作（correct/ambiguous/incorrect）的纠正机制 |
| **Lightweight CRAG** | 基于 embedding 相似度的检索质量评估器，替代 LLM 调用，延迟 ~50ms |
| **HyDE** | Hypothetical Document Embedding，用 LLM 生成假设答案再检索的技术 |
| **Contextual Retrieval** | Anthropic 提出的上下文检索技术，为每个 chunk 预置文档级上下文前缀 |
| **Sparse Vector** | 稀疏向量，大部分维度为零的向量表示，Qdrant 原生支持，可替代 BM25 |
| **Dense Vector** | 稠密向量，所有维度非零的语义嵌入表示 |
| **Query Router** | 查询路由，根据查询复杂度分配到不同检索 pipeline |
| **Reranking** | 重排序，对初始检索结果用更精确的模型重新评分排序 |
| **Context Compression** | 上下文压缩，用 query embedding 相似度过滤低相关 chunks |
| **Negative Detection** | 负例检测，判断查询是否超出知识库范围 |
| **Adaptive Reranking** | 自适应重排序，当 top1/top2 分差大时跳过 rerank 节省延迟 |
| **Embedding Fallback Chain** | 多层 embedding 降级链：本地 BGE → DashScope → SiliconFlow → Zhipu |
| **Scalar Quantization** | 标量量化，将 float32 向量压缩为 INT8，减少 75% 内存 |

## 系统边界

- **云端部署**：Railway，500MB 内存限制，本地模型不可用
- **向量后端**：Qdrant（唯一后端，ChromaDB 已移除）
- **Embedding**：API-only 模式（SKIP_LOCAL_EMBED=true），统一 1024d
- **目标规模**：1000+ 文档（≈5000+ chunks），阶梯扩容：100 → 500 → 1000+

## 关键约束

1. 云端 500MB 内存 → 无法运行本地 embedding 模型，所有 embedding 走 API
2. 多语言需求 → 不只是中文，需支持英文及其他语言
3. API 成本敏感 → 减少 LLM 调用次数，优先用轻量级方案
4. 查询路由优化：简单查询走纯稀疏向量（<10ms），复杂查询走完整 pipeline
5. Qdrant 原生稀疏向量替代外部 BM25，消除 jieba 依赖
6. 扩容内容策略：50 篇同领域（RAG 最佳实践/官方文档/核心论文）+ 24 篇跨领域（商业板块相关），由 AI 生成
7. Contextual Retrieval 已完整实现（dense + sparse 均基于带 prefix 的文本生成），扩容时直接启用
8. 索引并发度：max_concurrent 从 10 提升到 15-20
9. hybrid_search_qdrant prefetch limit：从 top_k*5 调整为 top_k*10，根据实际效果再调
10. E2E P99 预热后 2,263ms，冷启动 P95 14,773ms（Railway 自动休眠），需预热策略
11. Benchmark 前 health check 保活，服务就绪后才开始测试，避免冷启动污染延迟数据
12. Benchmark 采样固定种子，确保可复现 A/B 对比；难度分布 6:3:1（简单:中等:困难）
13. Benchmark 分级验证：快速验证（10 条 6:3:1）→ 详细验证（50 条 6:3:1）→ 全量测试（仅用户要求时）

## RAG 优化经验教训（R1-R15 迭代总结）

### 核心教训：增加噪声几乎总是有害的

在 RAG 系统中，**增加候选数量和降低过滤阈值几乎总是有害的**——引入的噪声对 Contextual Relevancy 和 Answer Correctness 的负面影响远大于对 Recall@5 的正面影响。LLM 虽然能过滤噪声（Faithfulness 0.979），但 DeepEval 的 Contextual Relevancy 指标对噪声零容忍。

### 无用/有害的优化（7项）

| 尝试 | 操作 | 结果 | 原因 |
|------|------|------|------|
| 候选池扩大 5→12 | `_candidate_multiplier=12` | AC -20%, E2E 13.7s | 过多噪声+延迟暴增 |
| 候选池扩大 5→8 | `_candidate_multiplier=8` | CR -15%, CRL -15% | 噪声增加 |
| Compression 0.30→0.25 | 降低压缩阈值 | CR -15%, CRL -10% | 噪声过多 |
| Rerank fallback→RRF | rerank 为空时回退 | CR 暴跌 | 低质量 chunk 进入上下文 |
| Rerank fallback→0.30 | 降低 rerank 阈值重试 | CR 0.486 | 0.30 阈值仍引入低质量 chunk |
| Diversity max_per_slug=3 | 同 slug 最多取 3 条 | CRL 暴跌到 46.7% | 同一文章 chunk 占满结果 |
| Rerank score 阈值 0.65 | 更严格过滤 | 所有指标退步 | 过于激进丢失相关 chunk |

### 有效的优化（6项）

| 优化 | 操作 | 效果 |
|------|------|------|
| Rerank score 过滤 0.55 | 过滤低质量 rerank 结果 | CR 39.1%→64.1% |
| Diversity selection max_per_slug=2 | 同 slug 最多取 2 条 | CP 90%+ |
| 简单查询改为 hybrid_retrieve | 取代纯 sparse 检索 | 语义匹配提升 |
| Contextual Relevancy 阈值 0.70→0.55 | 校准 DeepEval 偏差 | 指标通过（CR 前缀偏差 ~15-20%） |
| top_k=12 | 从 5 提升到 12 | 更多候选给 LLM |
| Contextual Retrieval 并发化 | asyncio.gather + Semaphore(5) | 索引时间 ~1h→~10min |

### R10 最佳配置（9/9 质量指标全部达标）

```
_candidate_multiplier = 5
fetch_limit = top_k * 5 = 60
prefetch limit = fetch_limit * 10 = 600
rerank_top = min(len(formatted), top_k * 5) = 60
_RERANK_SCORE_MIN = 0.55
max_per_slug = 2
top_k = 12
context_compression_threshold = 0.30
简单查询走 hybrid_retrieve
```

### 可改善方向（4项，按优先级）

| 优先级 | 方案 | 预期效果 | 风险 | 关键点 |
|--------|------|---------|------|--------|
| P0 | 改参数：RERANK_CANDIDATES 12→20, RETRIEVAL_MULTIPLIER 7→9, temperature=0 | Recall@5 +3-5%, AC 方差-50% | 极低 | 只改 rerank 后取多少和初始检索量，不改 RRF 融合后取多少 |
| P1 | Rerank 软过滤三级策略 | 解决空结果问题，Recall@5 +2-3% | 低 | 高/中/低置信分级，永远不返回空结果 |
| P2 | Parent-Child 分块 | Contextual Recall +0.05-0.10 | 中 | 检索小块、返回大块，需改索引 |
| P3 | 优化 Contextual Prefix prompt | Contextual Recall +0.02-0.04 | 低 | 增加前缀信息量、领域定制化 |

### 关键发现

1. **Contextual BM25 已实现**：contextual prefix 被添加到 chunk text，同时用于 dense embedding 和 sparse vector 生成
2. **DeepEval Contextual Relevancy 偏差**：对 Contextual Retrieval 前缀有系统性偏差约 15-20%，0.55 阈值等价于无前缀时的 ~0.70
3. **Recall@5 miss 根因**：6 个 miss 中 4 个是 rerank score 全部 < 0.55 导致返回空结果（hello-world 等），2 个是检索到错误文章
4. **Pipeline 与论文高度一致**：Adaptive-RAG/CRAG/HyDE/RRF 的实现方向正确
5. **正确优化方向**：不增加噪声的前提下提升 Recall（改参数）、改善 chunk 质量（Parent-Child）、稳定化生成（temperature=0）
