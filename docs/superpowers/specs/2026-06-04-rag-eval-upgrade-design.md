# Aureon RAG 评估体系升级设计

**日期**: 2026-06-04
**方案**: DeepEval + 现有评估器混合方案
**状态**: ✅ 已实施（5/6 指标已跑通，HallucinationMetric 待解决）

---

## 1. 背景

Aureon RAG 系统已有基础评估能力（`evaluator.py` 提供 Recall@k、nDCG、Faithfulness、Latency），但缺少 RAGAS 标准的 Context Precision/Relevance、Answer Relevancy 等企业级指标。本次升级补齐这些指标，使评估结果具有行业公信力。

### 1.1 现有评估能力（evaluator.py，保留不变）

| 指标 | 状态 |
|------|:---:|
| Recall@k | ✅ |
| nDCG@k | ✅ |
| Faithfulness (LLM-as-Judge) | ✅ |
| Latency (P50/P99) | ✅ |
| `run_full_evaluation()` | ✅ |

### 1.2 本次新增指标（DeepEval RAGAS）

| 指标 | 状态 | 首批验证分数 |
|------|:---:|:---:|
| Context Precision | ✅ 已集成 | 0.55 ⚠️ |
| Context Recall | ✅ 已集成 | 1.00 ✅ |
| Context Relevancy | ✅ 已集成 | 0.43 ⚠️ |
| Answer Relevancy | ✅ 已集成 | 0.87 ✅ |
| Faithfulness | ✅ 已集成 | 0.93 ✅ |
| Hallucination | ⏳ 待实现 | - |

> HallucinationMetric 需要单独的 OpenAI-compatible 配置，DeepSeek API 的 hallucination 检测端点暂不兼容。已预留 TODO。

---

## 2. 已实施架构

```
backend/app/rag/evaluator.py          ← 现有（保留，未修改）
  ├── evaluate_recall()              ✅
  ├── ndcg_at_k()                    ✅
  ├── evaluate_faithfulness()        ✅
  ├── evaluate_latency()             ✅
  └── run_full_evaluation()          ✅

backend/tests/deepeval_eval.py       ← 新增 ✅ (243 行)
  ├── build_test_cases()             ← QA 对 → LLMTestCase 转换
  ├── run_deepeval_metrics()         ← DeepEval 5 指标评估
  └── format_results()               ← 结果格式化

backend/app/rag/eval_runner.py       ← 新增 ✅ (283 行)
  ├── run_full_suite()               ← 调用 evaluator + deepeval
  ├── save_results_to_db()           ← 写入 evaluation 数据库
  └── generate_report()              ← 输出 Markdown 报告

backend/tests/test_data_golden.py    ← 新增 ✅ (478 行)
  ├── GOLDEN_97QA                    ← 全量 97 QA
  ├── CORE_REGRESSION_27QA           ← 核心回归集
  └── DIFFICULT_CASES_15QA           ← 困难用例

backend/tests/test_rag_quality.py    ← 新增 ✅ (100 行)
  └── CI 质量门禁 (Pytest)

.github/workflows/rag-quality.yml   ← 新增 ✅
  └── PR 触发 30 QA / main 触发 97 QA
```

### 2.1 数据流（已实现）

```
test_data_golden.py
    ↓ (提供 QA 对)
deepeval_eval.py
    ↓ (转换为 LLMTestCase)
    ↓ (调用 retrieve_fn + rag_query_fn)
    ↓ (DeepEval.evaluate() → DeepSeek API 做 LLM-as-Judge)
eval_runner.py
    ↓ (合并 evaluator.py 结果 + DeepEval 结果)
    ↓
    ├──→ evaluation 数据库 (历史追踪)
    └──→ Markdown 报告文件 (docs/rag-evaluation/reports/)
```

### 2.2 LLM-as-Judge 配置

DeepEval 默认使用 OpenAI API 做评判。已修改为自动使用 DeepSeek：

```python
# 自动检测：无 OPENAI_API_KEY 时，用 DeepSeek 做 judge
os.environ["OPENAI_API_KEY"] = settings.llm_api_key
os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1"
model = "deepseek-chat"  # API 模型名（非显示名）
```

---

## 3. 测试数据集

### 3.1 三层数据集（已实现）

| 层级 | 数据集 | 数量 | 触发条件 | 预估时间 |
|------|--------|:---:|----------|----------|
| L1 | 全量 97 QA | 97 | 每周定时 / 版本发布前 | ~8-10 min |
| L2 | 核心回归集 | 27 | 每次 PR/提交 | ~2-3 min |
| L3 | 困难用例 | 15 | 版本升级前 | ~3-5 min |

> 核心回归集实际为 27 QA（非设计时预估的 30），覆盖 10 个 category。

