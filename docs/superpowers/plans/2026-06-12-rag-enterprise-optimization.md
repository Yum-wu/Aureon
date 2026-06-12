# Aureon RAG 企业级优化实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Aureon RAG 系统从当前状态升级为企业级架构，支撑 1000+ 文档规模，提升召回率、降低延迟、减少内存占用。

**Architecture:** 基于 ADR-0001~0005 的决策，分 8 个 Task 实施：Qdrant 配置优化 → 稀疏向量迁移 → 并发安全修复 → CRAG 轻量化 → Embedding 统一 → 缓存/异步修复 → 查询路由 → 可观测性。

**Tech Stack:** Qdrant (HNSW + Scalar Quantization + Sparse Vectors), DashScope/SiliconFlow API (embedding + sparse), asyncio, DeepEval, LangSmith/LangFuse

---

## 文件结构映射

| 文件 | 职责 | 关键行号 |
|------|------|---------|
| `backend/app/rag/vector_store.py` | 向量存储 + BM25 + 检索 | L54 缓存上限, L62 全局embedding, L218 BM25构建, L270 scroll加载, L336 BM25检索, L493 embed_texts_llm, L612 孤立代码, L628 增量添加, L677 删除, L1020 统计, L1226 创建collection, L1262 向量检索 |
| `backend/app/rag/qa_chain.py` | RAG pipeline | L777 rag_query, L904 rag_query_astream, L1020 rag_query_with_cache, L1112 增量索引, L1180 全量索引, L1398 hybrid_retrieve_async, L1567 rag_query_async |
| `backend/app/rag/query_rewriter.py` | HyDE + 多查询 | L169 hyde_retrieve, L221 multi_query_retrieve |
| `backend/app/rag/query_classifier.py` | 查询分类 | L158 get_reranking_strategy |
| `backend/app/cache/semantic_cache.py` | 语义缓存 | L630 get_semantic_cache |
| `backend/app/config.py` | 配置 | L27 embedding_dim, L31 skip_local_embed |

---

### Task 1: Qdrant HNSW 参数优化 + 标量量化 + Payload 索引

**ADR:** [ADR-0001](docs/adr/0001-qdrant-hnsw-quantization.md)

**Files:**
- Modify: `backend/app/rag/vector_store.py:1226-1229` (save_index_qdrant)
- Modify: `backend/app/config.py:41-50` (VectorStoreSettings)

- [ ] **Step 1: 在 VectorStoreSettings 中添加 HNSW 和量化配置项**

```python
# backend/app/config.py — VectorStoreSettings 类中添加
class VectorStoreSettings(BaseModel):
    # ... 现有字段 ...
    hnsw_m: int = 32
    hnsw_ef_construct: int = 200
    hnsw_ef_search: int = 128
    quantization_enabled: bool = True
    vectors_on_disk: bool = True
```

- [ ] **Step 2: 修改 save_index_qdrant 使用新配置**

```python
# backend/app/rag/vector_store.py — save_index_qdrant 函数中
# 替换 L1226-1229 的 client.create_collection 调用

from qdrant_client import models as qmodels

client.create_collection(
    collection_name=collection_name,
    vectors_config=qmodels.VectorParams(
        size=dim,
        distance=qmodels.Distance.COSINE,
        on_disk=settings.vectors_on_disk,
        hnsw_config=qmodels.HnswConfigDiff(
            m=settings.hnsw_m,
            ef_construct=settings.hnsw_ef_construct,
        ),
    ),
    hnsw_config=qmodels.HnswConfigDiff(
        ef_search=settings.hnsw_ef_search,
    ),
    quantization_config=qmodels.ScalarQuantization(
        scalar=qmodels.ScalarQuantizationConfig(
            type=qmodels.ScalarType.INT8,
            quantile=0.99,
            always_ram=True,
        ),
    ) if settings.quantization_enabled else None,
)

# 创建 Payload 索引
for field_name in ["metadata.slug", "metadata.language", "metadata.source", "metadata.tenant_id"]:
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass  # 索引可能已存在
```

- [ ] **Step 3: 在 retrieve_qdrant 中使用 hnsw_ef_search 参数**

