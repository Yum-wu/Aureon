# RAG 成本优化：Token 预算与模型路由

## RAG 成本构成

RAG 系统的主要成本来自 LLM 调用，包括：

1. **检索相关 LLM 调用**：HyDE 生成、查询改写、Multi-Query 生成
2. **生成 LLM 调用**：答案生成
3. **评估 LLM 调用**：CRAG 评估、负例检测
4. **Embedding 调用**：查询和文档编码
5. **Rerank 调用**：Cross-Encoder 精排

### 成本分布（典型场景）

| 组件 | 成本占比 | 说明 |
|------|---------|------|
| 答案生成 | 50-60% | 主要成本 |
| HyDE/查询改写 | 10-15% | 复杂查询才有 |
| Rerank | 10-15% | API 调用成本 |
| Embedding | 5-10% | 查询编码 |
| 评估/检测 | 5-10% | CRAG + 负例检测 |

## Token 预算管理

### 预算分配策略

```python
class TokenBudget:
    """Token 预算管理"""

    def __init__(
        self,
        total_budget: int = 4000,
        retrieval_allocation: float = 0.2,
        generation_allocation: float = 0.6,
        evaluation_allocation: float = 0.2,
    ):
        self.total_budget = total_budget
        self.retrieval_budget = int(total_budget * retrieval_allocation)
        self.generation_budget = int(total_budget * generation_allocation)
        self.evaluation_budget = int(total_budget * evaluation_allocation)

    def get_context_limit(self, avg_doc_tokens: int = 200, k: int = 5) -> int:
        """计算可容纳的文档数"""
        # 生成预算 = Prompt 模板 + 上下文 + 答案
        prompt_template_tokens = 100
        answer_reserve = int(self.generation_budget * 0.4)  # 40% 给答案
        context_budget = self.generation_budget - prompt_template_tokens - answer_reserve

        max_docs = context_budget // avg_doc_tokens
        return min(max_docs, k)
```

### 动态上下文长度

根据查询复杂度动态调整上下文长度：

```python
async def dynamic_context_length(
    query: str,
    docs: list,
    llm,
    max_context_tokens: int = 3000,
    min_relevance_score: float = 0.3,
) -> list:
    """动态调整上下文长度"""
    selected_docs = []
    total_tokens = 0

    for doc in docs:
        doc_tokens = len(doc.page_content) // 2  # 粗略估算

        if total_tokens + doc_tokens > max_context_tokens:
            break

        selected_docs.append(doc)
        total_tokens += doc_tokens

    return selected_docs
```

## 模型路由

### 核心思想

不同任务对模型能力的要求不同，使用轻量模型处理简单任务可以显著降低成本：

```python
class ModelRouter:
    """模型路由器"""

    def __init__(self, models: dict[str, dict]):
        self.models = models  # {name: {model, cost_per_1k, capability}}

    def select_model(self, task: str, complexity: str = "medium") -> str:
        """根据任务和复杂度选择模型"""
        if task == "generation":
            if complexity == "simple":
                return "qwen3.5-flash"  # 便宜快速
            elif complexity == "medium":
                return "qwen3.5-plus"   # 平衡
            else:
                return "qwen3.5-max"    # 最强
        elif task == "hyde":
            return "qwen3.5-flash"  # HyDE 不需要强模型
        elif task == "evaluation":
            return "deepseek-v4-flash"  # 评估用便宜模型
        elif task == "negative_detection":
            return "deepseek-v4-flash"  # 负例检测用便宜模型
        else:
            return "qwen3.5-flash"
```

### 成本对比

| 任务 | 强模型成本 | 轻量模型成本 | 节省 |
|------|-----------|-------------|------|
| 答案生成（简单） | ¥0.02/次 | ¥0.002/次 | 90% |
| 答案生成（复杂） | ¥0.02/次 | ¥0.02/次 | 0% |
| HyDE 生成 | ¥0.02/次 | ¥0.002/次 | 90% |
| 查询改写 | ¥0.02/次 | ¥0.002/次 | 90% |
| CRAG 评估 | ¥0.02/次 | ¥0.001/次 | 95% |
| 负例检测 | ¥0.02/次 | ¥0.001/次 | 95% |

