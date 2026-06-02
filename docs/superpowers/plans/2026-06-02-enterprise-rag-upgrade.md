# 企业级 RAG 升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Aureon RAG 系统升级为企业级架构，新增 Recall@10/nDCG@10 指标，实现 LLM Negative Detection，升级 Embedding 和 Reranker，引入 Qdrant + Elasticsearch 支持 10K-100K chunks。

**Architecture:** Phase 1 在 benchmark 中新增指标 + qa_chain 中加 LLM classifier；Phase 2 升级 vector_store.py 中的 embedding 模型和 reranker，扩大检索量；Phase 3 新增 Qdrant 和 ES 后端，通过环境变量切换。

**Tech Stack:** Python, FastAPI, ChromaDB, Qdrant, Elasticsearch, sentence-transformers, DeepSeek API

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/tests/run_benchmark.py` | Modify | 新增 Recall@10, nDCG@10 |
| `backend/app/rag/qa_chain.py` | Modify | LLM Negative Detection + 检索量扩大 + rerank 调用 |
| `backend/app/rag/vector_store.py` | Modify | Embedding 模型升级 + Reranker 升级 + Qdrant 后端 + ES 后端 |
| `backend/app/config.py` | Modify | DashScope 维度 + Qdrant/ES 配置 |
| `backend/app/rag/evaluator.py` | Modify | nDCG 计算辅助函数 |
| `docker-compose.yml` | Modify | 新增 Qdrant + ES 容器 |
| `backend/requirements.txt` | Modify | 新增 qdrant-client, elasticsearch |
| `backend/data/benchmark_actual.json` | Modify | benchmark 结果 |
| `docs/benchmarks/recall-evaluation.md` | Modify | 指标文档 |

---

## Phase 1：指标对齐 + Negative Detection

### Task 1: 新增 Recall@10 和 nDCG@10 指标

**Files:**
- Modify: `backend/tests/run_benchmark.py`
- Modify: `backend/app/rag/evaluator.py`

- [ ] **Step 1: 在 evaluator.py 中新增 nDCG 计算函数**

在 `backend/app/rag/evaluator.py` 中添加：

```python
def ndcg_at_k(retrieved_sources: list, expected_source: str, k: int = 10) -> float:
    """Calculate nDCG@K for a single query.
    
    Relevant document gets score 1.0, irrelevant gets 0.0.
    """
    import math
    dcg = 0.0
    for i, source in enumerate(retrieved_sources[:k]):
        rel = 1.0 if source == expected_source else 0.0
        dcg += rel / math.log2(i + 2)  # i+2 because rank starts at 1
    
    # Ideal DCG: relevant doc at rank 1
    idcg = 1.0 / math.log2(2)  # = 1.0
    return dcg / idcg if idcg > 0 else 0.0
```

- [ ] **Step 2: 在 run_benchmark.py 的 test_recall 函数中新增 Recall@10 和 nDCG@10**

在 `test_recall` 函数中，在现有的 Recall@3 计算之后，添加 Recall@10 计算：

```python
# 在函数开头新增
recall_10_hits = 0
ndcg_scores = []

# 在 for qa 循环中，positive 分支内，现有 hit 检查之后添加：
# Recall@10 and nDCG@10
chunks_10 = retrieve_fn(q, top_k=10)
sources_10 = [c.get("metadata", {}).get("slug", "") for c in chunks_10]
if expected_source in sources_10:
    recall_10_hits += 1
from app.rag.evaluator import ndcg_at_k
ndcg_scores.append(ndcg_at_k(sources_10, expected_source, k=10))
```

在返回值中添加：

```python
return {
    # ... existing fields ...
    "recall@10": recall_10_hits / positive_total if positive_total else 0,
    "recall_10_hits": recall_10_hits,
    "ndcg@10": statistics.mean(ndcg_scores) if ndcg_scores else 0,
}
```

- [ ] **Step 3: 在 Summary 输出中添加新指标**

在 `run_benchmark` 函数的 Summary 部分添加：

```python
"Recall@10 (Hybrid)": (hybrid_results["recall@10"], 0.97),
"nDCG@10 (Hybrid)": (hybrid_results["ndcg@10"], 0.80),
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/run_benchmark.py backend/app/rag/evaluator.py
git commit -m "feat: add Recall@10 and nDCG@10 metrics to benchmark"
```

---

### Task 2: LLM Negative Detection Classifier

**Files:**
- Modify: `backend/app/rag/qa_chain.py`

- [ ] **Step 1: 添加 classify_query_answerable 函数**

在 `qa_chain.py` 顶部 import 区之后、函数定义之前添加：

```python
_LOW_SCORE_THRESHOLD = float(os.getenv("LOW_SCORE_THRESHOLD", "0.005"))
_NEGATIVE_DETECTION_ENABLED = os.getenv("NEGATIVE_DETECTION_ENABLED", "true").lower() == "true"


