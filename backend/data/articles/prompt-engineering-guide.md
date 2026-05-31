---
title: "Prompt Engineering 实战指南"
slug: "prompt-engineering-guide"
language: "zh"
source: "prompt-engineering-guide.md"
---

# Prompt Engineering 实战指南

## 什么是 Prompt Engineering

Prompt Engineering 是设计和优化输入给 LLM 的提示词，使其输出更准确、更有用的技术。好的 Prompt 是 AI 应用质量的决定性因素——同样的模型，不同的 Prompt 可以产出天壤之别的结果。

核心目标：让 LLM 理解任务意图，按预期格式和质量输出。

## 核心技术

### 1. Few-shot Learning（少样本学习）

在 Prompt 中提供少量示例，引导 LLM 模仿输出格式和风格：

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个情感分析专家，判断用户评论的情感倾向。"),
    ("human", "这个产品质量很好，非常满意"),
    ("assistant", "正面"),
    ("human", "服务太差了，等了一个小时"),
    ("assistant", "负面"),
    ("human", "一般般，没什么特别的"),
    ("assistant", "中性"),
    ("human", "{input}")  # 新输入
])

# Few-shot 效果：LLM 会自动输出 "正面"/"负面"/"中性" 格式的回答
```

**最佳实践**：
- 示例数量：3-5 个即可，过多会浪费 token
- 示例多样性：覆盖正面、负面、中性、边界情况
- 示例一致性：保持输入输出格式统一

### 2. Chain-of-Thought（思维链）

引导 LLM 逐步推理，显著提升复杂问题的回答质量：

```python
# 基础 CoT：加一句 "请一步步思考"
prompt = """请一步步思考并解答以下数学问题：

一个商店有 45 个苹果，卖出了 2/3，又进货了 12 个。现在有多少个苹果？

请展示你的推理过程。"""

# 结构化 CoT
prompt = """请按照以下步骤分析问题：

Step 1: 理解问题 - 明确已知条件和求解目标
Step 2: 分析思路 - 确定解决方法
Step 3: 执行计算 - 逐步计算
Step 4: 验证答案 - 检查结果是否合理

问题：{question}"""
```

**变体**：
- **Zero-shot CoT**：简单加 "Let's think step by step"
- **Few-shot CoT**：提供带推理过程的示例
- **Tree-of-Thought**：探索多个推理路径，选择最优

### 3. ReAct（推理 + 行动）

交替进行推理和工具调用，是 Agent 场景的标准 Prompt 模式：

```python
react_prompt = """Answer the following questions step by step.

You have access to these tools:
{tools}

Use this format:
Thought: <your reasoning about what to do>
Action: <tool name>
Action Input: <input for the tool>
Observation: <tool result will appear here>
... (repeat as needed)
Thought: I now have the answer
Final Answer: <your final answer>

Question: {input}"""
```

### 4. Self-Consistency（自洽性）

多次独立推理，选择出现最多的一致答案：

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0.7)  # 需要一定随机性

def self_consistency(question, n=5):
    """多次采样取多数"""
    answers = []
    for _ in range(n):
        response = llm.invoke(f"请逐步推理并回答：{question}")
        answers.append(extract_answer(response.content))

    # 投票选择最常见的答案
    from collections import Counter
    most_common = Counter(answers).most_common(1)[0]
    return most_common[0], most_common[1] / n  # 答案, 置信度
```

## System Prompt 设计

System Prompt 定义 AI 的角色、能力和行为边界：

```python
system_prompt = """# 角色
你是一个专业的技术文档助手，专注于 AI 和机器学习领域。

# 能力
- 解释技术概念
- 编写代码示例
- 分析和调试代码

# 行为规则
1. 回答时优先使用中文
2. 代码注释使用英文
3. 不确定时明确说"我不确定"
4. 不编造不存在的 API 或库
5. 复杂问题先给结论，再给详细解释

# 输出格式
- 简短问题：直接回答
- 复杂问题：分步骤回答，使用 Markdown 格式
- 代码问题：给出代码 + 解释 + 注意事项
"""
```

**System Prompt 设计原则**：
1. **角色定义清晰**：让 LLM 知道自己是谁
2. **边界明确**：说明能做什么、不能做什么
3. **格式规范**：定义输出格式，便于后处理
4. **优先级排列**：重要规则放在前面

## Prompt 模板

### 动态模板