### 3.2 困难用例分布（已实现）

| 类型 | 数量 |
|------|:---:|
| 多跳推理 | 3 |
| 反事实查询 | 3 |
| 模糊查询 | 3 |
| 边界情况 | 3 |
| 长尾问题 | 3 |

---

## 4. 首批验证结果

### 4.1 5 QA 快速验证（2026-06-04）

| 指标 | 分数 | 阈值 | 状态 | 说明 |
|------|:---:|:---:|:---:|------|
| Contextual Precision | 0.55 | ≥0.70 | ⚠️ | 检索排序需优化 |
| Contextual Recall | **1.00** | ≥0.75 | ✅ | 检索覆盖完美 |
| Contextual Relevancy | 0.43 | ≥0.70 | ⚠️ | 检索相关性需优化 |
| Answer Relevancy | **0.87** | ≥0.60 | ✅ | 回答切题 |
| Faithfulness | **0.93** | ≥0.70 | ✅ | 无幻觉 |

### 4.2 既有指标基线（97 QA）

| 指标 | 分数 | 标准 |
|------|:---:|:---:|
| Recall@5 (仅正面) | 90.2% | ≥85% ✅ |
| MRR | 0.696 | ≥0.600 ✅ |
| E2E 延迟 | 3,659ms | <5000ms ✅ |
| LLM 占比 | 99.8% | - |

### 4.3 分析

- **Contextual Precision/Relevancy 偏低**：检索到的文档排序和相关性需要优化。可能原因：RRF 融合后排名不够精确，或 top_k=5 时引入了噪音文档
- **Recall/Faithfulness 优秀**：检索覆盖和回答忠实度已达企业标准
- **Answer Relevancy 0.87**：超过 0.60 阈值，回答切题性好

---

## 5. CI 质量门禁

### 5.1 GitHub Actions（已配置）

```yaml
# .github/workflows/rag-quality.yml
on:
  pull_request:     # 触发条件：PR 修改 rag 相关文件
  workflow_dispatch: # 手动触发
```

- PR → 运行核心回归集 27 QA
- main → 运行全量 97 QA

### 5.2 质量门禁阈值

| 指标 | 阈值 | 动作 |
|------|:---:|------|
| Faithfulness | ≥ 0.70 | 低于 → 阻止合并 |
| Context Recall | ≥ 0.75 | 低于 → 阻止合并 |
| Context Precision | ≥ 0.70 | 低于 → 阻止合并 |
| Answer Relevancy | ≥ 0.60 | 低于 → 警告 |
| 任何指标下降 | > 5% | 相比 baseline → 警告 |

---

## 6. 已知问题与待办

### 6.1 已解决

| 问题 | 解决方案 |
|------|---------|
| DeepEval 默认用 OpenAI API | 自动配置 DeepSeek 作为 judge |
| ChromaDB 版本冲突（`_type` 错误） | 重建索引，pydantic 降级到 2.9.x |
| NumPy 2.x 不兼容 ChromaDB 0.5 | 限制 numpy<2 |
| `show_indicator` 参数不存在 | 移除该参数 |

### 6.2 待解决

| 问题 | 优先级 | 说明 |
|------|:---:|------|
| HallucinationMetric 不兼容 DeepSeek | 中 | 需要 DeepEval 支持自定义 hallucination 检测端点 |
| Context Precision/Relevancy 偏低 | 高 | 需要优化检索排序（Reranker 或 RRF 权重调整） |
| 核心回归集 27 QA（设计目标 30） | 低 | 补充 3 个 QA 达到 30 |
| 本地 Python 3.12 venv 依赖不完整 | 中 | 需要完整重装 requirements.txt |

---

## 7. 文件清单

| 文件 | 行数 | 说明 | 状态 |
|------|:---:|------|:---:|
| `tests/deepeval_eval.py` | 243 | DeepEval 集成 | ✅ |
| `tests/eval_runner.py` | 283 | 统一 Runner | ✅ |
| `tests/test_data_golden.py` | 478 | 三层测试数据集 | ✅ |
| `tests/test_rag_quality.py` | 100 | CI 质量门禁 | ✅ |
| `tests/benchmark_rag.py` | 262 | L1 快速测试 | ✅ |
| `tests/benchmark_rag_full.py` | 248 | L2 全量检索测试 | ✅ |
| `tests/benchmark_e2e.py` | 300 | L3 端到端测试 | ✅ |
| `.github/workflows/rag-quality.yml` | 45 | CI 工作流 | ✅ |
| `docs/rag-enterprise-analysis.md` | 200+ | 企业级对标报告 | ✅ |
| `requirements.txt` | 55 | +deepeval 依赖 | ✅ |
