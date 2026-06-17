# Aureon RAG 渐进式优化设计

**日期**：2026-06-16
**状态**：待审核
**方案**：方案 A（渐进式优化）

## 背景

当前 26 篇 / 434 chunks 数据集下的核心瓶颈：

| 指标 | 当前值 | 目标 | 差距 |
|------|--------|------|------|
| Contextual Relevancy | 39.1% | ≥70% | -30.9% |
| Contextual Recall | 50.0% | ≥75% | -25.0% |
| Recall@5 | 92.4% | ≥95% | -2.6% |

已达标指标：Faithfulness 0.979、Answer Relevancy 0.917、MRR 0.888、TTFT P50 610ms、E2E P99 2,263ms（预热后）。

## 已确认决策

1. 阶梯扩容：100 → 500 → 1000+
2. 扩容内容：50 篇 RAG 同领域 + 24 篇商业跨领域，AI 生成
3. Contextual Retrieval 已完整实现（dense + sparse 均基于带 prefix 文本生成）
4. 索引并发度 max_concurrent 从 10 提升到 15
5. hybrid_search_qdrant prefetch limit 从 top_k*5 → top_k*10
6. E2E P99 预热后 2,263ms，冷启动用 health check 保活
7. Benchmark 前 health check 保活再测试
8. Benchmark 固定种子采样，难度分布 6:3:1（简单:中等:困难）
9. 优化优先级：Contextual Relevancy > Contextual Recall > Recall@5
10. 文档越多性能越低，100 篇目标应高于 1000+ 篇
11. Benchmark 分级验证：快速验证（10 条 6:3:1）→ 详细验证（50 条 6:3:1）→ 全量测试（仅用户要求时）

## 识别的 7 个缺漏

| # | 缺漏 | 影响 | 阶段 |
|---|------|------|------|
| 1 | 冗余过滤缺失 | 同文章多 chunk 重复，Relevancy 低 | 阶段 2 |
| 2 | Qdrant RRF k 值未优化 | RRF 排序区分度不够 | 阶段 1 |
| 3 | compression_threshold 过低（0.15） | 几乎不过滤，噪声多 | 阶段 1 |
| 4 | hybrid_search_qdrant 缺少 parent_text | 与 retrieve_qdrant 行为不一致 | 阶段 1 |
| 5 | QA 数据集未覆盖扩容后文档 | Benchmark 不可靠 | 阶段 2 |
| 6 | 负例检测 benchmark 为 0.0 | 负例评估缺失 | 阶段 1 |
| 7 | 无生成质量反馈闭环 | 低质量答案无法回溯 | 阶段 3 |

---

## 阶段 1：扩容 + 快速修复

### 1.1 文档生成（74 篇）

**同领域 50 篇（RAG 最佳实践）**：

| 组 | 主题 | 篇数 | 示例标题 |
|---|------|------|---------|
| A | 检索技术 | 12 | "HyDE 原理与实践"、"Multi-Query 检索策略对比"、"BM25 vs 稀疏向量：RAG 关键词检索演进" |
| B | 向量与 Embedding | 10 | "Embedding 模型选型指南：BGE vs OpenAI vs Cohere"、"向量量化：INT8 vs FP16 延迟-精度权衡"、"Matryoshka 嵌入：一次编码多粒度检索" |
| C | RAG 架构 | 12 | "CRAG 自纠正检索增强生成"、"Self-RAG：学习检索-生成-批评"、"Adaptive-RAG 查询路由设计"、"Contextual Retrieval 实战" |
| D | 评估与优化 | 10 | "RAG 评估框架：RAG Triad 与 DeepEval"、"Faithfulness vs Relevancy：当指标冲突时怎么办"、"RAG 延迟优化：从 5s 到 1s 的实践" |
| E | 工具与平台 | 6 | "Qdrant Hybrid Search 最佳实践"、"LangChain RAG 模块深度解析"、"Cohere Rerank 集成指南" |

**跨领域 24 篇（商业板块）**：

