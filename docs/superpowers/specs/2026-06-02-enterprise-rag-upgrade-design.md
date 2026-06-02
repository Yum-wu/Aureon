# 企业级 RAG 升级设计文档

> **状态**：待批准  
> **日期**：2026-06-02  
> **版本**：v21  
> **范围**：指标对齐 + Negative Detection + Embedding 升级 + Reranker + 大规模架构

---

## 一、目标

将 Aureon 从 40 篇文章的小知识库升级为企业级 RAG 系统，支持 10K-100K chunks。

### 延迟目标（TTFT < 500ms）

| 阶段 | 升级后预算 | 当前 |
|------|-----------|------|
| Embedding | 5-10ms | <1ms |
| BM25 | 5-15ms | 2.4ms |
| Vector | 5-10ms | 1.8ms |
| Reranking | 50-100ms | 无 |
| **检索总计** | **70-140ms** | **4.4ms** |
| LLM TTFT | 200-400ms | ~300ms |
| **总 TTFT** | **<550ms** | **~310ms** |

### 质量目标

| 指标 | 当前 | 目标 | 行业标准 |
|------|------|------|---------|
| Recall@3 | 93.9% | ≥93% | 70-85% |
| Recall@10 | 未测 | ≥97% | 85-95% |
| MRR | 0.894 | ≥0.85 | 0.65-0.85 |
| nDCG@10 | 未测 | ≥0.80 | 0.65-0.85 |
| Negative Detection | 6.7% | ≥80% | — |

---

## 二、Phase 1：指标对齐 + Negative Detection

### 2.1 新增指标

在 `backend/tests/run_benchmark.py` 中新增：

- **Recall@10**：top-10 中是否包含正确文章
- **nDCG@10**：考虑排名位置的检索质量指标
- **按难度/类型分组统计**（已有，确保完整）

### 2.2 Negative Detection — LLM Classifier

**方案**：不靠检索分数，用 LLM 单次调用判断查询是否属于知识域。

#### 实现

```python
# backend/app/rag/qa_chain.py — 新增函数
async def classify_query_answerable(query: str, model: str = None) -> bool:
    """用 LLM 判断查询是否能在知识库中找到答案。"""
    from app.agent.llm import create_llm
    
    llm = create_llm(model=model, temperature=0.0, streaming=False)
    prompt = f"""你是一个企业知识库的查询分类器。判断以下查询是否能在"AI技术、开发经验、部署实践"相关的知识库中找到答案。

查询：{query}

只回答 YES 或 NO。如果查询涉及以下内容，回答 NO：
- 未在知识库中覆盖的具体技术细节（如特定云服务商配置、定价、团队规模）
- 与知识库主题无关的领域（如量子计算、生物医学）
- 要求最新实时信息的问题（如当前股价、今日天气）

如果查询涉及以下内容，回答 YES：
- RAG、LangChain、LangGraph、BM25、向量检索等 AI 技术
- 开发流程、部署实践、性能优化
- 知识库中可能涵盖的通用技术问题"""
    
    response = await llm.ainvoke(prompt)
    return "YES" in response.content.upper()
```

#### 集成点

在 `hybrid_retrieve` 返回结果后、生成答案前，调用 classifier：

```python
# rag_query_with_cache 或 rag_query_astream 中
results = hybrid_retrieve(query, top_k=3)
if not results:
    return "抱歉，该问题在知识库中未找到相关内容。"

# 对低分结果做二次确认
if results[0].get("score", 0) < _LOW_SCORE_THRESHOLD:
    answerable = await classify_query_answerable(query)
    if not answerable:
        return "抱歉，该问题超出了知识库的覆盖范围。"
```

#### 延迟

- DeepSeek API: ~200-300ms
- 仅在低分结果时触发（~30% 的查询），不影响正常查询延迟

---

## 三、Phase 2：Embedding + Reranker 升级

### 3.1 Embedding 升级

**方案**：BGE-small-zh (512d, 33M) → BGE-large-zh-v1.5 (1024d, 326M)

| 属性 | BGE-small-zh | BGE-large-zh |
|------|-------------|-------------|
| 维度 | 512 | 1024 |
| 参数量 | 33M | 326M |
| C-MTEB Retrieval | ~62-65 | ~68-70 |
| CPU 延迟 | <1ms | 5-10ms |
| 内存 | ~100MB | ~1.3GB |

#### 改动

```python
# backend/app/rag/vector_store.py
_LOCAL_MODEL_NAME = "BAAI/bge-large-zh-v1.5"  # 从 bge-small-zh 升级
_LOCAL_MODEL_DIM = 1024  # 从 512 升级
```

#### 重新索引

升级后必须重建所有向量索引（不同模型的向量空间不兼容）：
- ChromaDB collection 需要删除重建
- 运行 `POST /api/rag/index` 重新索引
- Railway startup 已有自动检测逻辑，会自动触发

#### DashScope fallback 维度对齐

```python
# backend/app/config.py
dashscope_dimensions: int = 1024  # 从 512 升级，与 BGE-large 对齐
```

### 3.2 Reranker 升级

**方案**：bge-reranker-base → bge-reranker-v2-m3

| 属性 | bge-reranker-base | bge-reranker-v2-m3 |
|------|-------------------|---------------------|
| 参数量 | 278M | 568M |
| 多语言 | 中英文 | 100+ 语言 |
| CPU 延迟 (10 docs) | ~100ms | ~150ms |
| 质量 (BEIR) | 基线 | +5-10% |

#### 改动

```python
# backend/app/rag/vector_store.py
_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"  # 从 bge-reranker-base 升级
```

