# RAG Benchmark Evaluation

## 最新结果（2026-06-06 v24）

### 测试数据集
- **97 QA pairs** — 覆盖全部 40 篇文章
- **类型分布**：factual(11) reasoning(41) synthesis(24) cross_article(6) negative(15)
- **语言**：中文 + 英文

### 检索指标

| 指标 | 值 | 目标 | 状态 |
|------|-----|------|------|
| Recall@3 (Hybrid) | 95.1% | ≥95% | ✅ |
| Recall@10 (Hybrid) | 100% | ≥99% | ✅ |
| MRR | 0.913 | ≥0.85 | ✅ |
| Negative Detection | 100% | ≥90% | ✅ |
| Retrieval Latency | 5.8ms | ≤26ms | ✅ |
| Context Compression | ✅ | — | 嵌入相似度过滤 |
| CRAG Self-Correction | ✅ | — | 自动重写查询 |

### DeepEval 质量指标

| 指标 | 分数 | 阈值 | 状态 |
|------|------|------|------|
| Context Precision | 0.791 | 0.70 | ✅ |
| Context Recall | 0.776 | 0.75 | ✅ |
| Faithfulness | 0.967 | 0.70 | ✅ |
| Hallucination | 0.033 | 0.20 | ✅ |
| Pass Rate | 100% | ≥80% | ✅ |

### 延迟

| 方法 | Mean | P50 | P99 |
|------|------|-----|-----|
| BM25 | 2.5ms | 2.5ms | 3.1ms |
| Vector | 2.5ms | 2.5ms | 2.2ms |
| RRF | 0.8ms | 0.8ms | 1.0ms |
| Total | 5.8ms | 5.8ms | 6.3ms |

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
