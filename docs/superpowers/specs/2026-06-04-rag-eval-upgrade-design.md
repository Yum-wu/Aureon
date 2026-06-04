# Aureon RAG 评估体系升级设计

**日期**: 2026-06-04
**方案**: DeepEval + 现有评估器混合方案
**状态**: 待实施

---

## 1. 背景

Aureon RAG 系统已有基础评估能力（`evaluator.py` 提供 Recall@k、nDCG、Faithfulness、Latency），但缺少 RAGAS 标准的 Context Precision/Relevance、Answer Relevancy、Hallucination 检测等企业级指标。本次升级补齐这些指标，使评估结果具有行业公信力。

### 1.1 现有评估能力

| 模块 | 指标 | 状态 |
|------|------|:---:|
| `evaluator.py` | Recall@k, nDCG@k | ✅ |
| `evaluator.py` | Faithfulness (LLM-as-Judge) | ✅ |
| `evaluator.py` | Latency (P50/P99) | ✅ |
| `evaluator.py` | `run_full_evaluation()` | ✅ |
| `qa_chain.py` | `check_faithfulness()` (claim-level) | ✅ |
| `evaluation/` | 数据库表 + API 端点 | ✅ |

### 1.2 缺失指标（本次补齐）

| 指标 | 来源 | 说明 |
|------|------|------|
| Context Precision | RAGAS | 检索到的文档中有多少真正相关 |
| Context Recall | RAGAS | ground truth 中的信息有多少被检索到 |
| Context Relevancy | RAGAS | 检索结果与查询的相关程度 |
| Answer Relevancy | RAGAS | 回答是否切题 |
| Hallucination | DeepEval | 回答中无上下文支撑的内容比例 |
| Answer Correctness | DeepEval | 回答与 ground truth 的事实一致性 |

---

## 2. 架构

```
backend/app/rag/evaluator.py          ← 现有（保留）
  ├── evaluate_recall()              ✅ 已有
  ├── ndcg_at_k()                    ✅ 已有
  ├── evaluate_faithfulness()        ✅ 已有
  ├── evaluate_latency()             ✅ 已有
  └── run_full_evaluation()          ✅ 已有

backend/tests/deepeval_eval.py       ← 新增（DeepEval 集成）
  ├── build_test_cases()             ← QA 对 → LLMTestCase 转换
  ├── run_deepeval_metrics()         ← DeepEval 六指标评估
  └── format_deepeval_results()      ← 结果格式化

backend/app/rag/eval_runner.py       ← 新增（统一 Runner）
  ├── run_full_suite()               ← 调用 evaluator + deepeval
  ├── save_results_to_db()           ← 写入 evaluation 数据库
  └── generate_report()              ← 输出 Markdown 报告

backend/tests/test_data_golden.py    ← 新增（测试数据集管理）
  ├── GOLDEN_97QA                    ← 全量 97 QA
  ├── CORE_REGRESSION_30QA           ← 核心回归集
  └── DIFFICULT_CASES_15QA           ← 困难用例

backend/tests/test_rag_quality.py    ← 新增（Pytest 质量门禁）
  └── test_rag_quality_gate()        ← CI 入口
```

### 2.1 数据流

```
test_data_golden.py
    ↓ (提供 QA 对)
deepeval_eval.py
    ↓ (转换为 LLMTestCase)
    ↓ (调用 retrieve_fn + rag_query_fn)
    ↓ (DeepEval.evaluate())
eval_runner.py
    ↓ (合并 evaluator.py 结果 + DeepEval 结果)
    ↓
    ├──→ evaluation 数据库 (历史追踪)
    └──→ Markdown 报告文件 (人工查看)
```

### 2.2 核心原则

- 现有 `evaluator.py` 不删不改，只在其基础上新增
- DeepEval 作为独立模块，通过 `eval_runner.py` 统一调用
- 测试数据从现有 `test_data.py` 迁移并扩展

---

## 3. DeepEval 集成

### 3.1 依赖

```bash
pip install deepeval
```

### 3.2 测试用例构建

```python
def build_test_cases(qa_pairs, retrieve_fn, rag_query_fn):
    """将 QA 对转换为 DeepEval LLMTestCase。"""
    test_cases = []
    for qa in qa_pairs:
        # 检索上下文
        chunks = retrieve_fn(qa["question"], top_k=5)
        retrieval_context = [c["text"] for c in chunks]
        
        # RAG 生成答案
        result = rag_query_fn(qa["question"])
        
        test_case = LLMTestCase(
            input=qa["question"],
            actual_output=result.answer,
            retrieval_context=retrieval_context,
            expected_output=qa["answer"],
            context=[qa["answer"]],  # ground truth 用于幻觉检测
        )
        test_cases.append(test_case)
    return test_cases
```

### 3.3 评估指标

```python
METRICS = {
    # 检索质量
    "context_precision": ContextualPrecisionMetric(threshold=0.7),
    "context_recall": ContextualRecallMetric(threshold=0.75),
    "context_relevancy": ContextualRelevancyMetric(threshold=0.7),
    # 生成质量
    "answer_relevancy": AnswerRelevancyMetric(threshold=0.6),
    "faithfulness": FaithfulnessMetric(threshold=0.7),
    "hallucination": HallucinationMetric(threshold=0.5),
}
```

### 3.4 评估执行

```python
def run_deepeval_metrics(test_cases):
    """运行 DeepEval 六指标评估。"""
    metrics = list(METRICS.values())
    result = evaluate(test_cases=test_cases, metrics=metrics)
    return format_results(result)
```

---

## 4. 测试数据集

### 4.1 三层数据集

