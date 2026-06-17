# Redis 语义缓存实现

## 语义缓存架构

Redis 语义缓存结合了 Redis 的高速键值存储和 Embedding 的语义匹配能力，实现语义级别的查询缓存。

## 实现方案

### 精确缓存（L1）

```python
import hashlib
import json

class RedisExactCache:
    """Redis 精确缓存"""

    def __init__(self, redis_client, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl

    def _key(self, query: str) -> str:
        return f"rag:exact:{hashlib.md5(query.encode()).hexdigest()}"

    async def get(self, query: str) -> str | None:
        return await self.redis.get(self._key(query))

    async def set(self, query: str, answer: str):
        await self.redis.set(self._key(query), answer, ex=self.ttl)

    async def clear(self):
        async for key in self.redis.scan_iter("rag:exact:*"):
            await self.redis.delete(key)
```

### 语义缓存（L2）

```python
class RedisSemanticCache:
    """Redis 语义缓存"""

    def __init__(self, redis_client, embedder, similarity_threshold: float = 0.95):
        self.redis = redis_client
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold

    async def get(self, query: str) -> str | None:
        """查询语义缓存"""
        query_embedding = await self.embedder.aembed_query(query)

        # 遍历缓存条目查找语义匹配
        async for key in self.redis.scan_iter("rag:semantic:*"):
            cached_embedding = json.loads(await self.redis.hget(key, "embedding"))
            similarity = np.dot(query_embedding, cached_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(cached_embedding)
            )

            if similarity >= self.similarity_threshold:
                return await self.redis.hget(key, "answer")

        return None

    async def set(self, query: str, answer: str, embedding: list[float]):
        """写入语义缓存"""
        key = f"rag:semantic:{hashlib.md5(query.encode()).hexdigest()}"
        await self.redis.hset(key, mapping={
            "query": query,
            "answer": answer,
            "embedding": json.dumps(embedding),
        })
        await self.redis.expire(key, 1800)
```

### 多级缓存

```python
class MultiLevelCache:
    """多级缓存：L1 精确 + L2 语义"""

    def __init__(self, exact_cache, semantic_cache):
        self.exact = exact_cache
        self.semantic = semantic_cache

    async def get(self, query: str) -> str | None:
        # L1：精确缓存
        answer = await self.exact.get(query)
        if answer:
            return answer

        # L2：语义缓存
        answer = await self.semantic.get(query)
        if answer:
            await self.exact.set(query, answer)  # 回填 L1
            return answer

        return None

    async def set(self, query: str, answer: str, embedding: list[float]):
        await self.exact.set(query, answer)
        await self.semantic.set(query, answer, embedding)
```

## 缓存效果

| 指标 | 无缓存 | L1 精确 | L1+L2 语义 |
|------|--------|---------|-----------|
| 命中率 | 0% | 25% | 60% |
| P50 延迟 | 980ms | 735ms | 390ms |

## 关键事实

1. **Redis 语义缓存结合 Redis 高速存储和 Embedding 语义匹配**，实现语义级别的查询缓存
2. **多级缓存策略**：L1 精确缓存（<1ms，命中率 25%）→ L2 语义缓存（~10ms，命中率 60%）
3. **语义缓存的相似度阈值通常设为 0.95**，低于此值可能返回不相关答案
4. **缓存 TTL 建议**：精确缓存 1 小时，语义缓存 30 分钟，检索结果缓存 15 分钟
5. **Aureon 的多级缓存将 P50 延迟从 980ms 降至 390ms**，命中率 60%