async def classify_query_answerable(query: str, model: str = None) -> bool:
    """用 LLM 判断查询是否属于知识库覆盖范围。"""
    from app.agent.llm import create_llm
    
    llm = create_llm(model=model, temperature=0.0, streaming=False)
    prompt = (
        "你是一个企业知识库的查询分类器。判断以下查询是否能在"
        "\"AI技术、开发经验、部署实践\"相关的知识库中找到答案。\n\n"
        f"查询：{query}\n\n"
        "只回答 YES 或 NO。如果查询涉及以下内容，回答 NO：\n"
        "- 未在知识库中覆盖的具体技术细节（如特定云服务商配置、定价、团队规模）\n"
        "- 与知识库主题无关的领域（如量子计算、生物医学）\n"
        "- 要求最新实时信息的问题（如当前股价、今日天气）\n\n"
        "如果查询涉及以下内容，回答 YES：\n"
        "- RAG、LangChain、LangGraph、BM25、向量检索等 AI 技术\n"
        "- 开发流程、部署实践、性能优化\n"
        "- 知识库中可能涵盖的通用技术问题"
    )
    
    try:
        response = await llm.ainvoke(prompt)
        return "YES" in response.content.upper()
    except Exception as e:
        logger.warning("LLM classifier failed: %s, defaulting to answerable", e)
        return True  # 降级：默认可回答
```

- [ ] **Step 2: 在 rag_query_astream 中集成 classifier**

找到 `rag_query_astream` 函数，在 `hybrid_retrieve` 调用之后、生成答案之前，添加：

```python
results = hybrid_retrieve(query, top_k=3)
if not results:
    yield {"answer": "抱歉，该问题在知识库中未找到相关内容。", "sources": []}
    return

# LLM Negative Detection: 对低分结果做二次确认
if _NEGATIVE_DETECTION_ENABLED and results[0].get("score", 0) < _LOW_SCORE_THRESHOLD:
    answerable = await classify_query_answerable(query, model=model)
    if not answerable:
        yield {"answer": "抱歉，该问题超出了知识库的覆盖范围。", "sources": []}
        return
```

- [ ] **Step 3: 同样在 rag_query_with_cache 中集成**

`rag_query_with_cache` 是同步版本，需要使用 `asyncio.run()` 或改为 async。最简方案：在同步版本中跳过 classifier（仅在流式版本中启用）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat: add LLM-based negative detection classifier

Only triggers for low-score results (score < 0.005).
Uses DeepSeek with temperature=0.0 for deterministic classification.
Falls back to 'answerable' on LLM errors."
```

---

### Task 3: Phase 1 Benchmark 验证

**Files:**
- Execute: `backend/tests/run_benchmark.py`
- Modify: `backend/data/benchmark_actual.json`

- [ ] **Step 1: 运行 benchmark**

```bash
cd backend && python tests/run_benchmark.py
```

- [ ] **Step 2: 验证新指标**

Expected:
- Recall@10 ≥ 97%
- nDCG@10 ≥ 0.80
- Negative Detection ≥ 60%（LLM classifier 对部分查询有效）

- [ ] **Step 3: Commit**

```bash
git add backend/data/benchmark_actual.json
git commit -m "bench: Phase 1 results — Recall@10, nDCG@10, LLM negative detection"
```

---

## Phase 2：Embedding + Reranker 升级

### Task 4: 升级 Embedding 模型到 BGE-large-zh-v1.5