#### 检索流程变更

当前：
```
Query → BM25(top-6) + Vector(top-6) → RRF → top-3
```

升级后：
```
Query → BM25(top-20) + Vector(top-20) → RRF → top-20 → Rerank → top-3
```

```python
# qa_chain.py — hybrid_retrieve 中
# 1. 扩大初始检索量
bm25_results = retrieve_keyword(query, top_k=top_k * 7, ...)  # 从 *2 改为 *7
vector_results = retrieve(query, top_k=top_k * 7, ...)  # 从 *2 改为 *7

# 2. RRF 融合后取 top-20
candidates = ... # RRF 排序后
candidate_limit = min(len(candidates), 20)  # 从 top_k*3 改为 20

# 3. Rerank
if len(candidates) > top_k:
    selected = rerank(query, candidates, top_k=top_k)
else:
    selected = candidates[:top_k]
```

#### 延迟影响

- Reranking 20 个候选：~150ms CPU
- 总检索延迟：4.4ms → ~160ms
- 仍在 TTFT 500ms 预算内（160ms 检索 + 300ms LLM = 460ms）

---

## 四、Phase 3：大规模架构

### 4.1 向量库：ChromaDB → Qdrant

| 属性 | ChromaDB | Qdrant |
|------|----------|--------|
| 100K 查询延迟 | ~10-20ms | <5ms |
| 内存效率 | 一般 | 高（Rust） |
| Payload 过滤 | 支持 | 原生支持 |
| 部署 | pip | Docker |

#### 改动

```python
# backend/app/rag/vector_store.py — 替换 ChromaDB 为 Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

_qdrant_client: Optional[QdrantClient] = None

def _get_qdrant() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY", ""),
        )
    return _qdrant_client
```

#### 迁移策略

1. Qdrant 作为新向量库，ChromaDB 代码保留作 fallback
2. 环境变量切换：`VECTOR_BACKEND=qdrant|chroma`
3. Railway 部署时 Qdrant 作为 sidecar 容器

### 4.2 BM25：内存倒排 → Elasticsearch

当前内存倒排在 100K chunks 时内存占用过大。Elasticsearch 提供：
- 分布式 BM25
- 增量索引更新
- 更好的中文分词（IK Analyzer）

#### 改动

```python
# backend/app/rag/vector_store.py — 新增 ES 检索
from elasticsearch import Elasticsearch

_es_client: Optional[Elasticsearch] = None

def retrieve_keyword_es(query: str, top_k: int = 20) -> List[Dict]:
    """BM25 检索 via Elasticsearch."""
    ...
```

#### 迁移策略

1. ES 作为 BM25 后端，内存倒排保留作 fallback
2. 环境变量切换：`BM25_BACKEND=elasticsearch|memory`
3. Railway 部署时 ES 作为 sidecar 容器

### 4.3 docker-compose.yml 更新

```yaml
services:
  backend:
    build: .
    ports: ["8000:8000"]
    environment:
      - VECTOR_BACKEND=qdrant
      - BM25_BACKEND=elasticsearch
      - QDRANT_URL=http://qdrant:6333
      - ES_URL=http://elasticsearch:9200
  
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: ["qdrant_data:/qdrant/storage"]
  
  elasticsearch:
    image: elasticsearch:8.12.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports: ["9200:9200"]
    volumes: ["es_data:/usr/share/elasticsearch/data"]

volumes:
  qdrant_data:
  es_data:
```

---

## 五、实施顺序

```
Phase 1: 指标 + Negative Detection（1-2 天）
├── A1. 新增 Recall@10, nDCG@10 指标
├── A2. LLM Negative Detection classifier
└── A3. 跑 benchmark 验证

Phase 2: Embedding + Reranker（2-3 天）
├── B1. 升级 BGE-large-zh-v1.5 (1024d)
├── B2. 升级 bge-reranker-v2-m3
├── B3. 扩大检索量 top-20 + rerank
├── B4. DashScope 维度对齐
├── B5. 重新索引 + benchmark 验证
└── B6. Railway 自动索引适配

Phase 3: 大规模架构（3-5 天）
├── C1. Qdrant 替代 ChromaDB
├── C2. Elasticsearch 替代内存 BM25
├── C3. docker-compose 更新
├── C4. 环境变量切换逻辑
└── C5. 端到端测试
```

---

## 六、验收标准

### Phase 1

| 指标 | 目标 |
|------|------|
| Recall@10 | ≥97% |
| nDCG@10 | ≥0.80 |
| Negative Detection | ≥80% |

### Phase 2

| 指标 | 目标 |
|------|------|
| Recall@3 | ≥93% |
| MRR | ≥0.85 |
| 检索延迟 | ≤160ms |
| TTFT | ≤500ms |

### Phase 3

| 指标 | 目标 |
|------|------|
| 100K chunks 查询延迟 | ≤10ms |
| docker-compose 一键启动 | ✅ |
| 环境变量切换 | ✅ |

---

## 七、风险与降级

| 风险 | 降级方案 |
|------|---------|
| BGE-large 延迟超预期 | 回退 BGE-small，用 DashScope API |
| Reranker 降低小库召回率 | 环境变量 RERANK_ENABLED=false |
| Qdrant 部署失败 | 保持 ChromaDB |
| ES 部署失败 | 保持内存 BM25 |
| LLM classifier 误判 | 双层：classifier + 系统 prompt 兜底 |

所有组件均可通过环境变量切换回旧实现。

---

*设计文档版本: v1*  
*最后更新: 2026-06-02*
