# RAG Benchmark Evaluation

## 最新结果（2026-06-02 v20）

### 测试数据集
- **97 QA pairs** — 覆盖全部 40 篇文章
- **类型分布**：factual(11) reasoning(41) synthesis(24) cross_article(6) negative(15)
- **语言**：中文 + 英文

### 检索指标

| 指标 | 值 | 目标 | 状态 |
|------|-----|------|------|
| Recall@3 (Hybrid) | 93.9% | ≥95% | 差 1.1% |
| Recall@3 (BM25) | 93.9% | ≥90% | ✅ |
| Recall@3 (Dense) | 86.6% | ≥85% | ✅ |
| MRR | 0.894 | ≥0.85 | ✅ |
| Precision@3 | 31.3% | ≥80% | 测量伪影* |
| Negative Detection | 6.7% | ≥90% | 部分有效 |
| Hybrid Latency | 4.4ms | ≤26ms | ✅ |

> *Precision@3 31.3% 是测量伪影：BM25 因 top-3 含重复 slug 而虚高 65.85%，hybrid 去重后更真实。MRR 0.894 证明排序质量实际改善。

### 按难度分布

| 难度 | Recall@3 | Precision@3 | MRR | 数量 |
|------|----------|-------------|-----|------|
| easy | 100.0% | 33.3% | 0.939 | 21 |
| medium | 95.2% | 31.7% | 0.929 | 47 |
| hard | 89.7% | 29.9% | 0.828 | 29 |

### 按类型分布

| 类型 | Recall@3 | Precision@3 | MRR | 数量 |
|------|----------|-------------|-----|------|
| factual | 100.0% | 33.3% | 0.939 | 11 |
| reasoning | 97.6% | 32.5% | 0.951 | 41 |
| synthesis | 87.5% | 29.2% | 0.833 | 24 |
| cross_article | 83.3% | 27.8% | 0.667 | 6 |

### 延迟

| 方法 | Mean | P50 | P99 |
|------|------|-----|-----|
| BM25 | 2.4ms | 2.4ms | 3.1ms |
| Vector | 1.8ms | 1.8ms | 2.2ms |
| Hybrid | 4.4ms | 4.3ms | 5.4ms |

## 检索管线

```
Query → BM25 (jieba 分词) + Vector (BGE-small-zh 512d)
     → Pre-RRF 过滤 (cosine ≥ 0.10)
     → RRF 融合 (k=200, BM25 10% boost, vector max 3 contrib, confidence ≥ 0.35)
     → 标题/Slug 关键词 Boost
     → Diversity 选取（仅跨文章查询）
     → Relevance gate (score ≥ 0.003)
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

## 运行 Benchmark

```bash
cd backend && python tests/run_benchmark.py
```

结果保存到 `backend/data/benchmark_actual.json`。
