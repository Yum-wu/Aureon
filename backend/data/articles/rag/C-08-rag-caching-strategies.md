# RAG 缓存策略：语义缓存与查询去重

## 缓存的必要性

RAG 系统的每次查询涉及 Embedding 编码、向量检索、Rerank、LLM 生成等多个步骤，延迟高、成本大。缓存可以避免重复计算，显著降低延迟和成本。

研究表明，生产环境中约 30-40% 的查询是重复或语义相似的，缓存命中率可达 60% 以上。

## 缓存层级

### L1：精确缓存（Exact Cache）

键值对缓存，查询完全匹配时命中：

```python
import hashlib
from datetime import timedelta

class ExactCache:
    """精确缓存：查询文本完全匹配"""

    def __init__(self, redis_client, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl

    def _cache_key(self, query: str) -> str:
        return f"rag:exact:{hashlib.md5(query.encode()).hexdigest()}"

    async def get(self, query: str) -> str | None:
        key = self._cache_key(query)
        return await self.redis.get(key)

    async def set(self, query: str, answer: str):
        key = self._cache_key(query)
        await self.redis.set(key, answer, ex=self.ttl)
```

**局限**：只能匹配完全相同的查询，"什么是 RAG"和"RAG 是什么"无法命中同一缓存。

### L2：语义缓存（Semantic Cache）

基于语义相似度的缓存，语义相似的查询可以命中同一缓存：

```python
class SemanticCache:
    """语义缓存：基于 Embedding 相似度"""

    def __init__(self, embedder, vectorstore, similarity_threshold: float = 0.95):
        self.embedder = embedder
        self.vectorstore = vectorstore  # 缓存向量库
        self.similarity_threshold = similarity_threshold

    async def get(self, query: str) -> str | None:
        """查询语义缓存"""
        query_embedding = await self.embedder.aembed_query(query)

        # 在缓存向量库中搜索最相似的缓存条目
        results = await self.vectorstore.asimilarity_search_by_vector(
            query_embedding, k=1
        )

        if results:
            doc = results[0]
            similarity = doc.metadata.get("score", 0)

            if similarity >= self.similarity_threshold:
                return doc.metadata.get("answer")

        return None

    async def set(self, query: str, answer: str):
        """写入语义缓存"""
        query_embedding = await self.embedder.aembed_query(query)

        await self.vectorstore.aadd_embedding(
            text=query,
            embedding=query_embedding,
            metadata={"answer": answer, "query": query},
        )
```

### L3：检索结果缓存

缓存检索结果而非最终答案，适用于检索结果可复用的场景：

```python
class RetrievalCache:
    """检索结果缓存"""

    def __init__(self, redis_client, ttl: int = 1800):
        self.redis = redis_client
        self.ttl = ttl

    async def get(self, query: str) -> list | None:
        key = f"rag:retrieval:{hashlib.md5(query.encode()).hexdigest()}"
        cached = await self.redis.get(key)
        if cached:
            return json.loads(cached)
        return None

    async def set(self, query: str, docs: list):
        key = f"rag:retrieval:{hashlib.md5(query.encode()).hexdigest()}"
        data = json.dumps([{"content": d.page_content, "metadata": d.metadata} for d in docs])
        await self.redis.set(key, data, ex=self.ttl)
```

## 查询去重

### 语义去重

识别语义相同的查询，避免重复处理：

```python
class QueryDeduplicator:
    """查询语义去重"""

    def __init__(self, embedder, similarity_threshold: float = 0.92):
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.query_history = []  # 最近查询的 Embedding

    async def is_duplicate(self, query: str) -> tuple[bool, str | None]:
        """判断查询是否与最近查询重复"""
        query_embedding = await self.embedder.aembed_query(query)

        for hist_query, hist_embedding in self.query_history:
            similarity = np.dot(query_embedding, hist_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(hist_embedding)
            )

            if similarity >= self.similarity_threshold:
                return True, hist_query

        # 添加到历史
        self.query_history.append((query, query_embedding))

        # 限制历史长度
        if len(self.query_history) > 1000:
            self.query_history = self.query_history[-500:]

        return False, None
```

### 会话内去重

同一会话中，连续的相似查询直接复用结果：

