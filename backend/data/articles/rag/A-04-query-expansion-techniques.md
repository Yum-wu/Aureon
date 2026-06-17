# 查询扩展技术：从伪相关反馈到 LLM 扩展

## 查询扩展的必要性

用户查询通常存在三个核心问题：**表述模糊**、**词汇不匹配**、**信息需求表达不完整**。查询扩展技术通过补充或改写原始查询，弥补这些缺陷，是提升检索召回率的关键手段。

研究表明，约 50% 的检索失败源于查询与文档之间的词汇不匹配问题——用户使用的词汇与文档中出现的词汇不同，但语义相同。

## 伪相关反馈（PRF）

### 基本原理

伪相关反馈（Pseudo-Relevance Feedback，PRF）是最经典的查询扩展方法。其假设是：**初次检索返回的前 k 个文档虽然不完全相关，但包含与查询相关的扩展词**。

### 工作流程

```
原始查询 → 初次检索 → 取前 k 个文档 → 提取扩展词 → 扩展查询 → 二次检索
```

### Rocchio 算法

PRF 的经典实现是 Rocchio 算法，其公式：

```
Q_new = α · Q_original + β · (1/|D_rel|) · Σ D_i - γ · (1/|D_nonrel|) · Σ D_j
```

其中：
- α：原始查询权重
- β：相关文档权重
- γ：不相关文档权重
- D_i：相关文档向量
- D_j：不相关文档向量

```python
def pseudo_relevance_feedback(
    query_vector, initial_results, top_k=3, alpha=1.0, beta=0.75, gamma=0.15
):
    """伪相关反馈扩展查询向量"""
    # 取前 top_k 个结果作为伪相关文档
    relevant_docs = initial_results[:top_k]
    # 取后面的结果作为不相关文档
    non_relevant_docs = initial_results[top_k:top_k*2]

    # 计算相关文档质心
    rel_centroid = np.mean([doc.vector for doc in relevant_docs], axis=0)

    # 计算不相关文档质心
    nonrel_centroid = np.mean(
        [doc.vector for doc in non_relevant_docs], axis=0
    ) if non_relevant_docs else np.zeros_like(query_vector)

    # Rocchio 公式
    expanded_vector = (
        alpha * query_vector
        + beta * rel_centroid
        - gamma * nonrel_centroid
    )

    return expanded_vector
```

### PRF 的局限

1. **噪声引入**：假设前 k 个文档相关，但实际可能不相关
2. **领域漂移**：扩展词可能偏离原始查询意图
3. **参数敏感**：α、β、γ 需要针对不同场景调优
4. **二次检索延迟**：需要两轮检索，延迟翻倍

## LLM 查询扩展

### 核心思想

利用大语言模型的语言理解能力，从语义层面扩展查询。与 PRF 的统计方法不同，LLM 扩展能够理解查询意图并生成语义相关的扩展词。

### 方法一：关键词扩展

让 LLM 为查询生成相关关键词：

```python
keyword_expansion_prompt = """请为以下查询生成 5-10 个相关的搜索关键词或短语，
这些关键词应该出现在与查询相关的文档中。

查询：{query}

相关关键词："""

async def llm_keyword_expansion(query: str, llm) -> list[str]:
    response = await llm.ainvoke(keyword_expansion_prompt.format(query=query))
    keywords = [kw.strip() for kw in response.split(",")]
    expanded_query = query + " " + " ".join(keywords)
    return expanded_query
```

### 方法二：查询改写

让 LLM 将查询改写为更适合检索的表述：

```python
rewrite_prompt = """请将以下查询改写为更适合文档检索的表述。
改写后的查询应该：
1. 更具体、更明确
2. 包含可能出现在相关文档中的专业术语
3. 保持原始查询的核心意图

原始查询：{query}

改写后的查询："""

async def llm_query_rewrite(query: str, llm) -> str:
    return await llm.ainvoke(rewrite_prompt.format(query=query))
```