## 上下文压缩

### 压缩策略

```python
async def compress_context(
    query: str,
    docs: list,
    llm,
    max_tokens: int = 2000,
) -> list:
    """压缩检索上下文"""
    # 策略 1：截断过长文档
    truncated = []
    for doc in docs:
        if len(doc.page_content) > 500:
            truncated.append(doc.__class__(
                page_content=doc.page_content[:500],
                metadata=doc.metadata,
            ))
        else:
            truncated.append(doc)

    # 策略 2：LLM 压缩（仅当文档过多时）
    total_tokens = sum(len(d.page_content) for d in truncated) // 2
    if total_tokens > max_tokens:
        compressed_context = await llm.ainvoke(
            f"请压缩以下文档，保留与查询'{query}'相关的关键信息：\n\n"
            + "\n\n".join([d.page_content for d in truncated])
        )
        return [truncated[0].__class__(page_content=compressed_context, metadata={})]

    return truncated
```

### Embedding 去重

```python
async def embedding_dedup(
    docs: list,
    embedder,
    similarity_threshold: float = 0.95,
) -> list:
    """基于 Embedding 的文档去重"""
    if not docs:
        return docs

    embeddings = [await embedder.aembed_query(doc.page_content) for doc in docs]

    unique_docs = [docs[0]]
    unique_embeddings = [embeddings[0]]

    for i in range(1, len(docs)):
        is_duplicate = False
        for j, unique_emb in enumerate(unique_embeddings):
            sim = np.dot(embeddings[i], unique_emb) / (
                np.linalg.norm(embeddings[i]) * np.linalg.norm(unique_emb)
            )
            if sim >= similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            unique_docs.append(docs[i])
            unique_embeddings.append(embeddings[i])

    return unique_docs
```

## 成本追踪

```python
class CostTracker:
    """成本追踪器"""

    async def track_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task: str,
    ):
        """追踪 LLM 调用成本"""
        cost = self._calculate_cost(model, input_tokens, output_tokens)
        await self.db.insert({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "task": task,
            "timestamp": datetime.now(),
        })

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """计算调用成本"""
        pricing = {
            "qwen3.5-flash": {"input": 0.0003, "output": 0.0006},
            "qwen3.5-plus": {"input": 0.002, "output": 0.006},
            "qwen3.5-max": {"input": 0.02, "output": 0.06},
            "deepseek-v4-flash": {"input": 0.001, "output": 0.002},
        }

        rates = pricing.get(model, {"input": 0.01, "output": 0.03})
        return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1000
```

## 成本优化效果

### 优化前后对比

| 指标 | 优化前 | 优化后 | 节省 |
|------|--------|--------|------|
| 日均 LLM 成本 | ¥50 | ¥18 | 64% |
| 平均 Token 消耗 | 2500/查询 | 1200/查询 | 52% |
| 简单查询成本 | ¥0.02 | ¥0.003 | 85% |
| 复杂查询成本 | ¥0.05 | ¥0.04 | 20% |

## 关键事实

1. **RAG 成本的主要来源是 LLM 答案生成（50-60%）**，其次是 HyDE/查询改写和 Rerank（各 10-15%）
2. **模型路由是成本优化的核心策略**——简单任务用轻量模型（qwen3.5-flash），复杂任务用强模型（qwen3.5-max），成本可降低 85%
3. **Token 预算管理**通过分配检索/生成/评估的 Token 比例，避免上下文过长浪费 Token
4. **上下文压缩**通过截断、LLM 压缩和 Embedding 去重三种策略，将平均 Token 消耗从 2500 降至 1200
5. **Aureon 的成本优化将日均 LLM 成本从 ¥50 降至 ¥18**，节省 64%，其中模型路由贡献最大