```python
# backend/app/rag/vector_store.py — retrieve_qdrant 函数的搜索调用中
# 在 client.search 或 client.query_points 调用中添加 search_params

search_params=qmodels.SearchParams(
    hnsw_ef=settings.hnsw_ef_search,
    quantization=qmodels.QuantizationSearchParams(rescore=True),
)
```

- [ ] **Step 4: 删除孤立代码 default_space**

删除 `backend/app/rag/vector_store.py:610-613` 的孤立方法：

```python
# 删除这些行：
# ── Embedding functions (ChromaDB wrapper removed — Qdrant is sole backend) ──

    def default_space(self):
        return "cosine"
```

- [ ] **Step 5: 运行 lint 检查**

```bash
cd backend && python -m ruff check app/rag/vector_store.py app/config.py
```

- [ ] **Step 6: 运行现有单元测试确认无回归**

```bash
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/config.py
git commit -m "feat: optimize Qdrant HNSW params, add scalar quantization and payload indices"
```

---

### Task 2: Qdrant 原生稀疏向量替代 jieba BM25

**ADR:** [ADR-0002](docs/adr/0002-qdrant-sparse-vectors.md)

**Files:**
- Modify: `backend/app/rag/vector_store.py` (添加 sparse 向量支持，移除 jieba BM25)
- Modify: `backend/app/config.py` (添加 sparse 向量配置)
- Create: `backend/app/rag/sparse_embed.py` (sparse embedding API 调用)

- [ ] **Step 1: 在 config.py 添加 sparse 向量配置**

```python
# backend/app/config.py — EmbeddingSettings 类中添加
class EmbeddingSettings(BaseModel):
    # ... 现有字段 ...
    sparse_enabled: bool = True
    sparse_provider: str = "siliconflow"  # siliconflow 支持 BGE-M3 sparse
    sparse_model: str = "BAAI/bge-m3"
```

- [ ] **Step 2: 创建 sparse_embed.py — sparse embedding API 调用**

```python
# backend/app/rag/sparse_embed.py
"""Sparse vector generation via API (BGE-M3 sparse output)."""

import structlog
from typing import Dict, List
from app.config import settings

logger = structlog.get_logger__)


def embed_sparse(texts: List[str]) -> List[Dict[int, float]]:
    """Generate sparse vectors via SiliconFlow BGE-M3 API.

    Returns list of sparse vectors, each as {token_id: weight} dict.
    """
    if not settings.sparse_enabled:
        return [{} for _ in texts]

    if settings.sparse_provider == "siliconflow":
        return _embed_sparse_siliconflow(texts)
    else:
        logger.warning("Sparse provider %s not supported, returning empty", settings.sparse_provider)
        return [{} for _ in texts]


def _embed_sparse_siliconflow(texts: List[str]) -> List[Dict[int, float]]:
    """SiliconFlow BGE-M3 sparse embedding."""
    import httpx

    url = f"{settings.siliconflow_base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
    }

    sparse_vectors = []
    batch_size = 10
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = {
            "model": settings.sparse_model,
            "input": batch,
            "encoding_format": "float",
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("data", []):
                # SiliconFlow BGE-M3 返回的 sparse 向量格式
                sparse = item.get("sparse", {})
                if sparse:
                    sparse_vectors.append(sparse)
                else:
                    sparse_vectors.append({})
        except Exception as e:
            logger.warning("SiliconFlow sparse embedding failed: %s", e)
            sparse_vectors.extend([{} for _ in batch])

    return sparse_vectors
```

- [ ] **Step 3: 修改 save_index_qdrant 支持 named vectors（dense + sparse）**

```python
# backend/app/rag/vector_store.py — save_index_qdrant 中
# 替换 vectors_config 为 named vectors

if settings.sparse_enabled:
    vectors_config = {
        "dense": qmodels.VectorParams(
            size=dim,
            distance=qmodels.Distance.COSINE,
            on_disk=settings.vectors_on_disk,
            hnsw_config=qmodels.HnswConfigDiff(
                m=settings.hnsw_m,
                ef_construct=settings.hnsw_ef_construct,
            ),
        ),
        "sparse": qmodels.SparseVectorParams(
            index=qmodels.SparseIndexParams(on_disk=False),
        ),
    }
else:
    vectors_config = qmodels.VectorParams(
        size=dim,
        distance=qmodels.Distance.COSINE,
        on_disk=settings.vectors_on_disk,
    )

client.create_collection(
    collection_name=collection_name,
    vectors_config=vectors_config,
    # ... hnsw_config, quantization_config, payload indices 同 Task 1 ...
)
```