**Files:**
- Modify: `backend/app/rag/vector_store.py:26-27`
- Modify: `backend/app/config.py:28`

- [ ] **Step 1: 修改 vector_store.py 中的模型常量**

```python
# 从
_LOCAL_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
_LOCAL_MODEL_DIM = 512
# 改为
_LOCAL_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
_LOCAL_MODEL_DIM = 1024
```

- [ ] **Step 2: 修改 config.py 中 DashScope 维度**

```python
# 从
dashscope_dimensions: int = 512
# 改为
dashscope_dimensions: int = 1024
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/config.py
git commit -m "feat: upgrade embedding to BGE-large-zh-v1.5 (1024d)"
```

---

### Task 5: 升级 Reranker 到 bge-reranker-v2-m3

**Files:**
- Modify: `backend/app/rag/vector_store.py:714`

- [ ] **Step 1: 修改 reranker 模型名**

```python
# 从
_RERANKER_MODEL = "BAAI/bge-reranker-base"
# 改为
_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/rag/vector_store.py
git commit -m "feat: upgrade reranker to bge-reranker-v2-m3"
```

---

### Task 6: 扩大检索量 + 启用 Rerank

**Files:**
- Modify: `backend/app/rag/qa_chain.py:67-68, 142-147`

- [ ] **Step 1: 扩大初始检索量**

在 `hybrid_retrieve` 中：

```python
# 从
bm25_results = retrieve_keyword(query, top_k=top_k * 2, lang_filter=lang_filter)
vector_results = retrieve(query, top_k=top_k * 2, use_mmr=False, lang_filter=lang_filter)
# 改为
_RETRIEVAL_MULTIPLIER = int(os.getenv("RETRIEVAL_MULTIPLIER", "7"))
bm25_results = retrieve_keyword(query, top_k=top_k * _RETRIEVAL_MULTIPLIER, lang_filter=lang_filter)
vector_results = retrieve(query, top_k=top_k * _RETRIEVAL_MULTIPLIER, use_mmr=False, lang_filter=lang_filter)
```

- [ ] **Step 2: 扩大 RRF 候选数量**

```python
# 从
candidate_limit = min(len(ranked), max(top_k * 3, 10))
# 改为
_RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "20"))
candidate_limit = min(len(ranked), max(_RERANK_CANDIDATES, top_k * 3))
```

- [ ] **Step 3: 启用 rerank 调用**

找到 `hybrid_retrieve` 中被注释掉的 rerank 调用位置，取消注释或添加：

```python
# Rerank: cross-encoder 精排
if len(candidates) > top_k:
    selected = rerank(query, candidates, top_k=top_k)
else:
    selected = candidates[:top_k]
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat: expand retrieval to top-20 and enable reranking

RETRIEVAL_MULTIPLIER=7 (top-21 per retriever)
RERANK_CANDIDATES=20 (RRF candidates for reranker)
Reranker: bge-reranker-v2-m3, top-20 → top-3"
```

---

### Task 7: 删除旧向量索引 + 重新索引

**Files:**
- Execute: `backend/data/vectors/` (删除旧 ChromaDB 数据)
- Execute: `POST /api/rag/index`

- [ ] **Step 1: 删除旧 ChromaDB 向量数据**

```bash
rm -rf backend/data/vectors/
```

- [ ] **Step 2: 重新索引**

```bash
cd backend && python -c "
from app.rag.vector_store import save_index
from app.rag.loader import load_all_articles
articles = load_all_articles()
save_index(articles)
print(f'Indexed {len(articles)} articles')
"
```

- [ ] **Step 3: 运行 benchmark 验证**

```bash
cd backend && python tests/run_benchmark.py
```

Expected: Recall@3 ≥ 93%, MRR ≥ 0.85, 检索延迟 ≤ 160ms

- [ ] **Step 4: Commit**

```bash
git add backend/data/benchmark_actual.json
git commit -m "bench: Phase 2 results — BGE-large + reranker"
```

---

## Phase 3：大规模架构

### Task 8: Qdrant 向量库后端

