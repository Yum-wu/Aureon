# CRAG 自纠正检索增强生成

## CRAG 的动机

传统 RAG 系统假设检索结果总是相关的，直接将检索文档送入 LLM 生成答案。但现实中检索结果可能不相关、不完整或包含噪声。CRAG（Corrective RAG）由 Yan 等人在 2024 年提出，核心思想是：**在生成前评估检索质量，必要时进行纠正**。

## CRAG 架构

### 三路动作

CRAG 根据检索质量评估结果，执行三种动作：

```
查询 → 检索 → 质量评估 →
  ├── Correct（正确）→ 直接生成
  ├── Ambiguous（模糊）→ 查询改写 + 重新检索 + 生成
  └── Incorrect（错误）→ 返回"无法回答"或使用 Web 搜索
```

### 质量评估方法

#### LLM 评估

使用 LLM 判断检索文档是否与查询相关：

```python
EVALUATION_PROMPT = """请评估以下检索文档是否与查询相关。

查询：{query}

文档：
{documents}

请判断：
- "correct"：文档与查询高度相关
- "ambiguous"：文档与查询部分相关，但信息不完整
- "incorrect"：文档与查询不相关

判断："""

async def llm_evaluate_retrieval(query: str, docs: list, llm) -> str:
    """LLM 评估检索质量"""
    doc_text = "\n\n".join([f"文档{i+1}: {doc.page_content}" for i, doc in enumerate(docs)])
    response = await llm.ainvoke(EVALUATION_PROMPT.format(query=query, documents=doc_text))
    return response.strip().lower()
```

#### Embedding 相似度评估（轻量 CRAG）

Aureon 采用基于 Embedding 相似度的快速评估，避免 LLM 调用延迟：

```python
import numpy as np

async def embedding_evaluate_retrieval(
    query: str,
    docs: list,
    embedder,
    correct_threshold: float = 0.7,
    incorrect_threshold: float = 0.3,
) -> str:
    """基于 Embedding 相似度的检索质量评估"""
    query_embedding = await embedder.aembed_query(query)

    # 计算查询与每个文档的相似度
    similarities = []
    for doc in docs:
        doc_embedding = await embedder.aembed_query(doc.page_content)
        sim = np.dot(query_embedding, doc_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
        )
        similarities.append(sim)

    # 取 Top-1 相似度作为评估指标
    max_sim = max(similarities) if similarities else 0

    if max_sim >= correct_threshold:
        return "correct"
    elif max_sim >= incorrect_threshold:
        return "ambiguous"
    else:
        return "incorrect"
```

## CRAG 实现详解

### 完整 CRAG Pipeline

```python
class CorrectiveRAG:
    """CRAG 自纠正检索增强生成"""

    def __init__(
        self,
        embedder,
        vectorstore,
        llm,
        correct_threshold: float = 0.7,
        ambiguous_threshold: float = 0.3,
        max_retries: int = 2,
    ):
        self.embedder = embedder
        self.vectorstore = vectorstore
        self.llm = llm
        self.correct_threshold = correct_threshold
        self.ambiguous_threshold = ambiguous_threshold
        self.max_retries = max_retries

    async def run(self, query: str, k: int = 5) -> dict:
        """执行 CRAG Pipeline"""
        # 1. 初始检索
        docs = await self.vectorstore.asimilarity_search(query, k=k)

        # 2. 质量评估
        evaluation = await self._evaluate(query, docs)

        # 3. 根据评估结果执行动作
        if evaluation == "correct":
            # 直接生成
            answer = await self._generate(query, docs)
            return {"answer": answer, "action": "correct", "docs": docs}

        elif evaluation == "ambiguous":
            # 查询改写 + 重新检索
            for attempt in range(self.max_retries):
                rewritten = await self._rewrite_query(query, docs)
                new_docs = await self.vectorstore.asimilarity_search(rewritten, k=k)

                # 合并新旧文档
                merged_docs = self._merge_docs(docs, new_docs)

                # 重新评估
                new_evaluation = await self._evaluate(query, merged_docs)
                if new_evaluation == "correct":
                    answer = await self._generate(query, merged_docs)
                    return {"answer": answer, "action": "ambiguous_retry", "docs": merged_docs}

                docs = merged_docs

            # 重试后仍模糊，用当前文档生成
            answer = await self._generate(query, docs)
            return {"answer": answer, "action": "ambiguous_fallback", "docs": docs}

        else:  # incorrect
            # 返回无法回答
            return {"answer": "抱歉，我无法找到相关信息来回答您的问题。", "action": "incorrect", "docs": []}

    async def _evaluate(self, query: str, docs: list) -> str:
        """评估检索质量"""
        return await embedding_evaluate_retrieval(
            query, docs, self.embedder,
            self.correct_threshold, self.ambiguous_threshold,
        )

    async def _rewrite_query(self, query: str, docs: list) -> str:
        """改写查询"""
        rewrite_prompt = """原始查询未能检索到足够相关的文档。请改写查询以获取更相关的结果。

原始查询：{query}

请改写查询："""
        return await self.llm.ainvoke(rewrite_prompt.format(query=query))

    async def _generate(self, query: str, docs: list) -> str:
        """生成答案"""
        context = "\n\n".join([doc.page_content for doc in docs])
        prompt = f"""基于以下上下文回答问题。

上下文：
{context}

问题：{query}

回答："""
        return await self.llm.ainvoke(prompt)

    def _merge_docs(self, old_docs: list, new_docs: list) -> list:
        """合并新旧文档，去重"""
        seen = set()
        merged = []
        for doc in old_docs + new_docs:
            doc_id = hash(doc.page_content)
            if doc_id not in seen:
                seen.add(doc_id)
                merged.append(doc)
        return merged
```

