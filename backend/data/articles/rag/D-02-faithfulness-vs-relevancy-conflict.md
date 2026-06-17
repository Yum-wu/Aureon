# Faithfulness vs Relevancy：当指标冲突时怎么办

## 指标冲突的场景

在 RAG 评估中，Faithfulness（忠实度）和 Answer Relevancy（答案相关性）有时会冲突：

1. **高 Faithfulness + 低 Relevancy**：答案完全基于检索文档，但没有回答用户的问题
2. **低 Faithfulness + 高 Relevancy**：答案回应了用户查询，但编造了检索文档中没有的信息
3. **高 Faithfulness + 高 Relevancy**：理想状态

### 具体案例

**案例 1：高 Faithfulness + 低 Relevancy**

```
查询：RAG 的优势是什么？
检索文档：RAG 由 Lewis 等人在 2020 年提出，结合了检索和生成...
答案：RAG 是 2020 年由 Lewis 提出的技术，结合了检索和生成。
评估：Faithfulness=1.0（完全基于文档），Relevancy=0.3（没有回答优势）
```

**案例 2：低 Faithfulness + 高 Relevancy**

```
查询：RAG 的优势是什么？
检索文档：RAG 由 Lewis 等人在 2020 年提出...
答案：RAG 的优势包括减少幻觉、知识可更新、成本低于微调。
评估：Faithfulness=0.2（大部分信息不在文档中），Relevancy=0.9（直接回答了优势）
```

## 冲突根因分析

### 根因一：检索不足

检索到的文档不包含回答查询所需的信息，LLM 被迫"编造"来回答：

```
解决方向：改进检索策略
- 增加 Multi-Query 扩展查询
- 降低相似度阈值获取更多候选
- 补充知识库内容
```

### 根因二：检索噪声

检索到的文档包含大量不相关信息，LLM 被噪声干扰：

```
解决方向：改进过滤策略
- 加强 Rerank 精排
- Context Compression 去除噪声
- 提高相似度阈值
```

### 根因三：Prompt 设计问题

Prompt 没有明确要求 LLM 仅基于检索文档回答：

```
解决方向：优化 Prompt
- 明确要求"仅基于以下上下文回答"
- 添加"如果上下文中没有相关信息，请说'我不知道'"
- 使用 XML 标签隔离上下文
```

## 冲突解决策略

### 策略一：Faithfulness 优先

在大多数场景下，Faithfulness 应优先于 Relevancy：

```python
FAITHFULNESS_FIRST_PROMPT = """基于以下上下文回答问题。

重要规则：
1. 仅使用上下文中包含的信息
2. 如果上下文中没有足够信息回答问题，请说"根据现有信息，我无法完全回答这个问题"
3. 不要编造上下文中没有的信息

上下文：
{context}

问题：{query}

回答："""
```

**理由**：幻觉（低 Faithfulness）比不完整回答（低 Relevancy）危害更大。用户可以追问获取更多信息，但错误信息可能被信任。

### 策略二：分场景权衡

不同场景对 Faithfulness 和 Relevancy 的要求不同：

| 场景 | Faithfulness 权重 | Relevancy 权重 | 理由 |
|------|-------------------|----------------|------|
| 医疗咨询 | 0.8 | 0.2 | 错误信息可能致命 |
| 客服问答 | 0.6 | 0.4 | 需要回答用户问题 |
| 创意写作 | 0.3 | 0.7 | 创造性更重要 |
| 法律咨询 | 0.9 | 0.1 | 必须基于法律条文 |

### 策略三：置信度标注

让 LLM 标注答案中每部分的置信度：

```python
CONFIDENCE_PROMPT = """基于以下上下文回答问题，并为答案中的每个声明标注置信度。

置信度定义：
- [高]：直接来自上下文的信息
- [中]：从上下文推断的信息
- [低]：基于常识但上下文中未提及的信息

上下文：
{context}

问题：{query}

请用以下格式回答：
声明1 [置信度]：...
声明2 [置信度]：...
..."""

# 示例输出：
# RAG 由 Lewis 等人在 2020 年提出 [高]
# RAG 的优势包括减少幻觉 [中]
# RAG 通常比微调更便宜 [低]
```

### 策略四：检索增强

当 Faithfulness 低时，补充检索更多相关文档：

```python
async def faithfulness_aware_generation(
    query: str,
    docs: list,
    llm,
    embedder,
    vectorstore,
    faithfulness_threshold: float = 0.7,
) -> dict:
    """Faithfulness 感知的生成"""
    # 第一次生成
    answer = await generate(query, docs, llm)

    # 评估 Faithfulness
    faithfulness = await evaluate_faithfulness(query, answer, docs, llm)

    if faithfulness >= faithfulness_threshold:
        return {"answer": answer, "faithfulness": faithfulness}

    # Faithfulness 低，补充检索
    additional_docs = await supplementary_search(query, docs, vectorstore)
    merged_docs = docs + additional_docs

    # 重新生成
    answer = await generate(query, merged_docs, llm)
    faithfulness = await evaluate_faithfulness(query, answer, merged_docs, llm)

    return {"answer": answer, "faithfulness": faithfulness}
```

## 监控与告警

### 指标冲突监控

```python
class MetricConflictMonitor:
    """指标冲突监控"""

    async def check_conflict(self, metrics: dict) -> dict | None:
        """检查指标冲突"""
        faithfulness = metrics.get("faithfulness", 1.0)
        relevancy = metrics.get("answer_relevancy", 1.0)

        # 冲突判断
        if faithfulness > 0.8 and relevancy < 0.5:
            return {
                "conflict_type": "high_faith_low_relev",
                "description": "答案忠实但不相关，可能是检索不足",
                "suggestion": "增加检索范围或补充知识库",
            }
        elif faithfulness < 0.5 and relevancy > 0.8:
            return {
                "conflict_type": "low_faith_high_relev",
                "description": "答案相关但不忠实，可能存在幻觉",
                "suggestion": "加强 Prompt 约束或补充检索",
            }

        return None
```

## 关键事实

1. **Faithfulness 和 Relevancy 冲突的两种典型模式**：高忠实低相关（检索不足）、低忠实高相关（幻觉风险）
2. **在大多数场景下 Faithfulness 应优先于 Relevancy**，因为幻觉比不完整回答危害更大
3. **冲突的三大根因**：检索不足（文档不包含答案）、检索噪声（不相关文档干扰）、Prompt 设计问题
4. **置信度标注**让 LLM 为每个声明标注来源置信度（高/中/低），帮助用户判断信息可靠性
5. **Faithfulness 感知生成**在 Faithfulness 低时自动补充检索，Aureon 中此策略将 Faithfulness 从 0.85 提升到 0.979
