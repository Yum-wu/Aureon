# Self-RAG：学习检索-生成-批评

## Self-RAG 的动机

传统 RAG 系统的检索和生成是分离的——无论是否需要检索，都会执行检索步骤；无论生成结果是否正确，都不会自我检查。Self-RAG 由 Asai 等人在 2023 年提出，让模型学会**自主决定何时检索、何时生成、何时批评**。

## Self-RAG 的核心机制

### 三种反思 Token

Self-RAG 引入三种特殊的反思 Token（Reflection Tokens），让模型在生成过程中自我评估：

1. **Retrieve Token**：`[Retrieve]` / `[No Retrieve]` — 是否需要检索
2. **IsRel Token**：`[IsRel]` / `[NoIsRel]` — 检索结果是否相关
3. **IsSup Token**：`[IsSup]` / `[NoIsSup]` — 生成内容是否有检索结果支持
4. **IsUse Token**：`[IsUse]` / `[NoIsUse]` — 生成内容是否有用

### 工作流程

```
输入查询 →
  1. 模型判断 [Retrieve/No Retrieve]
     ├── [No Retrieve] → 直接生成
     └── [Retrieve] → 检索文档
  2. 模型判断 [IsRel/NoIsRel]
     ├── [NoIsRel] → 丢弃文档，重新检索或直接生成
     └── [IsRel] → 基于文档生成
  3. 模型判断 [IsSup/NoIsSup]
     ├── [NoIsSup] → 标记为无支持，可能重新生成
     └── [IsSup] → 继续生成
  4. 模型判断 [IsUse/NoIsUse]
     ├── [NoIsUse] → 重新生成
     └── [IsUse] → 输出最终答案
```

## Self-RAG 实现

### 训练阶段

Self-RAG 需要在包含反思 Token 的数据上微调 LLM：

```python
# 训练数据格式
# 输入：查询 + 检索文档
# 输出：反思 Token + 生成内容

training_example = {
    "input": "什么是 RAG？",
    "output": "[Retrieve] [IsRel] RAG 是检索增强生成技术，由 Lewis 等人在 2020 年提出。[IsSup] [IsUse]"
}

# 对于不需要检索的查询
training_example_no_retrieve = {
    "input": "1+1等于几？",
    "output": "[No Retrieve] 1+1等于2。[IsUse]"
}
```

### 推理阶段