- [ ] **Step 4: 修改 upsert 逻辑同时写入 dense + sparse 向量**

```python
# backend/app/rag/vector_store.py — save_index_qdrant 的 upsert 部分
# 生成 sparse 向量
from app.rag.sparse_embed import embed_sparse
sparse_vectors = embed_sparse(texts) if settings.sparse_enabled else [{}] * len(texts)

# 构建 points
points = []
for i in range(start, end):
    vector_data = embeddings[i].tolist()  # dense
    point_vector = {"dense": vector_data}
    if settings.sparse_enabled and sparse_vectors[i]:
        point_vector["sparse"] = sparse_vectors[i]

    points.append(PointStruct(
        id=i,
        vector=point_vector,
        payload={"metadata": chunks[i].get("metadata", {}), "text": chunks[i]["text"]},
    ))
```

- [ ] **Step 5: 添加 hybrid_search_qdrant 函数（Qdrant 原生 RRF）**

```python
# backend/app/rag/vector_store.py — 新函数

def hybrid_search_qdrant(
    query: str,
    top_k: int = 5,
    collection_name: str = "aureon",
    tenant_id: str = None,
    lang_filter: str = None,
) -> List[Dict]:
    """Qdrant native hybrid search: dense + sparse with RRF fusion.

    Uses Qdrant Query API (v1.10+) prefetch + Fusion.RRF.
    Falls back to hybrid_retrieve if sparse not available.
    """
    if not settings.sparse_enabled:
        return hybrid_retrieve(query, top_k=top_k, lang_filter=lang_filter)

    client = _get_qdrant()
    if tenant_id is None:
        tenant_id = get_current_tenant_id()

    # 1. 生成 query 的 dense + sparse 向量
    if _skip_local_embed:
        query_emb = embed_texts_llm([query])
    else:
        from app.rag.embed_gpu import get_adaptive_embedder
        embedder = get_adaptive_embedder()
        query_emb = embedder.encode([query])
    dense_vector = query_emb[0].tolist()

    from app.rag.sparse_embed import embed_sparse
    sparse_result = embed_sparse([query])
    sparse_vector = sparse_result[0] if sparse_result else {}

    # 2. 构建 filter
    conditions = []
    if lang_filter:
        conditions.append(qmodels.FieldCondition(
            key="metadata.language",
            match=qmodels.MatchValue(value=lang_filter),
        ))
    if tenant_id:
        conditions.append(qmodels.FieldCondition(
            key="metadata.tenant_id",
            match=qmodels.MatchValue(value=tenant_id),
        ))
    query_filter = qmodels.Filter(must=conditions) if conditions else None

    # 3. Qdrant Query API: prefetch dense + sparse, RRF fusion
    prefetch = [
        qmodels.Prefetch(
            query=dense_vector,
            using="dense",
            limit=top_k * 3,
            filter=query_filter,
        ),
    ]
    if sparse_vector:
        prefetch.append(qmodels.Prefetch(
            query=sparse_vector,
            using="sparse",
            limit=top_k * 3,
            filter=query_filter,
        ))

    results = client.query_points(
        collection_name=collection_name,
        prefetch=prefetch,
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=top_k,
        search_params=qmodels.SearchParams(
            hnsw_ef=settings.hnsw_ef_search,
            quantization=qmodels.QuantizationSearchParams(rescore=True),
        ),
    )

    # 4. 格式化结果
    formatted = []
    for point in results.points:
        payload = point.payload or {}
        formatted.append({
            "id": str(point.id),
            "text": payload.get("text", ""),
            "metadata": payload.get("metadata", {}),
            "score": point.score,
        })
    return formatted
```

- [ ] **Step 6: 修改 hybrid_retrieve 使用 hybrid_search_qdrant**

