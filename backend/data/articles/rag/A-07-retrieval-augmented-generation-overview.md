# 检索增强生成：从朴素 RAG 到高级 RAG

## RAG 的演进

检索增强生成（Retrieval-Augmented Generation，RAG）由 Lewis 等人在 2020 年提出，将信息检索与文本生成结合，让 LLM 基于外部知识生成答案。随着实践深入，RAG 从简单的"检索-生成"两步流程，演进为包含查询理解、检索优化、结果评估、自我纠正等环节的复杂系统。

## 朴素 RAG（Naive RAG）

### 架构

朴素 RAG 是最基础的实现：

```
用户查询 → Embedding → 向量检索 → Top-K 文档 → 拼接 Prompt → LLM 生成
```

### 实现示例

```python
async def naive_rag(query: str, embedder, vectorstore, llm, k: int = 5) -> str:
    # 1. 检索
    docs = await vectorstore.asimilarity_search(query, k=k)

    # 2. 拼接上下文
    context = "\n\n".join([doc.page_content for doc in docs])

    # 3. 生成
    prompt = f"""基于以下上下文回答问题。如果上下文中没有相关信息，请说"我不知道"。

上下文：
{context}

问题：{query}

回答："""

    response = await llm.ainvoke(prompt)
    return response
```

### 朴素 RAG 的问题

1. **检索质量不稳定**：简单向量检索可能返回不相关文档
2. **上下文窗口浪费**：不相关文档占用宝贵的 Context Window
3. **无法自我纠正**：检索失败时没有补救机制
4. **幻觉风险**：LLM 可能忽略检索结果，凭"记忆"生成错误答案
5. **缺乏来源追溯**：无法验证答案是否基于检索文档

## 高级 RAG（Advanced RAG）

高级 RAG 在朴素 RAG 的基础上，在三个阶段引入优化：

### 检索前优化（Pre-Retrieval）

1. **查询路由**：根据查询复杂度选择不同检索策略
2. **查询改写**：将模糊查询改写为更明确的表述
3. **HyDE**：生成假设文档提升检索语义匹配
4. **Multi-Query**：多角度查询提升召回率

```python
async def pre_retrieval_optimization(query: str, llm, query_router):
    route = await query_router.aroute(query)

    if route == "simple":
        return {"strategy": "direct", "query": query}
    elif route == "medium":
        rewritten = await llm.ainvoke(f"改写查询：{query}")
        return {"strategy": "rewrite", "query": rewritten}
    else:
        return {"strategy": "hyde_multi", "query": query}
```

### 检索中优化（Retrieval）

1. **Hybrid Search**：dense + sparse 联合检索
2. **RRF 融合**：多路检索结果融合
3. **Rerank**：Cross-Encoder 精排
4. **自适应 Rerank**：高置信度时跳过 Rerank

```python
async def retrieval_optimization(query: str, embedder, vectorstore, reranker, k: int = 5):
    # Hybrid Search
    dense_results = await vectorstore.asimilarity_search(query, k=k*3)
    sparse_results = await sparse_search(query, k=k*3)

    # RRF 融合
    fused = reciprocal_rank_fusion([dense_results, sparse_results])

    # 自适应 Rerank
    if needs_rerank(fused):
        reranked = await reranker.arerank(query, fused, top_k=k)
        return reranked
    return fused[:k]
```

### 检索后优化（Post-Retrieval）

1. **Context Compression**：压缩检索文档，去除冗余
2. **CRAG 自纠正**：评估检索质量，必要时重试
3. **负例检测**：识别无法回答的查询
4. **来源标注**：标注答案的来源文档

