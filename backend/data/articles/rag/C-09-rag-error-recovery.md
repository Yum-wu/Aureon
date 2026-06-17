# RAG 错误恢复：检索失败时的降级策略

## 检索失败的类型

RAG 系统在运行过程中可能遇到多种故障：

1. **向量库不可用**：Qdrant 宕机、网络超时
2. **Embedding 服务不可用**：API 限流、模型加载失败
3. **Rerank 服务不可用**：API 超时、额度用尽
4. **LLM 服务不可用**：API 限流、模型过载
5. **检索结果为空**：查询与所有文档都不相关
6. **检索结果质量差**：返回的文档与查询不相关

## 降级策略设计

### 策略一：服务降级链

每个服务都有降级替代方案：

```python
class ResilientRAGPipeline:
    """容错 RAG Pipeline"""

    async def embed(self, text: str) -> list[float]:
        """Embedding 降级链"""
        # 主服务：本地模型
        try:
            return await self.local_embedder.aembed_query(text)
        except Exception:
            pass

        # 降级 1：DashScope API
        try:
            return await self.dashscope_embedder.aembed_query(text)
        except Exception:
            pass

        # 降级 2：SiliconFlow API
        try:
            return await self.siliconflow_embedder.aembed_query(text)
        except Exception:
            pass

        # 降级 3：OpenAI API
        try:
            return await self.openai_embedder.aembed_query(text)
        except Exception:
            pass

        raise RuntimeError("所有 Embedding 服务不可用")

    async def retrieve(self, query: str, k: int = 5) -> list:
        """检索降级链"""
        # 主服务：Hybrid Search
        try:
            return await self.hybrid_search(query, k)
        except Exception:
            pass

        # 降级 1：仅 Dense 检索
        try:
            return await self.dense_search(query, k)
        except Exception:
            pass

        # 降级 2：仅 Sparse 检索
        try:
            return await self.sparse_search(query, k)
        except Exception:
            pass

        # 降级 3：关键词匹配
        try:
            return await self.keyword_search(query, k)
        except Exception:
            pass

        return []  # 所有检索方式失败

    async def rerank(self, query: str, docs: list, k: int = 5) -> list:
        """Rerank 降级链"""
        # 主服务：DashScope Rerank
        try:
            return await self.dashscope_reranker.arerank(query, docs, top_k=k)
        except Exception:
            pass

        # 降级 1：跳过 Rerank，直接返回
        return docs[:k]

    async def generate(self, query: str, docs: list) -> str:
        """生成降级链"""
        # 主服务：主力 LLM
        try:
            return await self.primary_llm.ainvoke(query, docs)
        except Exception:
            pass

        # 降级 1：备用 LLM
        try:
            return await self.fallback_llm.ainvoke(query, docs)
        except Exception:
            pass

        # 降级 2：返回检索结果摘要
        if docs:
            return "以下是与您查询相关的信息：\n" + "\n".join([d.page_content[:200] for d in docs[:3]])

        return "抱歉，服务暂时不可用，请稍后重试。"
```

### 策略二：熔断器模式

当某个服务连续失败时，暂时跳过该服务：

```python
class CircuitBreaker:
    """熔断器"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self.state = "closed"  # closed / open / half_open
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_count = 0

    def can_execute(self) -> bool:
        """是否可以执行请求"""
        if self.state == "closed":
            return True
        elif self.state == "open":
            # 检查是否可以进入半开状态
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
                self.half_open_count = 0
                return True
            return False
        else:  # half_open
            return self.half_open_count < self.half_open_max

    def record_success(self):
        """记录成功"""
        if self.state == "half_open":
            self.state = "closed"
        self.failure_count = 0

    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "half_open":
            self.state = "open"
        elif self.failure_count >= self.failure_threshold:
            self.state = "open"


class ResilientService:
    """带熔断器的服务"""

    def __init__(self, service_fn, circuit_breaker: CircuitBreaker):
        self.service_fn = service_fn
        self.circuit_breaker = circuit_breaker

    async def execute(self, *args, **kwargs):
        """执行服务调用"""
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError("熔断器已打开")

        try:
            result = await self.service_fn(*args, **kwargs)
            self.circuit_breaker.record_success()
            return result
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise
```

### 策略三：超时与重试

```python
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0  # 秒
    max_delay: float = 10.0
    exponential_base: float = 2.0

async def retry_with_backoff(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: float = 10.0,
    **kwargs,
):
    """带指数退避的重试"""
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt), 10.0)
            await asyncio.sleep(delay)
        except Exception:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt), 10.0)
            await asyncio.sleep(delay)
```

### 策略四：空结果处理

```python
async def handle_empty_results(
    query: str,
    docs: list,
    llm,
    vectorstore,
    max_retries: int = 2,
) -> list:
    """处理检索结果为空的情况"""
    if docs:
        return docs

    # 策略 1：查询改写重试
    for _ in range(max_retries):
        rewritten = await rewrite_query(query, llm)
        docs = await vectorstore.asimilarity_search(rewritten, k=5)
        if docs:
            return docs

    # 策略 2：降低相似度阈值
    docs = await vectorstore.asimilarity_search(query, k=5, score_threshold=0.3)
    if docs:
        return docs

    # 策略 3：返回通用文档
    return await vectorstore.asimilarity_search("常见问题", k=3)
```

### 策略五：质量差结果处理

```python
async def handle_poor_results(
    query: str,
    docs: list,
    embedder,
    llm,
    vectorstore,
    quality_threshold: float = 0.3,
) -> list:
    """处理检索质量差的情况"""
    # 评估检索质量
    query_embedding = await embedder.aembed_query(query)
    max_sim = 0
    for doc in docs:
        doc_embedding = await embedder.aembed_query(doc.page_content)
        sim = cosine_similarity(query_embedding, doc_embedding)
        max_sim = max(max_sim, sim)

    if max_sim >= quality_threshold:
        return docs  # 质量可接受

    # 质量差：尝试 HyDE
    hypothetical = await generate_hypothetical_doc(query, llm)
    hyde_docs = await vectorstore.asimilarity_search(hypothetical, k=5)

    # 合并结果
    return reciprocal_rank_fusion([docs, hyde_docs])
```

## 降级优先级

```
1. 服务降级链（同功能不同提供方）
2. 功能降级（Hybrid → Dense → Sparse → 关键词）
3. 质量降级（Rerank → 跳过 Rerank）
4. 输出降级（完整答案 → 检索摘要 → 错误提示）
```

## 关键事实

1. **RAG 系统的六种故障类型**：向量库不可用、Embedding 不可用、Rerank 不可用、LLM 不可用、检索结果为空、检索质量差
2. **服务降级链**为每个服务提供多个替代方案，Aureon 的 Embedding 降级链为：本地 BGE → DashScope → SiliconFlow → Zhipu
3. **熔断器模式**在服务连续失败 5 次后暂时跳过，60 秒后进入半开状态尝试恢复
4. **功能降级策略**：Hybrid Search → 仅 Dense → 仅 Sparse → 关键词匹配，逐步降低检索能力
5. **空结果处理**通过查询改写重试、降低相似度阈值、返回通用文档三个策略逐步降级
