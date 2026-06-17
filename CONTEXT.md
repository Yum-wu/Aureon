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