**Files:**
- Modify: `backend/app/rag/vector_store.py`
- Modify: `backend/app/config.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加 qdrant-client 依赖**

在 `requirements.txt` 中添加：

```
qdrant-client>=1.7.0
```

- [ ] **Step 2: 在 config.py 中添加 Qdrant 配置**

```python
# 在 Settings 类中添加
qdrant_url: str = "http://localhost:6333"
qdrant_api_key: str = ""
vector_backend: str = "chroma"  # "chroma" or "qdrant"
```

- [ ] **Step 3: 在 vector_store.py 中实现 Qdrant 后端**

在文件末尾添加 Qdrant 相关函数：

```python
# ── Qdrant Backend ──
_qdrant_client = None

def _get_qdrant():
    """Get or create Qdrant client singleton."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from app.config import settings
        _qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _qdrant_client

def save_index_qdrant(chunks: List[Dict], collection_name: str = "aureon"):
    """Save chunks to Qdrant."""
    from qdrant_client.models import VectorParams, Distance, PointStruct
    
    client = _get_qdrant()
    dim = _LOCAL_MODEL_DIM
    
    # Recreate collection
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    
    # Embed and upload
    texts = [c["text"] for c in chunks]
    embeddings = _embed_local(texts) or embed_texts_llm(texts)
    
    points = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        points.append(PointStruct(
            id=i,
            vector=emb.tolist(),
            payload={"metadata": chunk.get("metadata", {}), "text": chunk["text"]},
        ))
    
    client.upsert(collection_name=collection_name, points=points)
    logger.info("Qdrant: indexed %d chunks into '%s'", len(chunks), collection_name)

def retrieve_qdrant(query: str, top_k: int = 3, collection_name: str = "aureon") -> List[Dict]:
    """Retrieve from Qdrant."""
    client = _get_qdrant()
    
    query_emb = _embed_local([query])
    if query_emb is None:
        query_emb = embed_texts_llm([query])
    
    results = client.search(
        collection_name=collection_name,
        query_vector=query_emb[0].tolist(),
        limit=top_k,
    )
    
    return [
        {
            "text": r.payload.get("text", ""),
            "metadata": r.payload.get("metadata", {}),
            "score": r.score,
        }
        for r in results
    ]
```

- [ ] **Step 4: 在 save_index 和 retrieve 中添加后端切换**

在 `save_index` 函数开头添加：

```python
from app.config import settings
if settings.vector_backend == "qdrant":
    return save_index_qdrant(chunks)
```

在 `retrieve` 函数开头添加：

```python
from app.config import settings
if settings.vector_backend == "qdrant":
    return retrieve_qdrant(query, top_k=top_k)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/config.py backend/requirements.txt
git commit -m "feat: add Qdrant vector backend (env: VECTOR_BACKEND=qdrant)"
```

---

### Task 9: Elasticsearch BM25 后端

**Files:**
- Modify: `backend/app/rag/vector_store.py`
- Modify: `backend/app/config.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加 elasticsearch 依赖**

在 `requirements.txt` 中添加：

```
elasticsearch>=8.10.0
```

- [ ] **Step 2: 在 config.py 中添加 ES 配置**

```python
# 在 Settings 类中添加
es_url: str = "http://localhost:9200"
es_index: str = "aureon"
bm25_backend: str = "memory"  # "memory" or "elasticsearch"
```

- [ ] **Step 3: 在 vector_store.py 中实现 ES 后端**

在文件末尾添加：

```python
# ── Elasticsearch BM25 Backend ──
_es_client = None

def _get_es():
    global _es_client
    if _es_client is None:
        from elasticsearch import Elasticsearch
        from app.config import settings
        _es_client = Elasticsearch(settings.es_url)
    return _es_client

def save_index_es(chunks: List[Dict], index_name: str = None):
    """Index chunks into Elasticsearch."""
    from app.config import settings
    index_name = index_name or settings.es_index
    es = _get_es()
    
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
    
    es.indices.create(index=index_name, body={
        "settings": {"analysis": {"analyzer": {"default": {"type": "standard"}}}},
        "mappings": {"properties": {
            "text": {"type": "text"},
            "slug": {"type": "keyword"},
            "title": {"type": "text"},
        }}
    })
    
    for i, chunk in enumerate(chunks):
        es.index(index=index_name, id=i, body={
            "text": chunk["text"],
            "slug": chunk.get("metadata", {}).get("slug", ""),
            "title": chunk.get("metadata", {}).get("title", ""),
        })
    
    es.indices.refresh(index=index_name)
    logger.info("ES: indexed %d chunks into '%s'", len(chunks), index_name)

def retrieve_keyword_es(query: str, top_k: int = 20, index_name: str = None) -> List[Dict]:
    """BM25 retrieval via Elasticsearch."""
    from app.config import settings
    index_name = index_name or settings.es_index
    es = _get_es()
    
    results = es.search(index=index_name, body={
        "query": {"multi_match": {"query": query, "fields": ["text", "title"]}},
        "size": top_k,
    })
    
    return [
        {
            "text": hit["_source"]["text"],
            "metadata": {"slug": hit["_source"]["slug"], "title": hit["_source"]["title"]},
            "score": hit["_score"],
        }
        for hit in results["hits"]["hits"]
    ]
```

- [ ] **Step 4: 在 save_index 和 retrieve_keyword 中添加后端切换**

同 Task 8 模式，用 `settings.bm25_backend` 切换。

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/config.py backend/requirements.txt
git commit -m "feat: add Elasticsearch BM25 backend (env: BM25_BACKEND=elasticsearch)"
```

---

### Task 10: docker-compose 更新

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: 添加 Qdrant 和 ES 服务**

在 `docker-compose.yml` 的 `services` 中添加：

```yaml
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.12.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data
```

在 backend 服务的 environment 中添加：

```yaml
      - VECTOR_BACKEND=qdrant
      - BM25_BACKEND=elasticsearch
      - QDRANT_URL=http://qdrant:6333
      - ES_URL=http://elasticsearch:9200
```

在 volumes 部分添加：

```yaml
volumes:
  qdrant_data:
  es_data:
```

- [ ] **Step 2: 验证 docker-compose**

```bash
docker-compose up -d qdrant elasticsearch
docker-compose ps
```

Expected: qdrant 和 elasticsearch 容器 running。

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Qdrant and Elasticsearch to docker-compose"
```

---

### Task 11: 端到端测试 + 最终 Benchmark

**Files:**
- Execute: `backend/tests/run_benchmark.py`
- Modify: `backend/data/benchmark_actual.json`
- Modify: `docs/benchmarks/recall-evaluation.md`

- [ ] **Step 1: 启动 Qdrant + ES**

```bash
docker-compose up -d qdrant elasticsearch
```

- [ ] **Step 2: 索引到 Qdrant**

```bash
cd backend && VECTOR_BACKEND=qdrant python -c "
from app.rag.vector_store import save_index
from app.rag.loader import load_all_articles
articles = load_all_articles()
save_index(articles)
"
```

- [ ] **Step 3: 运行完整 benchmark**

```bash
cd backend && VECTOR_BACKEND=qdrant BM25_BACKEND=memory python tests/run_benchmark.py
```

- [ ] **Step 4: 更新 benchmark 文档**

同步结果到 `docs/benchmarks/recall-evaluation.md`。

- [ ] **Step 5: Commit**

```bash
git add backend/data/benchmark_actual.json docs/benchmarks/recall-evaluation.md
git commit -m "bench: Phase 3 results — Qdrant + enterprise RAG pipeline"
```

---

## Execution Order

```
Phase 1:
  Task 1 (Recall@10, nDCG@10) ← 无依赖
  Task 2 (LLM Classifier)     ← 无依赖，可与 Task 1 并行
  Task 3 (Benchmark)           ← 依赖 Task 1, 2

Phase 2:
  Task 4 (Embedding 升级)      ← 无依赖
  Task 5 (Reranker 升级)       ← 无依赖
  Task 6 (检索量 + rerank)     ← 依赖 Task 4, 5
  Task 7 (重新索引 + benchmark) ← 依赖 Task 6

Phase 3:
  Task 8 (Qdrant)              ← 无依赖
  Task 9 (Elasticsearch)       ← 无依赖
  Task 10 (docker-compose)     ← 依赖 Task 8, 9
  Task 11 (端到端测试)          ← 依赖 Task 10
```

Phase 1 和 Phase 2 可部分并行。Phase 3 独立于 Phase 1/2。