```python
from langchain_core.prompts import ChatPromptTemplate

# 基础模板
template = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    ("human", "{user_input}")
])

# 多轮对话模板
multi_turn = ChatPromptTemplate.from_messages([
    ("system", "你是{role}"),
    *[
        (msg["role"], msg["content"])
        for msg in chat_history  # 历史消息
    ],
    ("human", "{current_input}")
])

# 带条件的模板
from langchain_core.prompts import MessagesPlaceholder

conditional = ChatPromptTemplate.from_messages([
    ("system", "你是{role}"),
    MessagesPlaceholder("chat_history", optional=True),  # 可选历史
    ("human", "{input}")
])
```

### 模板管理

```python
# 从文件加载模板
from langchain_core.prompts import load_prompt

# prompt.json
# {
#     "type": "chat",
#     "template": [
#         {"role": "system", "template": "{system}"},
#         {"role": "human", "template": "{input}"}
#     ]
# }
prompt = load_prompt("prompt.json")
```

## 结构化输出

确保 LLM 输出可解析的结构化数据：

```python
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 定义输出结构
class ProductReview(BaseModel):
    sentiment: str = Field(description="情感：positive/negative/neutral")
    confidence: float = Field(description="置信度 0-1")
    key_points: list[str] = Field(description="关键要点")
    summary: str = Field(description="一句话总结")

# 使用 with_structured_output 强制结构化输出
llm = ChatOpenAI(model="gpt-4o")
structured_llm = llm.with_structured_output(ProductReview)

prompt = ChatPromptTemplate.from_template(
    "分析以下产品评论：\n\n{review}"
)

chain = prompt | structured_llm
result = chain.invoke({"review": "这个手机拍照效果很好，但电池续航一般"})

# result 是 ProductReview 对象
print(result.sentiment)    # "positive"
print(result.key_points)   # ["拍照效果好", "电池续航一般"]
```

## Prompt 评估

### 手动评估

```python
# 建立评估数据集
eval_dataset = [
    {"input": "什么是 RAG？", "expected": "RAG 是检索增强生成"},
    {"input": "Python 和 Java 的区别", "expected": "Python 是动态类型..."},
]

# 逐一测试并评分
for item in eval_dataset:
    response = chain.invoke({"input": item["input"]})
    print(f"输入: {item['input']}")
    print(f"输出: {response}")
    print(f"期望: {item['expected']}")
    print("---")
```

### 自动评估（LLM-as-Judge）

```python
judge_prompt = """请评估以下 AI 回答的质量。

问题：{question}
AI 回答：{answer}
参考答案：{reference}

从以下维度评分（1-5分）：
1. 准确性：信息是否正确
2. 完整性：是否回答了所有要点
3. 清晰度：表达是否清楚
4. 简洁性：是否避免冗余

请给出总分和每个维度的分数。"""

# 用 LLM 评估 LLM 的输出
judge_llm = ChatOpenAI(model="gpt-4o")
judge_chain = ChatPromptTemplate.from_template(judge_prompt) | judge_llm
```

## 最佳实践

### 通用原则

1. **明确指令**：说清楚要什么，而不是不要什么
2. **提供上下文**：给 LLM 足够的背景信息
3. **约束输出格式**：JSON、Markdown、列表等
4. **迭代优化**：Prompt 是实验驱动的，需要不断测试调整
5. **版本管理**：记录每个 Prompt 的版本和效果

### RAG 场景专用

```python
rag_system_prompt = """你是一个知识问答助手。

规则：
1. 只基于以下参考资料回答
2. 如果参考资料中没有相关信息，明确回答"根据已有资料无法回答"
3. 引用信息时标注来源（如 [来源: xxx]）
4. 不要编造资料中没有的信息
5. 回答要简洁准确

参考资料：
{context}"""
```

### 避免常见陷阱

1. **避免过度约束**：规则太多反而让 LLM 困惑
2. **避免模糊指令**：说"写得好一点"不如说"用专业但友好的语气"
3. **避免过长 Prompt**：超过 4000 token 后效果可能下降
4. **注意注入攻击**：用户输入可能包含恶意 Prompt
5. **测试边界情况**：空输入、超长输入、多语言混合

### 渐进式优化流程

```
1. 基线：写一个最简单的 Prompt，测试基本效果
2. 增强：添加 Few-shot 示例或 CoT 引导
3. 约束：添加格式要求和边界规则
4. 评估：用评估数据集量化效果
5. 迭代：根据评估结果调整 Prompt
6. 部署：A/B 测试验证线上效果
```

Prompt Engineering 是一个持续迭代的过程。每次模型升级后都需要重新评估和优化现有 Prompt，因为不同模型对同一 Prompt 的响应可能差异很大。
