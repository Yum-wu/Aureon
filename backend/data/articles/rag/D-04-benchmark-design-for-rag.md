# RAG Benchmark 设计：数据集构建与指标选择

## Benchmark 的目标

RAG Benchmark 的核心目标是**量化评估 RAG 系统的质量和性能**，为优化提供数据驱动的决策依据。一个好的 Benchmark 需要：代表性、可复现、可比较。

## 数据集构建

### QA 数据集设计

```yaml
# benchmark_config.yaml
qa_dataset:
  - question: "什么是 RAG？"
    expected_answer: "RAG 是检索增强生成技术，由 Lewis 等人在 2020 年提出，将信息检索与文本生成结合。"
    source_article: "A-07-retrieval-augmented-generation-overview"
    is_negative: false
    difficulty: "simple"

  - question: "RAG 与 Fine-tuning 如何选择？"
    expected_answer: "选择取决于场景：RAG 适合知识频繁更新、需要来源追溯的场景；Fine-tuning 适合特定任务优化、延迟敏感的场景。"
    source_article: "C-03-adaptive-rag-query-routing"
    is_negative: false
    difficulty: "complex"

  - question: "Aureon 的定价是多少？"
    expected_answer: null
    source_article: null
    is_negative: true
    difficulty: null
```

### 数据集构成原则

1. **覆盖度**：覆盖所有知识领域和查询类型
2. **难度分层**：简单/中等/复杂查询各占约 1/3
3. **负例包含**：至少 10% 的查询是系统无法回答的
4. **可验证性**：每个正例有明确的 expected_answer 和 source_article

### 数据集规模

| 文档规模 | 推荐 QA 数量 | 说明 |
|---------|-------------|------|
| < 100 | 20-50 | 基础验证 |
| 100-500 | 50-100 | 标准测试 |
| 500-1000 | 100-200 | 全面评估 |
| > 1000 | 200+ | 压力测试 |

### 合成数据生成

```python
async def generate_qa_dataset(
    articles: list[dict],
    llm,
    n_questions_per_article: int = 3,
) -> list[dict]:
    """从文章生成 QA 数据集"""
    dataset = []

    for article in articles:
        prompt = f"""基于以下文章，生成 {n_questions_per_article} 个问题和答案对。
问题应该涵盖不同难度：
- 1 个简单问题（事实型）
- 1 个中等问题（分析型）
- 1 个复杂问题（推理型）

文章内容：
{article['content'][:2000]}

请用 JSON 格式输出：
[{{"question": "...", "expected_answer": "...", "difficulty": "simple/medium/complex"}}]"""

        response = await llm.ainvoke(prompt)
        qa_pairs = json.loads(response)

        for qa in qa_pairs:
            qa["source_article"] = article["slug"]
            qa["is_negative"] = False
            dataset.append(qa)

    return dataset
```

## 指标选择

### 检索指标

| 指标 | 公式 | 适用场景 | 目标 |
|------|------|---------|------|
| Recall@K | 命中数/相关总数 | 评估召回能力 | >=0.95 |
| MRR | 1/第一个相关结果的排名 | 评估排序质量 | >=0.85 |
| nDCG@K | 归一化折损累积增益 | 评估排序质量（考虑位置权重） | >=0.80 |
| Precision@K | 命中数/K | 评估精度 | >=0.70 |

### 生成指标

| 指标 | 评估内容 | 目标 |
|------|---------|------|
| Faithfulness | 答案是否忠实于检索文档 | >=0.70 |
| Answer Relevancy | 答案是否回应查询 | >=0.75 |
| Answer Correctness | 答案是否正确 | >=0.70 |
| Hallucination Rate | 幻觉比例 | <=0.20 |

### 延迟指标

| 指标 | 含义 | 目标 |
|------|------|------|
| TTFT P50 | 首 Token 延迟中位数 | <=2000ms |
| TPOT | 每 Token 生成延迟 | <=100ms/tok |
| E2E P50 | 端到端延迟中位数 | <=5000ms |

### 安全指标

| 指标 | 含义 | 目标 |
|------|------|------|
| PII Leakage | PII 泄露评分 | >=0.90 |
| Toxicity | 毒性评分 | >=0.90 |
| Negative Detection | 负例检测准确率 | >=0.80 |

## Benchmark 执行

### 三阶段执行

```python
# 阶段 1：Railway 采集（192 queries + TTFT/TPOT）
cd backend && python tests/run_full_benchmark.py --phase 1

# 阶段 2：本地 LLM-as-Judge 评估
cd backend && python tests/run_full_benchmark.py --phase 2

# 阶段 3：汇总报告
cd backend && python tests/run_full_benchmark.py --phase 3
```

### 报告格式

```python
benchmark_report = {
    "date": "2026-06-16",
    "pipeline_version": "v2.3",
    "qa_dataset_size": 192,
    "metrics": {
        "faithfulness": 0.979,
        "answer_relevancy": 0.917,
        "answer_correctness": 0.733,
        "hallucination": 0.000,
        "negative_detection": 0.90,
        "mrr": 0.888,
        "recall_at_5": 0.924,
    },
    "latency": {
        "ttft_p50_ms": 610,
        "tpot_ms_per_tok": 72.9,
        "e2e_p50_ms": 980,
    },
    "thresholds_met": True,
}
```

## 关键事实

1. **QA 数据集应包含正例和负例**，正例覆盖不同难度（简单/中等/复杂各 1/3），负例至少占 10%
2. **检索指标推荐 Recall@5 和 MRR**，生成指标推荐 Faithfulness 和 Answer Relevancy，延迟指标推荐 TTFT 和 E2E
3. **Benchmark 执行分三阶段**：Railway 采集（延迟数据）→ 本地 LLM-as-Judge 评估（质量数据）→ 汇总报告
4. **数据集规模与文档规模成正比**：<100 文档用 20-50 条 QA，>1000 文档用 200+ 条
5. **Aureon 的 Benchmark 包含 192 条 QA**，所有客户可见指标均达标，内部优化指标（Contextual Relevancy/Recall）仍在优化中
