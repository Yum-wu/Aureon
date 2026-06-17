# 联邦检索：多数据源统一搜索架构

## 联邦检索的挑战

企业级 RAG 系统通常需要从多个数据源检索信息：内部知识库、外部数据库、API 服务、文件系统等。联邦检索（Federated Search）的核心挑战是：**如何统一不同数据源的检索接口、排序标准和结果格式，提供一致的用户体验**。

## 联邦检索架构

### 整体架构

```
用户查询 → 查询路由 → 并行分发到多个数据源 → 结果归一化 → 融合排序 → 返回
```

### 核心组件

1. **查询路由器**：决定查询应该分发到哪些数据源
2. **适配器层**：统一不同数据源的检索接口
3. **结果归一化**：将不同格式的结果统一为标准格式
4. **融合排序**：合并多个数据源的结果并重新排序

## 数据源适配器模式

### 适配器接口设计

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class SearchResult(BaseModel):
    """统一的搜索结果格式"""
    doc_id: str
    title: str
    content: str
    score: float
    source: str
    metadata: dict = {}

class SearchAdapter(ABC):
    """数据源适配器基类"""

    @abstractmethod
    async def search(self, query: str, k: int = 10) -> list[SearchResult]:
        """执行搜索"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源名称"""
        ...
```

### Qdrant 适配器

```python
class QdrantAdapter(SearchAdapter):
    """Qdrant 向量库适配器"""

    def __init__(self, client, collection_name: str, embedder):
        self.client = client
        self.collection_name = collection_name
        self.embedder = embedder

    @property
    def source_name(self) -> str:
        return "qdrant_knowledge_base"

    async def search(self, query: str, k: int = 10) -> list[SearchResult]:
        query_vector = await self.embedder.aembed_query(query)
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=k,
        )
        return [
            SearchResult(
                doc_id=str(r.id),
                title=r.payload.get("title", ""),
                content=r.payload.get("text", ""),
                score=r.score,
                source=self.source_name,
                metadata=r.payload,
            )
            for r in results
        ]

    async def health_check(self) -> bool:
        try:
            info = self.client.get_collection(self.collection_name)
            return info.status == "green"
        except Exception:
            return False
```

### Elasticsearch 适配器

```python
class ElasticsearchAdapter(SearchAdapter):
    """Elasticsearch 适配器"""

    def __init__(self, es_client, index_name: str):
        self.es_client = es_client
        self.index_name = index_name

    @property
    def source_name(self) -> str:
        return "elasticsearch_docs"

    async def search(self, query: str, k: int = 10) -> list[SearchResult]:
        result = self.es_client.search(
            index=self.index_name,
            body={
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^2", "content"],
                    }
                },
                "size": k,
            },
        )
        return [
            SearchResult(
                doc_id=hit["_id"],
                title=hit["_source"].get("title", ""),
                content=hit["_source"].get("content", ""),
                score=hit["_score"],
                source=self.source_name,
                metadata=hit["_source"],
            )
            for hit in result["hits"]["hits"]
        ]

    async def health_check(self) -> bool:
        try:
            return self.es_client.ping()
        except Exception:
            return False
```

### API 适配器

```python
class APIAdapter(SearchAdapter):
    """外部 API 适配器"""

    def __init__(self, base_url: str, api_key: str, source_name: str):
        self.base_url = base_url
        self.api_key = api_key
        self._source_name = source_name

    @property
    def source_name(self) -> str:
        return self._source_name

    async def search(self, query: str, k: int = 10) -> list[SearchResult]:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/search",
                json={"query": query, "k": k},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
            data = response.json()
            return [
                SearchResult(
                    doc_id=item["id"],
                    title=item.get("title", ""),
                    content=item["content"],
                    score=item.get("score", 0),
                    source=self.source_name,
                    metadata=item.get("metadata", {}),
                )
                for item in data.get("results", [])[:k]
            ]

    async def health_check(self) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=5.0,
                )
                return response.status_code == 200
        except Exception:
            return False
```

## 查询路由

### 基于规则的查询路由

```python
class RuleBasedRouter:
    """基于规则的查询路由"""

    def __init__(self, source_rules: dict[str, list[str]]):
        # source_name → 关键词列表
        self.source_rules = source_rules

    def route(self, query: str) -> list[str]:
        """返回应该查询的数据源列表"""
        target_sources = []
        for source, keywords in self.source_rules.items():
            if any(kw in query for kw in keywords):
                target_sources.append(source)

        # 如果没有匹配，查询所有数据源
        return target_sources or list(self.source_rules.keys())

