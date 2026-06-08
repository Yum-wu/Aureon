# RAG Benchmark Evaluation

## 最新结果（2026-06-08 v31 全套 Benchmark）

### 测试数据集
- **192 QA pairs** — 覆盖全部 26 篇文章
- **类型分布**：factual(24) reasoning(92) synthesis(42) cross_article(14) negative(20)
- **难度分布**：easy(34) medium(105) hard(53)
- **语言**：中文 + 英文

### 检索指标（Hybrid RRF）

| 指标 | 值 | 目标 | 状态 |
|------|-----|------|------|
| Recall@3 (Hybrid) | 96.5% | ≥95% | ✅ |
| Recall@5 (Hybrid) | 100% | ≥85% | ✅ |
| Recall@10 (Hybrid) | 100% | ≥97% | ✅ |
| Precision@3 (Binary) | 96.5% | ≥80% | ✅ |
| MRR | 0.901 | ≥0.85 | ✅ |
| nDCG@10 | 0.914 | ≥0.80 | ✅ |
| Negative Detection | 50% | ≥90% | ⚠️ 需增强 |
| Context Compression | ✅ | — | 嵌入相似度过滤 |
| CRAG Self-Correction | ✅ | — | 自动重写查询 |

### 三种检索方法对比

| 方法 | Recall@3 | MRR | P50 延迟 |
|------|:---:|:---:|:---:|
| Hybrid (RRF) | **96.5%** | 0.884 | 154ms |
| BM25 | 95.9% | **0.912** | **1.9ms** |
| Dense (向量) | 93.6% | 0.874 | 142ms |

### 分类表现

| 难度 | Recall@3 | 样本数 |
|:---:|:---:|:---:|
| Easy | 95.2% | 21 |
| Medium | **98.0%** | 98 |
| Hard | 94.3% | 53 |

| 查询类型 | Recall@3 | 样本数 |
|:---:|:---:|:---:|
| Factual | 95.8% | 24 |
| Reasoning | **97.8%** | 92 |
| Synthesis | **97.6%** | 42 |
| Cross-article | 85.7% | 14 |

### 并发负载测试

| 并发数 | QPS | P50 延迟 | Recall |
|:---:|:---:|:---:|:---:|
| 1 | 4.6 | 151ms | 96.5% |
| 5 | **9.5** | 513ms | 96.5% |
| 10 | 9.6 | 987ms | 96.5% |
| 20 | 9.5 | 2,006ms | 96.5% |

### DeepEval 质量指标

| 指标 | 分数 | 阈值 | 状态 |
|------|------|------|------|
| Context Precision | 0.92+ | 0.70 | ✅ |
| Context Recall | 0.776 | 0.75 | ✅ |
| Faithfulness | 0.967 | 0.70 | ✅ |
| Hallucination | 0.033 | 0.20 | ✅ |
| Pass Rate | 100% | ≥80% | ✅ |

### E2E RAG 生成质量

| 指标 | 值 | 目标 | 状态 |
|------|:---:|:---:|:---:|
| Faithfulness | 95% | >90% | ✅ |
| Completeness | 0.74 | >0.50 | ✅ |
| Relevance | 0.21 | >0.50 | ⚠️ |
| LLM Latency | 2,868ms | <3,000ms | ✅ |
| E2E Total | 3,104ms | <5,000ms | ✅ |

### 延迟分布

| 方法 | Mean | P50 | P99 |
|------|------|-----|-----|
| BM25 | 1.9ms | 1.9ms | 2.9ms |
| Vector | 143.2ms | 142.1ms | 177.1ms |
| Hybrid | 174.3ms | 157.9ms | 252.4ms |

### 企业级基准评分

| 指标 | 值 | 目标 | 状态 |
|------|:---:|:---:|:---:|
| Recall@3 | 96.5% | ≥90% | PASS |
| Recall@5 | 100% | ≥95% | PASS |
| Recall@10 | 100% | ≥97% | PASS |
| Precision@3 | 96.5% | ≥80% | PASS |
| MRR | 0.884 | ≥0.80 | PASS |
| nDCG@10 | 0.914 | ≥0.80 | PASS |
| Negative Detection | 50% | ≥90% | FAIL |
| Latency P50 Hybrid | 158ms | ≤20ms | FAIL |
| Latency P99 Hybrid | 252ms | ≤100ms | FAIL |
| **企业级评分** | **6/9** | | |

### 规模预估（26→1000+ docs）

| 目标文档数 | 预估 Recall@3 | 预估 QPS@5 | 预估 P50 |
|:---:|:---:|:---:|:---:|
| 100 | 88.6% | 5.3 | 8.2ms |
| 250 | 84.2% | 4.9 | 9.1ms |
| 500 | 81.0% | 4.6 | 9.7ms |
| 1,000 | 77.7% | 4.4 | 10.3ms |

## 检索管线

```
Query → BM25 (jieba 分词) + Vector (BGE-small-zh 512d)
     → Pre-RRF 过滤 (cosine ≥ 0.10)
     → RRF 融合 (k=200, BM25 10% boost, vector max 3 contrib, confidence ≥ 0.35)
     → 标题/Slug 关键词 Boost
     → Diversity 选取（仅跨文章查询）
     → Relevance gate (score ≥ 0.003)
     → Context Compression (embedding similarity filter)
     → CRAG Self-Correction (retry on low quality)
     → Top-K 结果
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VECTOR_MIN_COSINE` | 0.10 | Pre-RRF 向量过滤阈值 |
| `VECTOR_CONFIDENCE_THRESHOLD` | 0.35 | RRF 向量置信度阈值 |
| `VECTOR_MAX_CONTRIB` | 3 | 向量参与 RRF 最大数量 |
| `RRF_K` | 200 | RRF 常数 k |
| `KW_MIN_RAW_SCORE` | 0.15 | BM25 最低原始分数 |
| `MIN_RELEVANCE_SCORE` | 0.003 | RRF 融合后最低分数 |

## 关键优化历史

| 版本 | 优化 | 效果 |
|------|------|------|
| v16 | BM25+ Scoring + RRF 去重 | Recall 78%→98% |
| v17 | BM25 预分词 | 延迟 153ms→2.1ms |
| v18 | 跨文章查询扩展 | +6 QA, Recall 97.4%→97.6% |
| v19 | QA 重建 + BM25 中文优化 | 97 QA, Recall 93.9%（更真实） |
| v20 | Pre-RRF 过滤 + RRF_K=200 + 多 LLM | MRR 0.878→0.894, 延迟 4.9→4.4ms |
| v23 | Contextual Retrieval + DeepEval | Context Precision +24.6%, Pass Rate 100% |
| v24 | Security + Context Compression + CRAG | 全链路安全加固 + 检索增强 |

## 运行 Benchmark

```bash
cd backend && python tests/run_benchmark.py
```

结果保存到 `backend/data/benchmark_actual.json`。
