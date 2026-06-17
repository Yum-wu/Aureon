# Adaptive-RAG 查询路由设计

## 查询路由的必要性

不同查询的复杂度差异巨大——"RAG 的全称"只需简单检索，"RAG 与 Fine-tuning 的优劣对比"则需要多角度检索和推理。如果对所有查询都执行完整 Pipeline，简单查询的延迟会不必要地增加；如果对所有查询都简单检索，复杂查询的质量会严重不足。

Adaptive-RAG 由 Jeong 等人在 2024 年提出，通过查询路由根据查询复杂度动态选择检索策略。

## 查询分类体系

### 三级分类

| 级别 | 特征 | 检索策略 | 典型查询 |
|------|------|---------|---------|
| 简单 | 事实型，关键词匹配即可 | 纯 Sparse | "RAG 的全称是什么" |
| 中等 | 分析型，需语义理解 | Hybrid + 自适应 Rerank | "RAG 的核心组件有哪些" |
| 复杂 | 推理型，需多角度分析 | HyDE + Multi-Query + Hybrid + Rerank + CRAG | "RAG 与 Fine-tuning 如何选择" |

## 路由方法

### 方法一：规则路由

基于关键词和查询特征的规则匹配：

```python
class RuleBasedQueryRouter:
    """规则路由器"""

    SIMPLE_KEYWORDS = {"全称", "定义", "是什么", "是什么意思", "who", "what", "when"}
    COMPLEX_KEYWORDS = {"对比", "比较", "优劣", "区别", "如何选择", "为什么", "分析"}

    def route(self, query: str) -> str:
        """路由查询"""
        # 检查关键词
        for kw in self.COMPLEX_KEYWORDS:
            if kw in query:
                return "complex"

        for kw in self.SIMPLE_KEYWORDS:
            if kw in query:
                return "simple"

        # 默认中等
        return "medium"
```

### 方法二：LLM 路由

使用 LLM 判断查询复杂度：

```python
ROUTING_PROMPT = """你是一个查询路由助手。请判断以下查询的复杂度：

- simple：事实型查询，关键词匹配即可回答
- medium：分析型查询，需要语义理解和推理
- complex：推理型查询，需要多角度分析和对比

查询：{query}

复杂度（simple/medium/complex）："""

class LLMQueryRouter:
    """LLM 路由器"""

    def __init__(self, llm):
        self.llm = llm

    async def route(self, query: str) -> str:
        response = await self.llm.ainvoke(ROUTING_PROMPT.format(query=query))
        route = response.strip().lower()
        if route in ("simple", "medium", "complex"):
            return route
        return "medium"  # 默认中等
```

### 方法三：Embedding 路由

使用查询 Embedding 与预定义类别中心的相似度：

```python
class EmbeddingQueryRouter:
    """Embedding 路由器"""

    def __init__(self, embedder, category_centers: dict[str, np.ndarray]):
        self.embedder = embedder
        self.category_centers = category_centers  # {category: center_vector}

    async def route(self, query: str) -> str:
        query_embedding = await self.embedder.aembed_query(query)

        best_category = "medium"
        best_sim = -1

        for category, center in self.category_centers.items():
            sim = np.dot(query_embedding, center) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(center)
            )
            if sim > best_sim:
                best_sim = sim
                best_category = category

        return best_category
```

### 方法四：分类器路由

训练轻量分类器：

```python
from sklearn.linear_model import LogisticRegression

class ClassifierQueryRouter:
    """分类器路由器"""

    def __init__(self, embedder, classifier: LogisticRegression):
        self.embedder = embedder
        self.classifier = classifier

    async def route(self, query: str) -> str:
        query_embedding = await self.embedder.aembed_query(query)
        prediction = self.classifier.predict([query_embedding])[0]
        return prediction

    @classmethod
    def train(cls, embedder, training_data: list[tuple[str, str]]):
        """训练分类器

        Args:
            training_data: [(query, category), ...]
        """
        import asyncio

        # 编码训练数据
        queries, categories = zip(*training_data)
        embeddings = asyncio.get_event_loop().run_until_complete(
            embedder.aembed_documents(list(queries))
        )

        # 训练分类器
        classifier = LogisticRegression(max_iter=1000)
        classifier.fit(embeddings, categories)

        return cls(embedder, classifier)
```

## Adaptive-RAG Pipeline

### 完整实现