### 方法三：意图分解

将模糊查询分解为明确的子意图：

```python
intent_decomposition_prompt = """请分析以下查询的可能意图，并为每个意图生成一个明确的子查询。

查询：{query}

请列出 3-5 个子意图及对应的子查询："""

async def intent_decomposition(query: str, llm) -> list[dict]:
    response = await llm.ainvoke(intent_decomposition_prompt.format(query=query))
    # 解析为 [{intent: "...", sub_query: "..."}, ...]
    return parse_intents(response)
```

## 嵌入空间扩展

### 思维链查询扩展

利用 LLM 的推理能力生成思维链，从中提取扩展信息：

```python
cot_expansion_prompt = """请逐步思考以下问题，给出详细的推理过程。

问题：{query}

推理过程："""

async def cot_expansion(query: str, llm, embedder, vectorstore, k: int = 5):
    # 生成思维链
    reasoning = await llm.ainvoke(cot_expansion_prompt.format(query=query))

    # 从思维链中提取关键句子
    key_sentences = extract_key_sentences(reasoning)

    # 分别检索并融合
    all_results = []
    for sentence in key_sentences[:3]:  # 取前 3 个关键句子
        results = await vectorstore.asimilarity_search(sentence, k=k)
        all_results.append(results)

    # 加上原始查询
    original_results = await vectorstore.asimilarity_search(query, k=k)
    all_results.append(original_results)

    return reciprocal_rank_fusion(all_results)[:k]
```

## 各方法对比

| 方法 | 延迟 | 召回提升 | 精度影响 | 成本 | 适用场景 |
|------|------|---------|---------|------|---------|
| PRF | 低（+10ms） | +5-10% | 可能下降 | 无 | 关键词匹配场景 |
| LLM 关键词扩展 | 中（+300ms） | +10-15% | 轻微下降 | ~100 tokens | 通用场景 |
| LLM 查询改写 | 中（+300ms） | +8-12% | 可能提升 | ~150 tokens | 模糊查询 |
| 意图分解 | 中（+400ms） | +15-20% | 轻微下降 | ~200 tokens | 复杂查询 |
| 思维链扩展 | 高（+1s） | +15-25% | 可能下降 | ~500 tokens | 推理型查询 |

## 组合策略

在实际 RAG 系统中，通常组合多种扩展策略：

```python
async def adaptive_query_expansion(
    query: str, query_router, llm, embedder, vectorstore, k: int = 5
):
    route = await query_router.aroute(query)

    if route == "simple":
        # 简单查询：直接检索
        return await vectorstore.asimilarity_search(query, k=k)

    elif route == "medium":
        # 中等查询：LLM 关键词扩展
        expanded = await llm_keyword_expansion(query, llm)
        return await vectorstore.asimilarity_search(expanded, k=k)

    else:
        # 复杂查询：意图分解 + HyDE + Multi-Query
        intents = await intent_decomposition(query, llm)
        all_results = []
        for intent in intents:
            results = await vectorstore.asimilarity_search(
                intent["sub_query"], k=k*2
            )
            all_results.append(results)
        return reciprocal_rank_fusion(all_results)[:k]
```

## 关键事实

1. **约 50% 的检索失败源于词汇不匹配问题**，查询扩展是解决这一问题的核心手段
2. **伪相关反馈（PRF）假设初次检索的前 k 个文档包含扩展词**，通过 Rocchio 算法调整查询向量，但可能引入噪声
3. **LLM 查询扩展从语义层面理解查询意图**，包括关键词扩展、查询改写和意图分解三种主要方法
4. **思维链查询扩展**通过 LLM 推理过程提取关键信息，召回提升最高（+15-25%），但延迟和成本也最高
5. **自适应查询扩展策略**根据查询复杂度选择不同扩展方法，简单查询直接检索，复杂查询组合多种扩展技术