| 组 | 主题 | 篇数 | 示例标题 |
|---|------|------|---------|
| F | 产品与增长 | 8 | "SaaS 定价策略：从免费到企业级"、"PLG vs SLG：产品驱动增长的选择"、"用户留存分析框架" |
| G | 管理与运营 | 8 | "OKR 落地实践：从目标到关键结果"、"敏捷开发中的技术债务治理"、"数据驱动决策：A/B 测试设计指南" |
| H | 商业模式 | 8 | "MVP 方法论：最小可行产品的验证循环"、"B2B 客户成功管理框架"、"从 0 到 1 的产品路线图规划" |

**文档质量要求**：
- 每篇 2000-4000 字，结构化（标题层级、列表、代码块）
- 中英混合：中文为主，技术术语保留英文
- 每篇包含 3-5 个可检索的关键事实点（供 QA 数据集使用）
- 保存为 Markdown，放入 `backend/data/articles/` 对应目录

### 1.2 代码修复（4 项）

**#2 Qdrant RRF k 值**
- 文件：`qdrant_ops.py`
- 改动：`hybrid_search_qdrant` 的 `FusionQuery` 传入 `rrf_k=60`（Qdrant 服务端 RRF，k=60 让排名靠前结果权重更大，区分度更高）
- 前置：确认 `qdrant_client` 版本是否支持 `rrf_k` 参数

**#3 compression_threshold 调整**
- 文件：`config.py`
- 改动：`context_compression_threshold` 从 0.15 → 0.30
- 影响：过滤掉约 30-40% 低相关 chunk，CRAG retry 兜底

**#4 parent_text 一致性**
- 文件：`qdrant_ops.py`
- 改动：`hybrid_search_qdrant` 返回结果也用 `parent_text` 替代 `text`（与 `retrieve_qdrant` 行为一致）
- 逻辑：`parent_text = payload.get("metadata", {}).get("parent_text", "")`，有则用，无则 fallback

**#6 负例检测 benchmark 修复**
- 文件：`benchmark_enterprise.py` 或 `run_full_benchmark.py`
- 改动：确保负例 query 被固定采样且 `negative_detection_rate` 正确计算
- 验证：benchmark 结果中 `negative_detection` 不再为 0.0

### 1.3 参数调整

| 参数 | 当前值 | 新值 | 理由 |
|------|--------|------|------|
| `max_concurrent`（contextual prefix） | 10 | 15 | 加速索引构建 |
| prefetch limit | top_k*5 | top_k*10 | 扩大候选池提升 Recall |
| benchmark 采样 | 随机 | 固定种子 + 6:3:1 | 可复现对比 |
| benchmark 预热 | 无 | health check 保活 | 避免冷启动污染 |

### 1.4 全量索引 + Benchmark

1. Health check 保活 Railway
2. 全量索引（74 篇新文档 + 26 篇现有，启用 Contextual Retrieval）
3. 生成 QA 数据集（覆盖 100 篇，含 20 条负例，固定种子 6:3:1 分布）
4. 快速验证：10 条 QA（6 简单 / 3 中等 / 1 困难），确认 pipeline 基本可用
5. 详细验证：50 条 QA（30 简单 / 15 中等 / 5 困难），记录基线指标
6. 全量测试：仅在用户要求时跑全部 QA

**Benchmark 分级验证策略**：

| 级别 | QA 数量 | 用途 | 触发条件 |
|------|---------|------|---------|
| 快速验证 | 10 条（6:3:1） | 确认 pipeline 基本可用 | 每次代码改动后 |
| 详细验证 | 50 条（6:3:1） | 记录基线、对比优化效果 | 阶段里程碑 |
| 全量测试 | 全部 QA | 最终确认 | 仅用户要求时 |

---

## 阶段 2：检索质量深化

### 2.1 冗余过滤（#1）

**实现位置**：`qa_chain.py` 的 `compress_context` 函数之后，新增 `_deduplicate_chunks` 函数。