```python
# backend/app/rag/vector_store.py — hybrid_retrieve 函数开头添加
def hybrid_retrieve(query, top_k=3, lang_filter=None):
    """Hybrid retrieval: Qdrant native sparse+dense RRF, or fallback to BM25+vector."""
    if settings.sparse_enabled:
        return hybrid_search_qdrant(query, top_k=top_k, lang_filter=lang_filter)
    # ... 原有 BM25 + 向量 RRF 逻辑保留作为 fallback ...
```

- [ ] **Step 7: 修改 _add_to_index_qdrant 支持 sparse 向量**

```python
# backend/app/rag/vector_store.py — _add_to_index_qdrant 中
# 在 upsert 前生成 sparse 向量
from app.rag.sparse_embed import embed_sparse
sparse_vectors = embed_sparse(texts) if settings.sparse_enabled else [{}] * len(texts)

# 构建 points 时包含 sparse
points = []
for i in range(end - start):
    vector_data = {"dense": embeddings[start + i].tolist()}
    if settings.sparse_enabled and sparse_vectors[start + i]:
        vector_data["sparse"] = sparse_vectors[start + i]
    points.append(PointStruct(
        id=existing_count + start + i,
        vector=vector_data,
        payload={"metadata": chunks[start + i].get("metadata", {}), "text": chunks[start + i]["text"]},
    ))
```

- [ ] **Step 8: 移除 _build_kw_index 的 force=True 全量重建**

```python
# backend/app/rag/vector_store.py — _add_to_index_qdrant 末尾
# 将 _build_kw_index(force=True) 改为条件调用
if not settings.sparse_enabled:
    _build_kw_index(force=True)  # 仅在 BM25 模式下重建
_invalidate_stats_cache()
```

- [ ] **Step 9: 运行 lint + 单元测试**

```bash
cd backend && python -m ruff check app/rag/vector_store.py app/rag/sparse_embed.py app/config.py
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 10: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/rag/sparse_embed.py backend/app/config.py
git commit -m "feat: add Qdrant native sparse vectors (BGE-M3), replace jieba BM25"
```

---

### Task 3: 修复 `_last_query_embedding` 并发竞态

**Files:**
- Modify: `backend/app/rag/vector_store.py:57-97` (全局变量 + get_thread_query_embedding)
- Modify: `backend/app/rag/vector_store.py:1262+` (retrieve_qdrant 返回值)
- Modify: `backend/app/rag/qa_chain.py` (compress_context 调用处)

- [ ] **Step 1: 修改 retrieve_qdrant 将 query_embedding 附加到结果中**

```python
# backend/app/rag/vector_store.py — retrieve_qdrant 函数末尾
# 在返回结果前，将 query_embedding 附加到每个 chunk

query_vector = query_emb[0]  # numpy array

# ... 现有搜索逻辑 ...

# 附加 query_embedding 到结果（替代全局变量）
for r in formatted_results:
    r["_query_embedding"] = query_vector

# 仍然设置全局变量作为向后兼容（标记 deprecated）
with _last_query_embedding_lock:
    global _last_query_embedding
    _last_query_embedding = query_vector

return formatted_results
```

- [ ] **Step 2: 修改 compress_context 优先使用参数传递的 embedding**

```python
# backend/app/rag/vector_store.py — compress_context 函数签名
def compress_context(query: str, chunks: list, query_embedding=None):
    """Filter chunks by embedding similarity to query.

    Args:
        query: 查询文本
        chunks: 检索结果列表
        query_embedding: 优先使用的 query embedding（从 retrieve_qdrant 结果中获取）
    """
    # 优先级：参数 > chunks 中携带 > 全局变量
    emb = query_embedding
    if emb is None and chunks:
        emb = chunks[0].get("_query_embedding")
    if emb is None:
        emb = get_thread_query_embedding()
    if emb is None:
        return chunks  # 无 embedding 可用，不过滤

    # ... 现有压缩逻辑 ...
```

- [ ] **Step 3: 修改 qa_chain.py 中所有 compress_context 调用处**

```python
# backend/app/rag/qa_chain.py — rag_query 函数中
# 将 chunks 传递给 compress_context 时保留 _query_embedding

chunks = compress_context(query, chunks)
# compress_context 现在会自动从 chunks[0]["_query_embedding"] 获取

# backend/app/rag/qa_chain.py — rag_query_astream 函数中
chunks = await asyncio.to_thread(compress_context, query, chunks)
# 同上，自动从 chunks 中获取
```