```python
class SessionQueryCache:
    """会话内查询缓存"""

    def __init__(self, similarity_threshold: float = 0.90):
        self.sessions = {}  # session_id → list of (query, answer, embedding)
        self.similarity_threshold = similarity_threshold

    async def get(self, session_id: str, query: str, embedder) -> str | None:
        """查询会话缓存"""
        if session_id not in self.sessions:
            return None

        query_embedding = await embedder.aembed_query(query)

        for hist_query, hist_answer, hist_embedding in self.sessions[session_id]:
            similarity = np.dot(query_embedding, hist_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(hist_embedding)
            )

            if similarity >= self.similarity_threshold:
                return hist_answer

        return None

    async def set(self, session_id: str, query: str, answer: str, embedding):
        """写入会话缓存"""
        if session_id not in self.sessions:
            self.sessions[session_id] = []

        self.sessions[session_id].append((query, answer, embedding))

        # 限制每会话缓存条目
        if len(self.sessions[session_id]) > 50:
            self.sessions[session_id] = self.sessions[session_id][-25:]
```

## 缓存策略组合

### 多级缓存

```python
class MultiLevelCache:
    """多级缓存：精确 → 语义 → 检索结果"""

    def __init__(
        self,
        exact_cache: ExactCache,
        semantic_cache: SemanticCache,
        retrieval_cache: RetrievalCache,
    ):
        self.exact_cache = exact_cache
        self.semantic_cache = semantic_cache
        self.retrieval_cache = retrieval_cache

    async def get_answer(self, query: str) -> str | None:
        """从多级缓存获取答案"""
        # L1：精确缓存
        answer = await self.exact_cache.get(query)
        if answer:
            return answer

        # L2：语义缓存
        answer = await self.semantic_cache.get(query)
        if answer:
            # 回填精确缓存
            await self.exact_cache.set(query, answer)
            return answer

        return None

    async def get_retrieval(self, query: str) -> list | None:
        """从检索缓存获取结果"""
        return await self.retrieval_cache.get(query)

    async def set_answer(self, query: str, answer: str):
        """写入所有缓存层"""
        await self.exact_cache.set(query, answer)
        await self.semantic_cache.set(query, answer)

    async def set_retrieval(self, query: str, docs: list):
        """写入检索缓存"""
        await self.retrieval_cache.set(query, docs)
```

## 缓存失效策略

### TTL 策略

```python
# 不同类型缓存的 TTL
CACHE_TTL = {
    "exact_answer": 3600,      # 精确答案缓存 1 小时
    "semantic_answer": 1800,   # 语义答案缓存 30 分钟
    "retrieval_results": 900,  # 检索结果缓存 15 分钟
    "session_query": 1800,     # 会话查询缓存 30 分钟
}
```

### 主动失效

```python
class CacheInvalidator:
    """缓存失效管理"""

    async def invalidate_on_document_update(self, doc_id: str):
        """文档更新时失效相关缓存"""
        # 失效所有检索缓存（无法确定哪些查询涉及该文档）
        await self.retrieval_cache.clear()

        # 失效语义缓存中与该文档相关的条目
        # 需要检索缓存向量库找到相关条目
        pass

    async def invalidate_on_model_update(self):
        """模型更新时失效所有缓存"""
        await self.exact_cache.clear()
        await self.semantic_cache.clear()
        await self.retrieval_cache.clear()
```

## 缓存效果

### Aureon 实测

| 指标 | 无缓存 | 精确缓存 | 语义缓存 | 多级缓存 |
|------|--------|---------|---------|---------|
| 命中率 | 0% | 25% | 45% | 60% |
| P50 延迟 | 980ms | 735ms | 540ms | 390ms |
| 月成本 | ¥500 | ¥375 | ¥275 | ¥200 |

## 关键事实

1. **生产环境中约 30-40% 的查询是重复或语义相似的**，缓存命中率可达 60% 以上
2. **语义缓存基于 Embedding 相似度匹配**，相似度阈值通常设为 0.95，可以匹配"什么是 RAG"和"RAG 是什么"等语义等价查询
3. **多级缓存策略**：L1 精确缓存（Redis，<1ms）→ L2 语义缓存（向量库，~10ms）→ L3 检索结果缓存（Redis，<1ms）
4. **查询去重**通过语义相似度识别重复查询，会话内去重阈值可设为 0.90（比语义缓存更宽松）
5. **Aureon 的多级缓存将 P50 延迟从 980ms 降至 390ms**，月成本从 ¥500 降至 ¥200