# 配置示例
router = RuleBasedRouter({
    "qdrant_knowledge_base": ["RAG", "检索", "向量", "嵌入"],
    "elasticsearch_docs": ["文档", "手册", "API", "配置"],
    "external_wiki": ["百科", "定义", "概念"],
})
```

### 基于 LLM 的查询路由

```python
class LLMRouter:
    """基于 LLM 的查询路由"""

    ROUTING_PROMPT = """你是一个查询路由助手。根据用户查询，决定应该查询哪些数据源。

可用数据源：
{sources}

用户查询：{query}

请返回应该查询的数据源名称列表（JSON 数组格式）："""

    async def route(self, query: str, sources: list[str], llm) -> list[str]:
        prompt = self.ROUTING_PROMPT.format(
            sources="\n".join(f"- {s}" for s in sources),
            query=query,
        )
        response = await llm.ainvoke(prompt)
        import json
        try:
            selected = json.loads(response)
            return [s for s in selected if s in sources]
        except json.JSONDecodeError:
            return sources  # 解析失败，查询所有
```

## 结果融合

### 分数归一化

不同数据源的分数尺度不同，需要归一化后再融合：

```python
def normalize_scores(results: list[SearchResult], method: str = "minmax") -> list[SearchResult]:
    """归一化搜索结果的分数"""
    if not results:
        return results

    scores = [r.score for r in results]

    if method == "minmax":
        min_s, max_s = min(scores), max(scores)
        range_s = max_s - min_s if max_s != min_s else 1
        for r in results:
            r.score = (r.score - min_s) / range_s
    elif method == "zscore":
        import statistics
        mean_s = statistics.mean(scores)
        std_s = statistics.stdev(scores) if len(scores) > 1 else 1
        for r in results:
            r.score = (r.score - mean_s) / std_s

    return results
```

### 联邦 RRF 融合

```python
async def federated_search(
    query: str,
    adapters: list[SearchAdapter],
    router,
    k: int = 10,
    rrf_k: int = 60,
) -> list[SearchResult]:
    """联邦检索：多数据源统一搜索"""
    # 1. 查询路由
    target_sources = router.route(query)
    target_adapters = [a for a in adapters if a.source_name in target_sources]

    # 2. 并行检索
    search_tasks = [adapter.search(query, k=k*2) for adapter in target_adapters]
    all_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # 3. 归一化各数据源的分数
    normalized_results = []
    for results in all_results:
        if isinstance(results, Exception):
            continue  # 跳过失败的数据源
        normalized = normalize_scores(results, method="minmax")
        normalized_results.append(normalized)

    # 4. RRF 融合
    fused = federated_rrf(normalized_results, k=rrf_k)

    return fused[:k]


def federated_rrf(
    result_lists: list[list[SearchResult]], k: int = 60
) -> list[SearchResult]:
    """联邦 RRF 融合"""
    scores = {}
    for results in result_lists:
        for rank, result in enumerate(results, start=1):
            if result.doc_id not in scores:
                scores[result.doc_id] = {"score": 0, "result": result}
            scores[result.doc_id]["score"] += 1 / (k + rank)

    sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return [item["result"] for item in sorted_results]
```

## 容错与降级

### 数据源故障处理

```python
async def resilient_federated_search(
    query: str,
    adapters: list[SearchAdapter],
    k: int = 10,
    timeout: float = 5.0,
) -> list[SearchResult]:
    """容错联邦检索"""
    import asyncio

    async def search_with_timeout(adapter: SearchAdapter):
        try:
            return await asyncio.wait_for(adapter.search(query, k=k*2), timeout=timeout)
        except asyncio.TimeoutError:
            return []
        except Exception:
            return []

    # 并行检索，超时和异常返回空结果
    tasks = [search_with_timeout(adapter) for adapter in adapters]
    all_results = await asyncio.gather(*tasks)

    # 过滤空结果
    valid_results = [r for r in all_results if r]

    if not valid_results:
        # 所有数据源都失败，返回空结果
        return []

    # 融合
    return federated_rrf(valid_results)[:k]
```

## 性能优化

### 缓存策略

```python
class CachedFederatedSearch:
    """带缓存的联邦检索"""

    def __init__(self, adapters, router, cache, ttl: int = 300):
        self.adapters = adapters
        self.router = router
        self.cache = cache
        self.ttl = ttl

    async def search(self, query: str, k: int = 10) -> list[SearchResult]:
        # 检查缓存
        cache_key = f"federated:{query}:{k}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # 执行联邦检索
        results = await federated_search(query, self.adapters, self.router, k=k)

        # 写入缓存
        await self.cache.set(cache_key, results, ttl=self.ttl)

        return results
```

## 关键事实

1. **联邦检索的核心挑战**是统一不同数据源的检索接口、排序标准和结果格式，提供一致的用户体验
2. **适配器模式（Adapter Pattern）**是联邦检索的基础，为每个数据源实现统一接口，隔离差异
3. **查询路由决定查询应该分发到哪些数据源**，可以基于规则（关键词匹配）或基于 LLM（语义理解）
4. **不同数据源的分数尺度不同，必须归一化后才能融合**，常用 Min-Max 归一化或 Z-Score 归一化
5. **容错设计是联邦检索的关键**——单个数据源故障不应影响整体检索，通过超时控制和异常处理实现降级