```python
async def post_retrieval_optimization(
    query: str, docs, llm, embedder, vectorstore
):
    # CRAG 自纠正
    retrieval_score = evaluate_retrieval_quality(query, docs, embedder)

    if retrieval_score < 0.3:  # 检索质量差
        # 重写查询重试
        rewritten = await rewrite_query(query, llm)
        docs = await vectorstore.asimilarity_search(rewritten, k=10)
    elif retrieval_score < 0.6:  # 检索质量中等
        # 补充检索
        additional = await supplementary_search(query, docs, vectorstore)
        docs = docs + additional

    # Context Compression
    compressed = await compress_context(query, docs, llm)

    return compressed
```

## 模块化 RAG（Modular RAG）

模块化 RAG 将 RAG 流程拆分为可组合的模块，每个模块可以独立优化和替换：

### 核心模块

| 模块 | 职责 | 可选实现 |
|------|------|---------|
| Query Understanding | 查询理解与路由 | 规则路由 / LLM 路由 / Embedding 路由 |
| Retrieval | 文档检索 | Dense / Sparse / Hybrid / Multi-Query |
| Reranking | 结果精排 | Cross-Encoder / ColBERT / LLM Rerank |
| Filtering | 结果过滤 | 相似度阈值 / 负例检测 / PII 过滤 |
| Compression | 上下文压缩 | LLM 压缩 / Embedding 去重 / 摘要 |
| Generation | 答案生成 | 单轮 / 多轮 / 流式 |
| Evaluation | 质量评估 | Faithfulness / Relevancy / 负例检测 |

### Pipeline 配置

```python
class RAGPipeline:
    def __init__(self, config: dict):
        self.query_handler = QueryHandler(config["query"])
        self.retriever = Retriever(config["retrieval"])
        self.reranker = Reranker(config["reranking"]) if config.get("reranking") else None
        self.compressor = Compressor(config["compression"]) if config.get("compression") else None
        self.generator = Generator(config["generation"])
        self.evaluator = Evaluator(config["evaluation"]) if config.get("evaluation") else None

    async def run(self, query: str) -> dict:
        # 查询理解
        query_plan = await self.query_handler.process(query)

        # 检索
        docs = await self.retriever.retrieve(query_plan)

        # Rerank
        if self.reranker:
            docs = await self.reranker.rerank(query, docs)

        # 压缩
        if self.compressor:
            docs = await self.compressor.compress(query, docs)

        # 生成
        answer = await self.generator.generate(query, docs)

        # 评估
        evaluation = None
        if self.evaluator:
            evaluation = await self.evaluator.evaluate(query, docs, answer)

        return {"answer": answer, "docs": docs, "evaluation": evaluation}
```

## Aureon 的 RAG 架构

Aureon 实现了完整的模块化 RAG 架构：

### 查询路由

```
Query → Query Router →
  ├── 简单 → 纯 Sparse（<10ms）
  ├── 中等 → Hybrid + 自适应 Rerank
  └── 复杂 → HyDE + Multi-Query + Hybrid + Ensemble Rerank + CRAG
```

### 关键指标

| 指标 | 值 | 说明 |
|------|-----|------|
| Faithfulness | 0.979 | 答案忠实度 |
| Answer Relevancy | 0.917 | 答案相关性 |
| Hallucination | 0.000 | 幻觉率 |
| TTFT P50 | 610ms | 首 Token 延迟 |
| E2E P50 | 980ms | 端到端延迟 |

## 关键事实

1. **RAG 由 Lewis 等人在 2020 年提出**，将信息检索与文本生成结合，解决了 LLM 知识过时和幻觉问题
2. **朴素 RAG 的核心问题**是检索质量不稳定、无法自我纠正、幻觉风险高，这些是高级 RAG 优化的核心目标
3. **高级 RAG 在检索前、检索中、检索后三个阶段引入优化**，包括查询路由、Hybrid Search、Rerank、CRAG 自纠正等
4. **模块化 RAG 将流程拆分为可组合模块**，每个模块独立优化和替换，支持不同场景的灵活配置
5. **Aureon 的 Adaptive-RAG 查询路由**将查询分为简单/中等/复杂三级，简单查询走纯 Sparse（<10ms），复杂查询走完整 Pipeline（~5s）
