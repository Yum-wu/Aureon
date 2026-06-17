# RAG 评估框架：RAG Triad 与 DeepEval

## RAG 评估的重要性

RAG 系统上线后，如何量化评估其质量是核心问题。没有评估就无法优化——你无法改善你无法衡量的东西。RAG 评估需要回答三个核心问题：**检索到的文档是否相关？生成的答案是否忠实于检索文档？答案是否回应了用户查询？**

## RAG Triad

### 三角评估框架

RAG Triad 由三个核心指标构成：

1. **Context Relevancy（上下文相关性）**：检索到的文档是否与查询相关
2. **Faithfulness（忠实度）**：答案是否忠实于检索文档，没有幻觉
3. **Answer Relevancy（答案相关性）**：答案是否回应了用户查询

```
         用户查询
          /    \
         /      \
  Answer        Context
  Relevancy    Relevancy
         \      /
          \    /
        Faithfulness
```

### 指标详解

#### Faithfulness（忠实度）

衡量答案是否完全基于检索文档，没有编造信息：

```python
# Faithfulness 计算方法
# 1. 将答案拆分为多个声明（claims）
# 2. 判断每个声明是否可以从检索文档中推导出来
# 3. Faithfulness = 可推导的声明数 / 总声明数

# 示例
# 检索文档：RAG 由 Lewis 等人在 2020 年提出
# 答案：RAG 是 2020 年由 Lewis 团队提出的技术
# 声明1：RAG 是一种技术 → 可推导 ✓
# 声明2：RAG 在 2020 年提出 → 可推导 ✓
# 声明3：由 Lewis 团队提出 → 可推导 ✓
# Faithfulness = 3/3 = 1.0
```

#### Answer Relevancy（答案相关性）

衡量答案是否回应了用户查询：

```python
# Answer Relevancy 计算方法
# 1. 从答案中反向生成可能的问题
# 2. 计算生成问题与原始查询的语义相似度
# 3. Answer Relevancy = 平均相似度

# 示例
# 查询：什么是 RAG？
# 答案：RAG 是检索增强生成技术，结合了信息检索和文本生成
# 生成的问题：["什么是检索增强生成？", "RAG 是什么技术？", "检索增强生成的定义是什么？"]
# 与原始查询的相似度：[0.92, 0.95, 0.88]
# Answer Relevancy = 0.917
```

#### Context Relevancy（上下文相关性）

衡量检索到的文档是否与查询相关：

```python
# Context Relevancy 计算方法
# 1. 判断检索文档中哪些句子与查询相关
# 2. Context Relevancy = 相关句子数 / 总句子数

# 示例
# 查询：RAG 的全称是什么？
# 文档1：RAG（Retrieval-Augmented Generation）是... → 相关
# 文档2：向量数据库是存储嵌入向量的... → 不相关
# Context Relevancy = 1/2 = 0.5
```

## DeepEval 评估框架

### 安装与配置

```python
# 安装
# pip install deepeval

from deepeval import evaluate
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
)
from deepeval.test_case import LLMTestCase

# 配置评估模型
from deepeval.models import DeepEvalBaseLLM

# 使用自定义 LLM 作为 Judge
class CustomJudgeLLM(DeepEvalBaseLLM):
    def __init__(self, model):
        self.model = model

    def load_model(self):
        return self.model

    async def generate(self, prompt: str) -> str:
        return await self.model.ainvoke(prompt)
```

### 构建测试用例

```python
async def build_test_cases(
    qa_dataset: list[dict],
    rag_pipeline,
) -> list[LLMTestCase]:
    """从 QA 数据集构建 DeepEval 测试用例"""
    test_cases = []

    for item in qa_dataset:
        query = item["question"]
        expected = item["expected_answer"]

        # 执行 RAG Pipeline
        result = await rag_pipeline.run(query)

        test_case = LLMTestCase(
            input=query,
            actual_output=result["answer"],
            expected_output=expected,
            retrieval_context=[doc.page_content for doc in result["docs"]],
        )
        test_cases.append(test_case)

    return test_cases
```

### 执行评估

```python
async def run_deepeval_metrics(
    test_cases: list[LLMTestCase],
    judge_model,
) -> dict:
    """运行 DeepEval 评估"""
    # 初始化指标
    faithfulness = FaithfulnessMetric(
        model=judge_model,
        threshold=0.7,
    )
    answer_relevancy = AnswerRelevancyMetric(
        model=judge_model,
        threshold=0.75,
    )
    contextual_relevancy = ContextualRelevancyMetric(
        model=judge_model,
        threshold=0.7,
    )

    # 执行评估
    results = evaluate(
        test_cases=test_cases,
        metrics=[faithfulness, answer_relevancy, contextual_relevancy],
        async_config=AsyncConfig(max_concurrent=15),
        cache_config=CacheConfig(use_cache=True),
    )

    return {
        "faithfulness": faithfulness.score,
        "answer_relevancy": answer_relevancy.score,
        "contextual_relevancy": contextual_relevancy.score,
    }
```

## Aureon 的评估结果

### RAG Triad 指标

| 指标 | 值 | 目标 | 状态 |
|------|-----|------|------|
| Faithfulness | 0.979 | >=0.70 | ✅ |
| Answer Relevancy | 0.917 | >=0.75 | ✅ |
| Answer Correctness | 0.733 | >=0.70 | ✅ |
| Hallucination | 0.000 | <=0.20 | ✅ |

### DeepEval 配置

- **Judge 模型**：`deepseek-ai/DeepSeek-V4-Flash`（硅基流动）
- **异步配置**：`AsyncConfig(max_concurrent=15)`
- **缓存配置**：`CacheConfig(use_cache=True)`
- **超时保护**：单次查询 60s + 整体评估 300s

## 评估最佳实践

1. **定期评估**：每次 Pipeline 变更后运行评估
2. **保留基线**：记录每次评估结果，对比变化趋势
3. **分层评估**：单元测试 → 质量门禁 → 性能基准 → 生产冒烟
4. **负例测试**：包含系统无法回答的查询，验证负例检测能力
5. **Judge 模型选择**：使用与生成模型不同的模型作为 Judge，避免偏见

## 关键事实

1. **RAG Triad 由三个核心指标构成**：Context Relevancy（检索相关性）、Faithfulness（忠实度）、Answer Relevancy（答案相关性）
2. **Faithfulness 衡量答案是否忠实于检索文档**，通过将答案拆分为声明并逐一验证可推导性来计算
3. **DeepEval 是最流行的 RAG 评估框架**，支持 Faithfulness、Answer Relevancy、Contextual Relevancy 等多种指标
4. **Aureon 的 Faithfulness 为 0.979**，Answer Relevancy 为 0.917，Hallucination 为 0.000，均超过目标阈值
5. **Judge 模型应与生成模型不同**，Aureon 使用 DeepSeek-V4-Flash 作为 Judge，避免评估偏见