**算法**：
1. 按 slug 分组
2. 组内：计算 chunk 间 cosine 相似度（复用已有 embedding）
3. 如果两个 chunk cosine > 0.85 且同 slug：保留 compression_score 更高的，丢弃另一个
4. 不同 slug 间不做去重（保留跨文章多样性）
5. 返回去重后的 chunks

**设计决策**：
- 只做同 slug 去重：不同文章讨论同一概念是有价值的跨文档多样性
- 阈值 0.85：语义近似的常规分界线
- 复用已有 embedding：避免额外 API 调用
- 先按 compression_score 降序排列：确保保留最相关的 chunk

**预期效果**：8 chunks 中约 2-3 个同文章重复 → 去重后保留 5-6 个高质量 chunk，Relevancy 预计从 39% → 55-65%

### 2.2 QA 数据集扩展（#5）

- 每篇文档 2-3 条 QA，由 LLM 生成
- 简单 QA：直接从文档中提取事实
- 中等 QA：需要理解+推理
- 困难 QA：跨文档综合
- 负例 QA：知识库不覆盖的领域
- 数据集格式兼容现有 `benchmark_config.yaml`，新增 `difficulty` 字段

### 2.3 参数微调策略

基于阶段 1 benchmark 基线调整：

| 参数 | 当前值 | 调优方向 | 依据 |
|------|--------|---------|------|
| `retrieval_multiplier` | 12 | 降低到 6-8 | 100 篇时 96 候选过多 |
| `rerank_candidates` | 20 | 维持或微调 | 配合 prefetch limit 调整 |
| `context_compression_threshold` | 0.30 | 根据 Relevancy 微调 | Relevancy 仍低则提高到 0.35 |
| `adaptive_rerank_threshold` | 0.3 | 提高到 0.5 | 让更多查询跳过 rerank 降低延迟 |
| `crag_high_confidence` | 0.05 | 提高到 0.15 | 让 CRAG 更有区分度 |

---

## 阶段 3：闭环优化 + 阶梯扩容

### 3.1 生成质量反馈闭环（#7）

**实现位置**：`qa_chain.py` 的 `rag_query_astream` 函数中，生成完成后增加质量评估步骤。

**轻量级评估逻辑**（不额外调用 LLM）：
1. 检查 LLM 输出是否包含"文档中未提及"/"无法回答"等短语
2. 如果是，且检索 top_score > 0.3 → 触发 CRAG retry（用 variant query 重新检索）
3. 如果是，且检索 top_score < 0.3 → 确实无相关信息，直接返回"无法回答"
4. 记录到 feedback log（query, top_score, action）供后续分析

**用户投票反馈**：前端已有 👍👎 投票，结果写入 feedback log，定期分析低分 query 的检索质量。

### 3.2 阶梯扩容流程

每级扩容重复：生成文档 → 全量索引 → 扩展 QA → health check → benchmark → 参数微调 → 确认达标

**各级目标**（文档越多性能越低，100 篇目标应最高）：

| 级别 | 文档数 | Chunks（估） | Relevancy | Recall | Recall@5 |
|------|--------|-------------|-----------|--------|----------|
| 100 篇 | 100 | ~1,600 | ≥75% | ≥80% | ≥97% |
| 500 篇 | 500 | ~8,000 | ≥72% | ≥78% | ≥96% |
| 1000+ | 1000+ | ~16,000+ | ≥70% | ≥75% | ≥95% |

如果 100 篇时 Relevancy 达不到 75%，说明优化方向有问题，需要及时调整再扩容。

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| compression_threshold 提高导致 Recall 下降 | CRAG retry 兜底 + 阈值可回退 |
| 冗余过滤误删相关 chunk | 只做同 slug 去重，阈值 0.85 偏保守 |
| 100 篇文档内容质量不够 | 每篇包含 3-5 个可检索事实点，QA 数据集交叉验证 |
| Qdrant RRF k 值不支持 | 确认 API 版本，不支持则在客户端 post-processing |
| 扩容后参数需要重新调优 | 阶梯式扩容，每级 benchmark 对比 |