| 层级 | 数据集 | 数量 | 触发条件 | 预估时间 |
|------|--------|:---:|----------|----------|
| L1 | 全量 97 QA | 97 | 每周定时 / 版本发布前 | ~8-10 min |
| L2 | 核心回归集 | 30 | 每次 PR/提交 | ~2-3 min |
| L3 | 困难用例 | 15 | 版本升级前 | ~3-5 min |

### 4.2 核心回归集选择标准

从 97 QA 中精选 30 个，确保：
- 每个 category 至少 2 个（core_concept, tech_stack, embedding, framework, deployment, caching, devops, frontend）
- 包含正面和负面（知识库外）问题
- 包含中英文混合查询
- 覆盖高、中、低难度

### 4.3 困难用例设计

| 类型 | 数量 | 示例 |
|------|:---:|------|
| 多跳推理 | 3 | 需要串联多文档回答 |
| 反事实查询 | 3 | 知识库中没有的信息 |
| 模糊查询 | 3 | 语义相近但答案不同 |
| 长尾问题 | 3 | 罕见但重要 |
| 边界情况 | 3 | 空查询、超长查询、特殊字符 |

### 4.4 数据集格式

```python
{
    "question": str,           # 查询文本
    "answer": str,             # 标准答案
    "source_article": str,     # 期望来源文档
    "category": str,           # 分类
    "difficulty": str,         # easy/medium/hard
    "requires_multi_hop": bool, # 是否需要多跳推理
    "is_negative": bool,       # 是否为知识库外问题
    "version": str,            # 数据集版本号
}
```

---

## 5. 统一 Runner

### 5.1 `run_full_suite()`

```python
def run_full_suite(
    dataset_name: str = "golden_97qa",
    include_deepeval: bool = True,
    include_latency: bool = True,
) -> dict:
    """运行完整评估套件。"""
    # 1. 加载数据集
    qa_pairs = load_dataset(dataset_name)
    
    # 2. 运行现有评估器
    existing_results = run_full_evaluation(
        retrieve_fn=retrieve,
        rag_query_fn=rag_query,
        llm=create_llm(),
    )
    
    # 3. 运行 DeepEval（可选）
    deepeval_results = None
    if include_deepeval:
        test_cases = build_test_cases(qa_pairs, retrieve, rag_query)
        deepeval_results = run_deepeval_metrics(test_cases)
    
    # 4. 合并结果
    combined = merge_results(existing_results, deepeval_results)
    combined["dataset_version"] = get_dataset_version(dataset_name)
    combined["git_version"] = get_git_version()
    combined["recent_changes"] = get_recent_changes()
    
    return combined
```

### 5.2 报告生成

报告包含：
- 测试执行时间
- RAG 系统版本（git commit hash）
- 系统配置（嵌入模型、LLM、向量库）
- 最近 5 条 git 改动
- 全部指标得分 + 阈值对比 + 状态标记
- 每个 QA 的详细评估结果

输出路径：`docs/rag-evaluation/reports/YYYY-MM-DD-report.md`

### 5.3 数据库存储

复用现有 `evaluation` 数据库表：
- `metric_name`: 指标名（如 `context_precision`）
- `metric_value`: 分数
- `dataset_version`: 数据集版本
- `run_timestamp`: 运行时间

---

## 6. CI 质量门禁

### 6.1 GitHub Actions 配置

```yaml
# .github/workflows/rag-quality.yml
name: RAG Quality Gate
on:
  pull_request:
    paths:
      - 'backend/app/rag/**'
      - 'backend/tests/**'

jobs:
  rag-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r backend/requirements.txt deepeval
      - run: |
          cd backend
          python -m pytest tests/test_rag_quality.py -v --timeout=300
```

### 6.2 质量门禁阈值

| 指标 | 阈值 | 动作 |
|------|:---:|------|
| Faithfulness | ≥ 0.70 | 低于 → 阻止合并 |
| Context Recall | ≥ 0.75 | 低于 → 阻止合并 |
| Context Precision | ≥ 0.70 | 低于 → 阻止合并 |
| Answer Relevancy | ≥ 0.60 | 低于 → 警告 |
| Hallucination | < 0.20 | 高于 → 阻止合并 |
| 任何指标下降 | > 5% | 相比 baseline → 警告 |

---

## 7. 实现计划

### Phase 1：DeepEval 集成（1 天）
- [ ] 安装 deepeval 依赖
- [ ] 创建 `deepeval_eval.py`（build_test_cases + run_deepeval_metrics）
- [ ] 创建 `test_data_golden.py`（三层数据集）
- [ ] 本地验证 DeepEval 六指标可运行

### Phase 2：统一 Runner（1 天）
- [ ] 创建 `eval_runner.py`（run_full_suite + save_results_to_db + generate_report）
- [ ] 对接现有 `evaluation` 数据库表
- [ ] 实现 Markdown 报告生成

### Phase 3：CI 集成（0.5 天）
- [ ] 创建 `test_rag_quality.py`（Pytest 入口）
- [ ] 配置 GitHub Actions workflow
- [ ] 设置质量门禁阈值

### Phase 4：困难用例 + 验证（0.5 天）
- [ ] 设计 15 个困难测试用例
- [ ] 全量运行验证
- [ ] 调优阈值

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| DeepEval LLM-as-Judge 成本 | 每次评估消耗 API token | 核心回归集控制在 30 QA |
| DeepEval 评判不稳定 | 同一样本多次评估分数波动 | 设置 temperature=0，取多次平均 |
| 本地 Python 3.14 兼容性 | DeepEval 可能不兼容 | CI 用 Python 3.12 |
| Railway DashScope 连接不稳 | 评估时 API 超时 | 本地运行评估，结果同步到数据库 |