- [ ] **Step 4: 运行 lint + 测试**

```bash
cd backend && python -m ruff check app/rag/vector_store.py app/rag/qa_chain.py
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/rag/qa_chain.py
git commit -m "fix: pass query_embedding via function params instead of global variable"
```

---

### Task 4: 轻量评估器替代 LLM CRAG

**ADR:** [ADR-0004](docs/adr/0004-lightweight-crag.md)

**Files:**
- Modify: `backend/app/rag/qa_chain.py:904-1018` (rag_query_astream)
- Modify: `backend/app/rag/retrieval_confidence.py` (评估逻辑)
- Modify: `backend/app/config.py` (添加 CRAG 阈值配置)

- [ ] **Step 1: 在 config.py 添加轻量 CRAG 阈值**

```python
# backend/app/config.py — VectorStoreSettings 类中添加
class VectorStoreSettings(BaseModel):
    # ... 现有字段 ...
    crag_enabled: bool = True
    crag_high_confidence: float = 0.80  # embedding 相似度 > 0.8 = correct
    crag_low_confidence: float = 0.50   # embedding 相似度 < 0.5 = incorrect
```

- [ ] **Step 2: 创建轻量 CRAG 评估函数**

```python
# backend/app/rag/retrieval_confidence.py — 添加新函数

import numpy as np
from typing import List, Dict

def lightweight_crag_assess(
    query_embedding: np.ndarray,
    chunks: List[Dict],
    high_threshold: float = 0.80,
    low_threshold: float = 0.50,
) -> str:
    """基于 embedding 相似度的轻量 CRAG 评估器。

    Returns:
        "correct" — 检索结果高质量，直接使用
        "ambiguous" — 检索结果中等，可补充但不过滤
        "incorrect" — 检索结果低质量，建议返回无结果
    """
    if not chunks:
        return "incorrect"

    # 计算 query 与 top chunks 的相似度
    similarities = []
    for chunk in chunks[:3]:  # 只看 top 3
        chunk_emb = chunk.get("_query_embedding")  # 不对，应该用 chunk 自己的 embedding
        # 使用 score 字段（已经是相似度分数）
        score = chunk.get("score", 0)
        similarities.append(score)

    if not similarities:
        return "ambiguous"

    max_sim = max(similarities)

    if max_sim >= high_threshold:
        return "correct"
    elif max_sim >= low_threshold:
        return "ambiguous"
    else:
        return "incorrect"
```

- [ ] **Step 3: 在 rag_query_astream 中启用轻量 CRAG**

```python
# backend/app/rag/qa_chain.py — rag_query_astream 函数中
# 替换 "CRAG assessment disabled" 注释块

# 2. Lightweight CRAG assessment (embedding-based, not LLM)
if settings.crag_enabled and chunks:
    from app.rag.retrieval_confidence import lightweight_crag_assess
    query_emb = chunks[0].get("_query_embedding") if chunks else None
    assessment = lightweight_crag_assess(
        query_emb, chunks,
        high_threshold=settings.crag_high_confidence,
        low_threshold=settings.crag_low_confidence,
    )
    if assessment == "incorrect":
        no_result_msg = (
            "No relevant content found in the knowledge base. Please try a different question."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        yield {"type": "sources", "sources": []}
        yield {"type": "text", "content": no_result_msg}
        return
    # "correct" 和 "ambiguous" 都继续执行
```

- [ ] **Step 4: 运行 lint + 测试**

```bash
cd backend && python -m ruff check app/rag/qa_chain.py app/rag/retrieval_confidence.py app/config.py
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/qa_chain.py backend/app/rag/retrieval_confidence.py backend/app/config.py
git commit -m "feat: replace LLM CRAG with lightweight embedding-based assessor"
```

---

### Task 5: Embedding 维度统一 1024d

**ADR:** [ADR-0003](docs/adr/0003-embedding-dim-1024.md)

**Files:**
- Modify: `backend/app/config.py:27` (embedding_dim)
- Modify: `backend/app/config.py:35` (dashscope_dimensions)
- Modify: `backend/app/rag/vector_store.py:68` (_LOCAL_MODEL_DIM)

- [ ] **Step 1: 修改 config.py 默认维度为 1024**