```python
class SelfRAG:
    """Self-RAG 实现"""

    def __init__(self, llm, retriever, max_retries: int = 2):
        self.llm = llm
        self.retriever = retriever
        self.max_retries = max_retries

    async def generate(self, query: str) -> dict:
        """Self-RAG 生成"""
        # 步骤 1：判断是否需要检索
        need_retrieve = await self._should_retrieve(query)

        if not need_retrieve:
            # 直接生成
            answer = await self._direct_generate(query)
            return {"answer": answer, "retrieved": False}

        # 步骤 2：检索
        docs = await self.retriever.aretrieve(query, k=5)

        # 步骤 3：评估检索相关性
        relevant_docs = await self._filter_relevant(query, docs)

        if not relevant_docs:
            # 无相关文档，直接生成
            answer = await self._direct_generate(query)
            return {"answer": answer, "retrieved": True, "relevant_docs": 0}

        # 步骤 4：基于文档生成
        answer = await self._generate_with_docs(query, relevant_docs)

        # 步骤 5：自我批评
        is_supported = await self._check_support(query, answer, relevant_docs)
        is_useful = await self._check_usefulness(query, answer)

        if not is_supported or not is_useful:
            # 重新生成
            for _ in range(self.max_retries):
                answer = await self._generate_with_docs(query, relevant_docs)
                is_supported = await self._check_support(query, answer, relevant_docs)
                is_useful = await self._check_usefulness(query, answer)
                if is_supported and is_useful:
                    break

        return {
            "answer": answer,
            "retrieved": True,
            "relevant_docs": len(relevant_docs),
            "is_supported": is_supported,
            "is_useful": is_useful,
        }

    async def _should_retrieve(self, query: str) -> bool:
        """判断是否需要检索"""
        prompt = f"""判断以下查询是否需要检索外部知识来回答。
如果查询涉及事实性知识、最新信息或专业领域，需要检索。
如果查询是常识、数学计算或个人观点，不需要检索。

查询：{query}

回答 [Retrieve] 或 [No Retrieve]："""
        response = await self.llm.ainvoke(prompt)
        return "[retrieve]" in response.lower()

    async def _filter_relevant(self, query: str, docs: list) -> list:
        """过滤相关文档"""
        relevant = []
        for doc in docs:
            prompt = f"""判断以下文档是否与查询相关。

查询：{query}
文档：{doc.page_content[:500]}

回答 [IsRel] 或 [NoIsRel]："""
            response = await self.llm.ainvoke(prompt)
            if "[isrel]" in response.lower():
                relevant.append(doc)
        return relevant

    async def _check_support(self, query: str, answer: str, docs: list) -> bool:
        """检查答案是否有文档支持"""
        context = "\n".join([doc.page_content[:300] for doc in docs])
        prompt = f"""判断以下答案是否有上下文支持。

上下文：{context}
答案：{answer}

回答 [IsSup] 或 [NoIsSup]："""
        response = await self.llm.ainvoke(prompt)
        return "[issup]" in response.lower()

    async def _check_usefulness(self, query: str, answer: str) -> bool:
        """检查答案是否有用"""
        prompt = f"""判断以下答案对查询是否有用。

查询：{query}
答案：{answer}

回答 [IsUse] 或 [NoIsUse]："""
        response = await self.llm.ainvoke(prompt)
        return "[isuse]" in response.lower()
```

## Self-RAG vs CRAG

| 维度 | Self-RAG | CRAG |
|------|----------|------|
| 检索决策 | 模型自主决定 | 总是检索 |
| 评估方式 | 生成后自我批评 | 生成前评估检索质量 |
| 支持度检查 | 有（IsSup） | 无 |
| 有用性检查 | 有（IsUse） | 无 |
| 实现复杂度 | 高（需微调模型） | 低（即插即用） |
| 额外延迟 | 高（多次 LLM 调用） | 低（轻量评估） |
| 适用场景 | 高精度要求 | 通用场景 |

## 实践建议

### 简化版 Self-RAG

完整 Self-RAG 需要微调模型，成本较高。实践中可以采用简化版：

```python
class SimplifiedSelfRAG:
    """简化版 Self-RAG：无需微调"""

    async def generate(self, query: str, retriever, llm) -> dict:
        # 1. 检索（总是执行，避免判断延迟）
        docs = await retriever.aretrieve(query, k=5)

        # 2. 生成
        answer = await self._generate(query, docs, llm)

        # 3. 自我批评（仅 Faithfulness 检查）
        faithfulness = await self._check_faithfulness(query, answer, docs, llm)

        if faithfulness < 0.5:
            # 重新生成，强调基于文档
            answer = await self._generate_strict(query, docs, llm)

        return {"answer": answer, "faithfulness": faithfulness}
```

## 关键事实

1. **Self-RAG 由 Asai 等人在 2023 年提出**，引入反思 Token 让模型自主决定何时检索、评估检索相关性、检查生成支持度和有用性
2. **Self-RAG 的四种反思 Token**：Retrieve/No Retrieve、IsRel/NoIsRel、IsSup/NoIsSup、IsUse/NoIsUse
3. **Self-RAG 需要在包含反思 Token 的数据上微调 LLM**，实现成本高，但能实现更精细的自我评估
4. **CRAG 侧重生成前评估检索质量**，Self-RAG 侧重生成后自我批评，两者可以互补
5. **简化版 Self-RAG 无需微调**，通过 LLM Prompt 实现检索决策和 Faithfulness 检查，成本更低但精度略低
