# LLM-as-Judge 评估：原理、偏见与缓解

## LLM-as-Judge 的原理

LLM-as-Judge 是使用大语言模型作为评估者，对 RAG 系统的输出进行质量评分。相比人工评估，LLM-as-Judge 具有成本低、速度快、一致性高的优势，但也存在偏见和可靠性问题。

### 评估方式

1. **单点评分**：给单个输出打分（1-5 分）
2. **成对比较**：比较两个输出的优劣
3. **参考对比**：将输出与参考答案对比

```python
JUDGE_PROMPT = """你是一个 RAG 系统质量评估专家。请评估以下答案的质量。

查询：{query}
检索文档：{context}
生成的答案：{answer}

请从以下维度评分（1-5 分）：
1. 忠实度：答案是否完全基于检索文档
2. 相关性：答案是否回应了查询
3. 完整性：答案是否提供了足够的信息

请以 JSON 格式输出：
{{"faithfulness": 1-5, "relevancy": 1-5, "completeness": 1-5, "reasoning": "..."}}"""
```

## LLM-as-Judge 的偏见

### 偏见类型

1. **位置偏见（Position Bias）**：在成对比较中，倾向于选择第一个或第二个
2. **冗长偏见（Verbosity Bias）**：倾向于给更长的答案更高分
3. **自我偏好（Self-Preference）**：倾向于给自己生成的答案更高分
4. **锚定偏见（Anchoring Bias）**：评分受参考答案影响过大
5. **一致性偏见（Consistency Bias）**：对相似输入给出相似评分，即使质量不同

### 偏见检测

```python
async def detect_position_bias(
    judge_llm,
    queries: list[str],
    answer_pairs: list[tuple[str, str]],
    n_trials: int = 10,
) -> float:
    """检测位置偏见"""
    preference_counts = {"first": 0, "second": 0, "tie": 0}

    for query, (answer_a, answer_b) in zip(queries, answer_pairs):
        # 正序比较
        result_ab = await judge_llm.ainvoke(
            f"查询：{query}\n答案A：{answer_a}\n答案B：{answer_b}\n哪个更好？"
        )

        # 反序比较
        result_ba = await judge_llm.ainvoke(
            f"查询：{query}\n答案A：{answer_b}\n答案B：{answer_a}\n哪个更好？"
        )

        # 如果正序选 A 但反序也选 A（实际是 B），说明有位置偏见
        if "A" in result_ab and "A" in result_ba:
            preference_counts["first"] += 1
        elif "B" in result_ab and "B" in result_ba:
            preference_counts["second"] += 1
        else:
            preference_counts["tie"] += 1

    total = sum(preference_counts.values())
    position_bias_rate = (preference_counts["first"] + preference_counts["second"]) / total
    return position_bias_rate
```

## 偏见缓解策略

### 策略一：随机化顺序

```python
import random

async def unbiased_pairwise_comparison(
    judge_llm,
    query: str,
    answer_a: str,
    answer_b: str,
) -> str:
    """无偏见的成对比较"""
    # 随机决定顺序
    if random.random() > 0.5:
        first, second = answer_a, answer_b
        first_label, second_label = "A", "B"
    else:
        first, second = answer_b, answer_a
        first_label, second_label = "B", "A"

    result = await judge_llm.ainvoke(
        f"查询：{query}\n答案1：{first}\n答案2：{second}\n哪个更好？"
    )

    # 映射回原始标签
    if "1" in result:
        return first_label
    elif "2" in result:
        return second_label
    return "tie"
```

### 策略二：多 Judge 投票

```python
async def multi_judge_evaluation(
    judge_llms: list,
    query: str,
    answer: str,
    context: str,
) -> dict:
    """多 Judge 投票评估"""
    scores = {"faithfulness": [], "relevancy": [], "completeness": []}

    for judge in judge_llms:
        result = await judge.ainvoke(JUDGE_PROMPT.format(
            query=query, context=context, answer=answer
        ))
        parsed = json.loads(result)
        for key in scores:
            scores[key].append(parsed.get(key, 3))

    # 取中位数（比平均值更鲁棒）
    return {
        key: sorted(vals)[len(vals) // 2]
        for key, vals in scores.items()
    }
```

### 策略三：校准评分

```python
async def calibrate_judge(
    judge_llm,
    calibration_set: list[dict],  # [{query, answer, human_score}]
) -> dict:
    """校准 Judge 评分"""
    judge_scores = []
    human_scores = []

    for item in calibration_set:
        judge_result = await judge_llm.ainvoke(JUDGE_PROMPT.format(
            query=item["query"],
            context=item.get("context", ""),
            answer=item["answer"],
        ))
        judge_score = json.loads(judge_result).get("faithfulness", 3)
        judge_scores.append(judge_score)
        human_scores.append(item["human_score"])

    # 计算校准映射
    from scipy.stats import linregress
    slope, intercept, r_value, _, _ = linregress(judge_scores, human_scores)

    return {
        "slope": slope,
        "intercept": intercept,
        "correlation": r_value ** 2,
        "calibrate": lambda x: slope * x + intercept,
    }
```

### 策略四：与人工评估对齐

```python
async def human_alignment_check(
    judge_llm,
    test_cases: list[dict],
    human_ratings: list[dict],
    agreement_threshold: float = 0.8,
) -> dict:
    """检查 Judge 与人工评估的一致性"""
    agreements = 0

    for test_case, human in zip(test_cases, human_ratings):
        judge_result = await judge_llm.ainvoke(JUDGE_PROMPT.format(**test_case))
        judge_score = json.loads(judge_result).get("faithfulness", 3)

        # 判断是否一致（差异 <= 1 分）
        if abs(judge_score - human["faithfulness"]) <= 1:
            agreements += 1

    agreement_rate = agreements / len(test_cases)

    return {
        "agreement_rate": agreement_rate,
        "meets_threshold": agreement_rate >= agreement_threshold,
        "recommendation": "可用" if agreement_rate >= agreement_threshold else "需要校准",
    }
```

## Judge 模型选择

| 模型 | 成本 | 延迟 | 一致性 | 推荐 |
|------|------|------|--------|------|
| GPT-4o | 高 | 慢 | 最高 | 高精度场景 |
| DeepSeek-V4-Flash | 低 | 快 | 高 | 生产评估 |
| Qwen3.5-Plus | 中 | 中 | 中 | 通用场景 |
| Qwen3.5-Flash | 极低 | 极快 | 较低 | 快速迭代 |

## 关键事实

1. **LLM-as-Judge 的五种主要偏见**：位置偏见、冗长偏见、自我偏好、锚定偏见、一致性偏见
2. **位置偏见是最常见的偏见**，在成对比较中 Judge 倾向于选择第一个答案，缓解方法是随机化顺序
3. **多 Judge 投票**使用多个 LLM 评估取中位数，比单个 Judge 更鲁棒
4. **校准评分**通过线性回归将 Judge 评分映射到人工评分尺度，提高评分准确性
5. **Aureon 使用 DeepSeek-V4-Flash 作为 Judge 模型**，成本低、延迟快、一致性高，与人工评估一致率 >80%