```python
class AdaptiveRAGPipeline:
    """Adaptive-RAG 查询路由 Pipeline"""

    def __init__(
        self,
        router,
        embedder,
        vectorstore,
        sparse_search_fn,
        reranker,
        llm,
    ):
        self.router = router
        self.embedder = embedder
        self.vectorstore = vectorstore
        self.sparse_search_fn = sparse_search_fn
        self.reranker = reranker
        self.llm = llm

    async def run(self, query: str, k: int = 5) -> dict:
        """执行 Adaptive-RAG"""
        # 1. 查询路由
        route = await self.router.route(query)

        # 2. 根据路由选择检索策略
        if route == "simple":
            result = await self._simple_retrieve(query, k)
        elif route == "medium":
            result = await self._medium_retrieve(query, k)
        else:
            result = await self._complex_retrieve(query, k)

        result["route"] = route
        return result

    async def _simple_retrieve(self, query: str, k: int) -> dict:
        """简单查询：纯 Sparse 检索"""
        docs = await self.sparse_search_fn(query, k=k)
        answer = await self._generate(query, docs)
        return {"answer": answer, "docs": docs}

    async def _medium_retrieve(self, query: str, k: int) -> dict:
        """中等查询：Hybrid + 自适应 Rerank"""
        # Hybrid Search
        dense_results = await self.vectorstore.asimilarity_search(query, k=k*3)
        sparse_results = await self.sparse_search_fn(query, k=k*3)
        fused = reciprocal_rank_fusion([dense_results, sparse_results])

        # 自适应 Rerank
        if self._needs_rerank(fused):
            docs = await self.reranker.arerank(query, fused, top_k=k)
        else:
            docs = fused[:k]

        answer = await self._generate(query, docs)
        return {"answer": answer, "docs": docs}

    async def _complex_retrieve(self, query: str, k: int) -> dict:
        """复杂查询：HyDE + Multi-Query + Hybrid + Rerank + CRAG"""
        # HyDE
        hypothetical_doc = await self._generate_hypothetical(query)
        hyde_results = await self.vectorstore.asimilarity_search(hypothetical_doc, k=k*2)

        # Multi-Query
        sub_queries = await self._generate_sub_queries(query)
        multi_results = []
        for sq in sub_queries:
            results = await self.vectorstore.asimilarity_search(sq, k=k*2)
            multi_results.append(results)

        # Hybrid Search
        sparse_results = await self.sparse_search_fn(query, k=k*2)

        # RRF 融合所有结果
        all_results = [hyde_results, sparse_results] + multi_results
        fused = reciprocal_rank_fusion(all_results)

        # Rerank
        docs = await self.reranker.arerank(query, fused, top_k=k*2)

        # CRAG 评估
        evaluation = await self._crag_evaluate(query, docs)
        if evaluation == "incorrect":
            return {"answer": "无法找到相关信息", "docs": []}
        elif evaluation == "ambiguous":
            # 重写查询重试
            rewritten = await self._rewrite_query(query)
            docs = await self.vectorstore.asimilarity_search(rewritten, k=k)

        answer = await self._generate(query, docs[:k])
        return {"answer": answer, "docs": docs[:k]}
```

## 路由方法对比

| 方法 | 延迟 | 准确率 | 成本 | 可维护性 |
|------|------|--------|------|---------|
| 规则路由 | <1ms | 70-80% | 无 | 低（规则硬编码） |
| LLM 路由 | 200-500ms | 85-90% | ~100 tokens | 中 |
| Embedding 路由 | 10-20ms | 75-85% | 1 次 Embedding | 高（需训练） |
| 分类器路由 | 5-10ms | 80-88% | 1 次 Embedding | 高（需训练） |

## Aureon 的路由配置

Aureon 使用 LLM 路由 + 规则路由的混合方案：

- **快速路径**：关键词匹配直接路由（<1ms）
- **LLM 路由**：关键词未匹配时调用轻量 LLM（~300ms）
- **路由阈值**：`SIMPLE_THRESHOLD` 和 `COMPLEX_THRESHOLD` 控制路由决策

### 实测路由分布

| 路由 | 占比 | 平均延迟 |
|------|------|---------|
| 简单 | 30% | 8ms |
| 中等 | 45% | 50ms |
| 复杂 | 25% | 3-5s |

## 关键事实

1. **Adaptive-RAG 由 Jeong 等人在 2024 年提出**，根据查询复杂度动态选择检索策略，避免过度检索或检索不足
2. **三级分类体系**：简单（事实型，纯 Sparse）、中等（分析型，Hybrid+Rerank）、复杂（推理型，完整 Pipeline）
3. **四种路由方法**：规则路由（<1ms，准确率 70-80%）、LLM 路由（~300ms，85-90%）、Embedding 路由（~15ms，75-85%）、分类器路由（~8ms，80-88%）
4. **Aureon 使用 LLM + 规则混合路由**，关键词匹配快速路径 + LLM 语义路由，平均路由延迟 <50ms
5. **路由分布中约 30% 为简单查询、45% 为中等、25% 为复杂**，路由后平均延迟从 3s 降至 1.5s