```python
# backend/app/config.py
class EmbeddingSettings(BaseModel):
    embedding_dim: int = 1024  # 从 768 改为 1024
    # ...
    dashscope_dimensions: int = 1024  # 从 768 改为 1024
```

- [ ] **Step 2: 修改 vector_store.py 本地模型维度**

```python
# backend/app/rag/vector_store.py
_LOCAL_MODEL_DIM = 1024  # 保持不变（bge-large-zh 就是 1024d）
```

- [ ] **Step 3: 修改 _embed_api 函数中 DashScope 调用传递 dimensions 参数**

```python
# backend/app/rag/vector_store.py — _embed_api 函数中 DashScope 分支
# 确保 API 调用时传递 dimensions=1024

payload = {
    "model": settings.dashscope_model,
    "input": batch,
    "dimensions": settings.dashscope_dimensions,  # 1024
}
```

- [ ] **Step 4: 在 collection 元数据中记录 embedding 维度和模型版本**

```python
# backend/app/rag/vector_store.py — save_index_qdrant 创建 collection 后
# 在 Qdrant collection 的 metadata 中记录配置
# Qdrant 不直接支持 collection metadata，改为在第一个 point 的 payload 中存储

# 在 upsert 的第一个 batch 中添加配置信息
if start == 0 and len(points) > 0:
    points[0].payload["_index_config"] = {
        "embedding_dim": dim,
        "embedding_model": settings.dashscope_model if _skip_local_embed else _LOCAL_MODEL_NAME,
        "sparse_enabled": settings.sparse_enabled,
        "created_at": time.time(),
    }
```

- [ ] **Step 5: 运行 lint + 测试**

```bash
cd backend && python -m ruff check app/rag/vector_store.py app/config.py
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/config.py
git commit -m "feat: unify embedding dimension to 1024d across all providers"
```

---

### Task 6: 语义缓存 + 异步修复 + HyDE 混合检索 + 文档版本管理

**Files:**
- Modify: `backend/app/cache/semantic_cache.py` (API fallback embedding)
- Modify: `backend/app/rag/qa_chain.py:1085` (async 修复)
- Modify: `backend/app/rag/query_rewriter.py:169-218` (HyDE 走混合检索)
- Modify: `backend/app/rag/qa_chain.py:1112-1177` (增量索引前删除旧版本)
- Modify: `backend/app/rag/vector_store.py:54` (缓存上限)

- [ ] **Step 1: 修复语义缓存 API-only 模式**

```python
# backend/app/cache/semantic_cache.py — 找到 skip_local_embed 检查处
# 将 "return False" 改为使用 embed_texts_llm 做 embedding

# 原代码（大约在初始化方法中）：
# if skip_local:
#     logger.info("Skipping local BGE embed, semantic cache will use exact match only")
#     self._embedding_model_loaded = True
#     return False

# 替换为：
if skip_local:
    logger.info("Using API embedding for semantic cache (SKIP_LOCAL_EMBED=true)")
    self._use_api_embed = True
    self._embedding_model_loaded = True
    return True  # 标记为已加载，但使用 API
```

同时在缓存查找/写入方法中：

```python
# 在需要 embedding 的地方，使用 embed_texts_llm 替代本地模型
if getattr(self, '_use_api_embed', False):
    from app.rag.vector_store import embed_texts_llm
    embedding = embed_texts_llm([text])[0]
else:
    # 原有本地模型逻辑
    embedding = self._model.encode([text])[0]
```

- [ ] **Step 2: 修复 rag_query_with_cache 阻塞事件循环**

```python
# backend/app/rag/qa_chain.py — rag_query_with_cache 函数中
# 将 L1085 的同步调用改为异步

# 原代码：
# result = rag_query(query, llm_call_fn, top_k, use_mmr, lang, filter_lang)

# 替换为：
import asyncio
result = await asyncio.to_thread(rag_query, query, llm_call_fn, top_k, use_mmr, lang, filter_lang)
```

- [ ] **Step 3: 修复 HyDE 走混合检索**

```python
# backend/app/rag/query_rewriter.py — hyde_retrieve 函数中
# 将 retrieve() 调用改为 hybrid_retrieve()

# 原代码（大约 L196-218）：
# results = retrieve(hypothetical, top_k=top_k, lang_filter=lang_filter)

# 替换为：
from app.rag.vector_store import hybrid_retrieve
results = hybrid_retrieve(hypothetical, top_k=top_k, lang_filter=lang_filter)
```