## 轻量 CRAG 优化

### 跳过冗余步骤

在 Aureon 的实现中，轻量 CRAG 进行了以下优化：

1. **高置信度跳过**：Top-1 相似度 > 0.8 时直接生成，跳过评估
2. **复用查询 Embedding**：检索时已计算查询 Embedding，评估时复用
3. **单次重试**：模糊查询最多重试 1 次，避免延迟累积

```python
async def lightweight_crag(
    query: str,
    query_embedding: np.ndarray,  # 复用检索时的 Embedding
    docs: list,
    doc_embeddings: list[np.ndarray],  # 复用检索时的文档 Embedding
    llm,
    vectorstore,
    high_score_skip_threshold: float = 0.8,
    correct_threshold: float = 0.5,
) -> dict:
    """轻量 CRAG：复用 Embedding，高置信度跳过"""
    # 计算相似度（复用已有 Embedding）
    similarities = [
        np.dot(query_embedding, doc_emb) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(doc_emb)
        )
        for doc_emb in doc_embeddings
    ]
    max_sim = max(similarities) if similarities else 0

    # 高置信度跳过
    if max_sim > high_score_skip_threshold:
        answer = await generate(query, docs)
        return {"answer": answer, "action": "skip_crag"}

    # CRAG 评估
    if max_sim >= correct_threshold:
        answer = await generate(query, docs)
        return {"answer": answer, "action": "correct"}
    else:
        # 单次重试
        rewritten = await rewrite_query(query, llm)
        new_docs = await vectorstore.asimilarity_search(rewritten, k=5)
        answer = await generate(query, docs + new_docs)
        return {"answer": answer, "action": "retry"}
```

### 延迟对比

| 方法 | 延迟 | 精度 |
|------|------|------|
| 无 CRAG | 800ms | 基准 |
| LLM CRAG | 1800ms | +5% |
| 轻量 CRAG | 850ms | +3% |
| 轻量 CRAG + 跳过 | 820ms | +2% |

轻量 CRAG 的评估延迟仅约 50ms（vs LLM CRAG 的 ~1s），且高置信度跳过进一步减少不必要的评估。

## CRAG 与负例检测

CRAG 的 "incorrect" 判断与负例检测有重叠，但侧重点不同：

- **CRAG**：关注检索质量，判断检索结果是否足够回答查询
- **负例检测**：关注查询本身，判断系统是否有能力回答查询

在 Aureon 中，两者配合使用：

```
查询 → 负例检测 →
  ├── 是负例 → 直接拒绝
  └── 非负例 → 检索 → CRAG 评估 → 生成
```

## 关键事实

1. **CRAG 由 Yan 等人在 2024 年提出**，核心思想是在生成前评估检索质量，必要时进行纠正
2. **CRAG 的三路动作**：correct（直接生成）、ambiguous（查询改写+重新检索）、incorrect（返回无法回答）
3. **轻量 CRAG 使用 Embedding 相似度替代 LLM 评估**，延迟从 ~1s 降至 ~50ms，精度损失约 2%
4. **高置信度跳过（high_score_skip_threshold=0.1）**在 Aureon 中约 30% 的查询可以跳过 CRAG 评估
5. **CRAG 与负例检测配合使用**：负例检测判断查询是否可回答，CRAG 判断检索结果是否足够，两者互补