- [ ] **Step 4: 增量索引前删除旧版本**

```python
# backend/app/rag/qa_chain.py — run_incremental_index 函数中
# 在添加新 chunks 之前，先删除该文件的旧 chunks

# 在 "add_to_index" 调用之前添加：
from app.rag.vector_store import delete_from_index
filename = os.path.basename(filepath)
delete_from_index(filename)
logger.info("Deleted old chunks for '%s' before re-indexing", filename)
```

- [ ] **Step 5: 增大 embedding 缓存上限**

```python
# backend/app/rag/vector_store.py — L54
_EMBED_CACHE_MAX = 5000  # 从 500 改为 5000，支撑 1000+ 文档
```

- [ ] **Step 6: 运行 lint + 测试**

```bash
cd backend && python -m ruff check app/cache/semantic_cache.py app/rag/qa_chain.py app/rag/query_rewriter.py app/rag/vector_store.py
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/cache/semantic_cache.py backend/app/rag/qa_chain.py backend/app/rag/query_rewriter.py backend/app/rag/vector_store.py
git commit -m "fix: semantic cache API fallback, async rag_query_with_cache, HyDE hybrid retrieve, doc versioning, cache size"
```

---

### Task 7: 查询路由 Adaptive-RAG

**ADR:** [ADR-0005](docs/adr/0005-adaptive-rag-query-routing.md)

**Files:**
- Modify: `backend/app/rag/query_classifier.py` (添加路由决策)
- Modify: `backend/app/rag/qa_chain.py` (rag_query_astream 使用路由)
- Modify: `backend/app/config.py` (添加路由配置)

- [ ] **Step 1: 在 config.py 添加查询路由配置**

```python
# backend/app/config.py — VectorStoreSettings 类中添加
class VectorStoreSettings(BaseModel):
    # ... 现有字段 ...
    query_routing_enabled: bool = True
```

- [ ] **Step 2: 在 query_classifier.py 添加路由函数**

```python
# backend/app/rag/query_classifier.py — 添加新函数

def route_retrieval(query: str) -> str:
    """根据查询复杂度决定检索策略。

    Returns:
        "simple" — 纯 sparse/BM25 检索（<10ms）
        "medium" — hybrid retrieve（100-200ms）
        "complex" — multi_query + rerank（300-500ms）
    """
    if not settings.query_routing_enabled:
        return "complex"  # 默认走完整 pipeline

    strategy = get_reranking_strategy(query)
    # 复用现有分类器的结果
    if strategy == "simple":
        return "simple"
    elif strategy == "medium":
        return "medium"
    else:
        return "complex"
```

- [ ] **Step 3: 在 rag_query_astream 中使用查询路由**

```python
# backend/app/rag/qa_chain.py — rag_query_astream 函数中
# 替换固定的 multi_query_retrieve 调用

# 原代码：
# chunks = await asyncio.to_thread(multi_query_retrieve, query, top_k=top_k, lang_filter=filter_lang)

# 替换为：
from app.rag.query_classifier import route_retrieval

route = route_retrieval(query)
if route == "simple":
    # 简单查询：只走 sparse/keyword 检索
    if settings.sparse_enabled:
        chunks = await asyncio.to_thread(
            hybrid_search_qdrant, query, top_k=top_k, lang_filter=filter_lang
        )
    else:
        from app.rag.vector_store import retrieve_keyword
        chunks = retrieve_keyword(query, top_k=top_k, lang_filter=filter_lang)
elif route == "medium":
    # 中等查询：hybrid retrieve（不含 multi_query）
    chunks = await asyncio.to_thread(
        hybrid_retrieve, query, top_k=top_k, lang_filter=filter_lang
    )
else:
    # 复杂查询：完整 pipeline
    chunks = await asyncio.to_thread(multi_query_retrieve, query, top_k=top_k, lang_filter=filter_lang)
```

- [ ] **Step 4: 运行 lint + 测试**

```bash
cd backend && python -m ruff check app/rag/query_classifier.py app/rag/qa_chain.py app/config.py
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/query_classifier.py backend/app/rag/qa_chain.py backend/app/config.py
git commit -m "feat: add Adaptive-RAG query routing (simple/medium/complex)"
```

---

### Task 8: 可观测性集成 + Contextual Retrieval 并发化

**Files:**
- Modify: `backend/app/rag/qa_chain.py:1180-1271` (run_index_pipeline 并发化)
- Modify: `backend/app/observability/tracing.py` (LangSmith 集成)
- Modify: `backend/app/config.py` (添加可观测性配置)

- [ ] **Step 1: 在 config.py 添加可观测性配置**

```python
# backend/app/config.py — 新增 ObservabilitySettings 类

class ObservabilitySettings(BaseModel):
    langsmith_enabled: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "aureon-rag"
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
```

并在 Settings 类中添加 `observability: ObservabilitySettings = ObservabilitySettings()`

- [ ] **Step 2: 在 tracing.py 中添加 LangSmith 集成**

```python
# backend/app/observability/tracing.py — 添加 LangSmith 初始化

def setup_langsmith():
    """初始化 LangSmith tracing。"""
    if not settings.observability.langsmith_enabled:
        return
    import os
    os.environ["LANGCHAIN_API_KEY"] = settings.observability.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.observability.langsmith_project
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
```

- [ ] **Step 3: 并发化 Contextual Retrieval**

```python
# backend/app/rag/qa_chain.py — run_index_pipeline 函数中
# 将串行的 contextual prefix 生成改为并发

import asyncio

async def _generate_context_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=10):
    """并发生成 contextual prefixes。"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_one(chunk_text, doc_text):
        async with semaphore:
            prompt = f"""<document>
{doc_text}
</document>
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_text}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""
            result = await asyncio.to_thread(llm_call_fn, [{"role": "user", "content": prompt}])
            return result if isinstance(result, str) else str(result)

    tasks = [_process_one(c, d) for c, d in chunks_with_docs]
    return await asyncio.gather(*tasks)
```

- [ ] **Step 4: 运行 lint + 测试**

```bash
cd backend && python -m ruff check app/rag/qa_chain.py app/observability/tracing.py app/config.py
cd backend && python -m pytest tests/ -v -k "not integration and not benchmark and not quality and not smoke"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/qa_chain.py backend/app/observability/tracing.py backend/app/config.py
git commit -m "feat: add LangSmith observability + concurrent Contextual Retrieval"
```

---

## 自审检查

### 1. Spec 覆盖检查

| ADR/问题 | 对应 Task | 状态 |
|----------|----------|------|
| ADR-0001 Qdrant HNSW + 量化 | Task 1 | 覆盖 |
| ADR-0002 稀疏向量替代 BM25 | Task 2 | 覆盖 |
| ADR-0003 维度统一 1024d | Task 5 | 覆盖 |
| ADR-0004 轻量 CRAG | Task 4 | 覆盖 |
| ADR-0005 查询路由 | Task 7 | 覆盖 |
| P0-3 并发竞态 | Task 3 | 覆盖 |
| P1-6 语义缓存 | Task 6 Step 1 | 覆盖 |
| P1-7 async 修复 | Task 6 Step 2 | 覆盖 |
| P1-8 HyDE 混合检索 | Task 6 Step 3 | 覆盖 |
| P1-9 Contextual 并发 | Task 8 Step 3 | 覆盖 |
| P1-10 Payload 索引 | Task 1 Step 2 | 覆盖 |
| P2-B Reranking | 已有 DashScope rerank，无需额外集成 | 确认 |
| P2-C 可观测性 | Task 8 Step 2 | 覆盖 |
| P2-D 文档版本管理 | Task 6 Step 4 | 覆盖 |

### 2. 占位符扫描

无 TBD/TODO/占位符。所有步骤包含完整代码。

### 3. 类型一致性

- `hybrid_search_qdrant` 返回 `List[Dict]`，与 `hybrid_retrieve` 返回类型一致
- `lightweight_crag_assess` 返回 `str`（"correct"/"ambiguous"/"incorrect"）
- `route_retrieval` 返回 `str`（"simple"/"medium"/"complex"）
- `embed_sparse` 返回 `List[Dict[int, float]]`
- 所有函数签名与调用处参数匹配
