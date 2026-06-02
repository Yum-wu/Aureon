# RAG 质量优化 + P1 功能补齐 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 RAG Negative Detection (0→80%+) 和 Precision@3 (31→60%+)，补齐多 LLM 适配、Suggested Prompts、SEO 等 P1 功能。

**Architecture:** 
Phase 1 在 `qa_chain.py` 的 RRF 融合前插入检索分数阈值过滤（vector cosine ≥ 0.25, BM25 raw ≥ 0.15），限制 vector 参与数量（max 3），调大 RRF k 值（60→200）。Phase 2 通过 `MODEL_REGISTRY` + `create_llm()` 扩展支持多 provider，新增 `/api/rag/suggestions` 端点和 Landing Page SEO meta tags。

**Tech Stack:** Python, FastAPI, LangChain, ChromaDB, React, TypeScript

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/rag/qa_chain.py` | Modify | 检索分数阈值 + vector 限制 + RRF_K 调整 |
| `backend/app/rag/vector_store.py` | Modify | BM25 阈值提升 + cosine_score 存入 metadata |
| `backend/app/rag/test_data.py` | Modify | 新增 threshold 相关断言 |
| `backend/tests/test_rag_quality.py` | Create | Phase 1 质量门禁测试 |
| `backend/app/config.py` | Modify | 新增 MODEL_REGISTRY |
| `backend/app/agent/llm.py` | Modify | create_llm() 支持 model 参数 |
| `backend/app/routers/rag.py` | Modify | 新增 /api/rag/suggestions 端点 |
| `backend/app/routers/chat.py` | Modify | chat 端点加 model 参数 |
| `src/pages/Search.tsx` | Modify | Suggested Prompts UI |
| `src/pages/Landing.tsx` | Modify | SEO meta tags + JSON-LD |
| `index.html` | Modify | 默认 meta tags |
| `src/App.tsx` | Modify | 隐藏 /crew 导航入口 |
| `backend/data/benchmark_actual.json` | Modify | Phase 1 benchmark 结果 |
| `docs/benchmarks/recall-evaluation.md` | Modify | 同步指标 |
| `目标.md` | Modify | 更新到 v20 |

---

## Phase 1: RAG 质量修复（P0）

### Task 1: Vector cosine_score 存入 metadata

**Why:** 当前 `vector_store.py` 的 `retrieve()` 返回的结果中，cosine score 存在 `doc["score"]` 但不在 `metadata` 里。后续阈值过滤需要从 metadata 读取。

**Files:**
- Modify: `backend/app/rag/vector_store.py`

- [ ] **Step 1: 读取 vector_store.py 的 retrieve 函数**

找到 `retrieve()` 函数中 ChromaDB 查询结果的处理逻辑。ChromaDB 返回 `distances`，当前代码转换为 `score = 1.0 / (1.0 + distance)`。

- [ ] **Step 2: 将 cosine_score 存入 metadata**

在 `retrieve()` 函数中，将 `cosine_score` 写入每个结果的 metadata：

```python
# 在构建 result dict 时，添加 cosine_score 到 metadata
metadata["cosine_score"] = cosine_sim  # cosine_sim = 1.0 - distance
```

确保 `cosine_score` 是原始 cosine similarity（0-1 范围），不是转换后的 `1/(1+distance)`。

- [ ] **Step 3: 验证**

```bash
cd backend && python -c "
from app.rag.vector_store import retrieve
results = retrieve('RAG 检索', top_k=3)
for r in results:
    print(r.get('metadata', {}).get('cosine_score', 'MISSING'))
"
```

Expected: 每个结果打印一个 0-1 之间的浮点数。

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/vector_store.py
git commit -m "feat: store cosine_score in retrieval metadata for threshold filtering"
```

---

### Task 2: Negative Detection — 检索分数阈值过滤

**Why:** 当前 `_MIN_RELEVANCE_SCORE = 0.015` 形同虚设，RRF rank-1 得分 0.0164 轻松通过。需要在 RRF 融合前对各检索器设分数门槛。

**Files:**
- Modify: `backend/app/rag/qa_chain.py:40-68` (阈值定义 + hybrid_retrieve 函数)

- [ ] **Step 1: 添加环境变量阈值定义**

在 `qa_chain.py` 顶部（`_MIN_RELEVANCE_SCORE` 附近）添加：

```python
# Pre-RRF score thresholds: filter low-quality results before fusion
_VECTOR_MIN_COSINE = float(os.getenv("VECTOR_MIN_COSINE", "0.25"))
_BM25_MIN_RAW_SCORE = float(os.getenv("BM25_MIN_RAW_SCORE", "0.15"))
```

- [ ] **Step 2: 在 hybrid_retrieve 中 RRF 融合前插入过滤逻辑**

在 `hybrid_retrieve` 函数中，`bm25_results` 和 `vector_results` 获取之后、RRF 融合之前，插入：

```python
# ── Pre-RRF score filtering ──
# Filter vector results by cosine similarity threshold
if vector_results:
    filtered_vector = [
        r for r in vector_results
        if r.get("metadata", {}).get("cosine_score", 1.0) >= _VECTOR_MIN_COSINE
    ]
    if not filtered_vector and vector_results:
        logger.info(
            "All %d vector results below cosine threshold %.2f, degrading to BM25-only",
            len(vector_results), _VECTOR_MIN_COSINE,
        )
    vector_results = filtered_vector

# If both retrievers have no qualifying results → unanswerable
if not bm25_results and not vector_results:
    logger.info("No results from either retriever after threshold filtering")
    return []
```

- [ ] **Step 3: 运行 benchmark 验证**

```bash
cd backend && python tests/run_benchmark.py
```

Expected: `negative_detection_rate` 从 0.0 提升到 0.7+ (10/15+)。Recall@3 保持 ≥90%。

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat: add pre-RRF score thresholds for negative detection

Vector cosine < 0.25 and BM25 raw < 0.15 now filter before RRF fusion.
Unanswerable queries return empty results instead of hallucinated matches.
Env vars: VECTOR_MIN_COSINE, BM25_MIN_RAW_SCORE for tuning."
```

---

### Task 3: BM25 阈值提升

**Why:** `_KW_MIN_RAW_SCORE = 0.01` 过低，几乎所有 BM25 结果都能通过。提升到 0.15 配合 negative detection。

**Files:**
- Modify: `backend/app/rag/vector_store.py:73`

- [ ] **Step 1: 修改默认阈值**

```python
# 从
_KW_MIN_RAW_SCORE = 0.01
# 改为
_KW_MIN_RAW_SCORE = float(os.getenv("KW_MIN_RAW_SCORE", "0.15"))
```

- [ ] **Step 2: 验证 BM25 检索不受影响**

```bash
cd backend && python -c "
from app.rag.vector_store import retrieve_keyword
results = retrieve_keyword('RAG 检索系统', top_k=3)
print(f'Results: {len(results)}')
for r in results[:3]:
    print(f'  {r[\"metadata\"].get(\"slug\",\"?\")} score={r.get(\"score\",0):.4f}')
"
```

Expected: 正常查询仍有 3 个结果，分数 > 0.15。

- [ ] **Step 3: Commit**

```bash
git add backend/app/rag/vector_store.py
git commit -m "feat: raise BM25 min raw score threshold from 0.01 to 0.15"
```

---

### Task 4: Precision@3 修复 — 限制 vector 参与 + 置信度阈值

**Why:** BM25 Precision@3 = 65.85%，Hybrid = 31.3%。向量检索的无关结果通过 RRF 淹没 BM25 的正确结果。

**Files:**
- Modify: `backend/app/rag/qa_chain.py:96-104` (RRF 循环)

- [ ] **Step 1: 添加 vector 参与限制和置信度阈值**

在 `qa_chain.py` 顶部添加：

```python
_VECTOR_MAX_CONTRIB = int(os.getenv("VECTOR_MAX_CONTRIB", "3"))
_VECTOR_CONFIDENCE_THRESHOLD = float(os.getenv("VECTOR_CONFIDENCE_THRESHOLD", "0.60"))
```

- [ ] **Step 2: 修改 RRF 循环**

将 `hybrid_retrieve` 中的 vector RRF 循环从：

```python
for rank, doc in enumerate(vector_deduped, 1):
    key = _doc_key(doc)
    rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
```

改为：

```python
_vector_contrib_count = 0
for rank, doc in enumerate(vector_deduped, 1):
    if _vector_contrib_count >= _VECTOR_MAX_CONTRIB:
        break
    cosine = doc.get("metadata", {}).get("cosine_score", 1.0)
    if cosine < _VECTOR_CONFIDENCE_THRESHOLD:
        continue
    key = _doc_key(doc)
    rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
    if key not in doc_map:
        doc_map[key] = doc
    _vector_contrib_count += 1
```

- [ ] **Step 3: 同样修改 multi_query_retrieve 中的 RRF 循环**

`multi_query_retrieve` 函数（约 206 行）有独立的 RRF 循环，做相同修改。

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat: limit vector RRF contribution to top-3 with confidence threshold

VECTOR_MAX_CONTRIB=3 caps vector results in RRF fusion.
VECTOR_CONFIDENCE_THRESHOLD=0.60 skips low-confidence vector matches.
Expected: Precision@3 from 31% to 55-70%."
```

---

### Task 5: RRF_K 调大 + 环境变量化

**Why:** k=60 时 rank-1 (0.0164) ≈ rank-2 (0.0161)，差距仅 1.8%。k=200 让 BM25 的 10% bonus 更有决定性。

**Files:**
- Modify: `backend/app/rag/qa_chain.py:21`

- [ ] **Step 1: 修改 RRF_K 默认值**

```python
# 从
_RRF_K = 60
# 改为
_RRF_K = int(os.getenv("RRF_K", "200"))
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat: increase RRF_K from 60 to 200 to amplify BM25 bonus"
```

---

### Task 6: Phase 1 Benchmark 验证

**Why:** 验证所有 Phase 1 改动的综合效果，确保指标达标。

**Files:**
- Execute: `backend/tests/run_benchmark.py`
- Modify: `backend/data/benchmark_actual.json`
- Modify: `docs/benchmarks/recall-evaluation.md`

- [ ] **Step 1: 运行完整 benchmark**

```bash
cd backend && python tests/run_benchmark.py
```

- [ ] **Step 2: 检查指标**

验证：
- Recall@3 ≥ 93%
- Precision@3 ≥ 55%
- Negative Detection ≥ 70%
- Hybrid Latency ≤ 10ms

- [ ] **Step 3: 更新 benchmark 文档**

将结果同步到 `docs/benchmarks/recall-evaluation.md`。

- [ ] **Step 4: Commit**

```bash
git add backend/data/benchmark_actual.json docs/benchmarks/recall-evaluation.md
git commit -m "bench: update Phase 1 results — Precision@3 and Negative Detection improved"
```

---

## Phase 2: 功能补齐（P1）

### Task 7: 多 LLM 适配 — MODEL_REGISTRY + create_llm 扩展

**Why:** Portfolio 需要展示多 provider 能力。DeepSeek 兼容 OpenAI API，GPT-4o/Claude 需要各自的 SDK。

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/agent/llm.py`

- [ ] **Step 1: 在 config.py 添加 MODEL_REGISTRY**

在 `Settings` 类之后添加：

```python
MODEL_REGISTRY = {
    "deepseek-chat": {
        "provider": "deepseek",
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "api_key": settings.llm_api_key,
        "max_tokens": 8192,
    },
    "gpt-4o": {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",  # set via OPENAI_API_KEY env
        "max_tokens": 16384,
    },
    "claude-sonnet-4-20250514": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "base_url": "https://api.anthropic.com",
        "api_key": "",  # set via ANTHROPIC_API_KEY env
        "max_tokens": 8192,
    },
}
```

- [ ] **Step 2: 扩展 create_llm 支持 model 参数**

```python
def create_llm(model: str = None, **kwargs):
    """Factory: create ChatOpenAI instance. Supports DeepSeek/OpenAI/Anthropic via MODEL_REGISTRY."""
    from app.config import MODEL_REGISTRY
    
    if model and model in MODEL_REGISTRY:
        cfg = MODEL_REGISTRY[model]
        api_key = cfg["api_key"] or os.environ.get(f"{cfg['provider'].upper()}_API_KEY", "")
        if not api_key:
            raise ValueError(f"No API key for {model}. Set {cfg['provider'].upper()}_API_KEY.")
        return ChatOpenAI(
            model=cfg["model"],
            api_key=api_key,
            base_url=cfg["base_url"],
            temperature=kwargs.get("temperature", 0.7),
            streaming=kwargs.get("streaming", True),
            max_tokens=cfg["max_tokens"],
        )
    # Default: DeepSeek (existing behavior)
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=kwargs.get("temperature", 0.7),
        streaming=kwargs.get("streaming", True),
    )
```

- [ ] **Step 3: 验证默认行为不变**

```bash
cd backend && python -c "
from app.agent.llm import create_llm
llm = create_llm()
print(f'Default model: {llm.model_name}')
"
```

Expected: `deepseek-v4-flash`（行为不变）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/app/agent/llm.py
git commit -m "feat: add MODEL_REGISTRY for multi-LLM support (DeepSeek/OpenAI/Claude)"
```

---

### Task 8: Chat API 加 model 参数

**Why:** 前端需要能选择不同的 LLM model。

**Files:**
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/app/rag/qa_chain.py` (rag_query 接收 model 参数)

- [ ] **Step 1: 在 chat router 的请求体中添加 model 字段**

找到 chat/stream 端点的请求模型，添加 `model: Optional[str] = None`。

- [ ] **Step 2: 透传 model 到 LLM 调用**

将 `model` 参数从 API 端点传到 `create_llm(model=model)`。

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/chat.py backend/app/rag/qa_chain.py
git commit -m "feat: add model parameter to chat API endpoints"
```

---

### Task 9: Suggested Prompts — 后端端点

**Why:** 搜索页 UX 需要推荐查询引导用户。

**Files:**
- Modify: `backend/app/routers/rag.py`

- [ ] **Step 1: 添加 suggestions 端点**

在 `rag.py` 中添加：

```python
@router.get("/api/rag/suggestions")
async def get_suggestions():
    """Return suggested queries based on knowledge base topics."""
    suggestions = [
        {"query": "RAG 系统的检索管线是怎么设计的？", "category": "RAG"},
        {"query": "BM25 和向量检索各有什么优劣？", "category": "检索"},
        {"query": "LangGraph 和 LangChain LCEL 有什么区别？", "category": "框架"},
        {"query": "如何优化 RAG 系统的检索延迟？", "category": "性能"},
        {"query": "企业 AI 知识库部署有哪些注意事项？", "category": "部署"},
    ]
    return {"suggestions": suggestions}
```

- [ ] **Step 2: 测试端点**

```bash
cd backend && python -c "
import asyncio
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
r = client.get('/api/rag/suggestions')
print(r.status_code, r.json())
"
```

Expected: 200, 返回 5 个 suggestion。

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/rag.py
git commit -m "feat: add /api/rag/suggestions endpoint for search page"
```

---

### Task 10: Suggested Prompts — 前端 UI

**Why:** 搜索页展示推荐查询。

**Files:**
- Modify: `src/pages/Search.tsx`

- [ ] **Step 1: 添加 suggestions state 和 fetch**

在 `Search` 组件中添加：

```tsx
const [suggestions, setSuggestions] = useState<Array<{query: string; category: string}>>([]);

useEffect(() => {
  fetch('/api/rag/suggestions')
    .then(r => r.json())
    .then(d => setSuggestions(d.suggestions || []))
    .catch(() => {});
}, []);
```

- [ ] **Step 2: 渲染推荐查询**

在搜索框下方、结果区域之前添加：

```tsx
{suggestions.length > 0 && !answer && !isLoading && (
  <div className="flex flex-wrap gap-2 mt-4">
    {suggestions.map((s, i) => (
      <button
        key={i}
        onClick={() => { setQuery(s.query); }}
        className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-800 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition"
      >
        {s.query}
      </button>
    ))}
  </div>
)}
```

- [ ] **Step 3: 验证前端**

```bash
npm run dev
# 浏览器打开 http://localhost:5173/search，确认推荐查询显示
```

- [ ] **Step 4: Commit**

```bash
git add src/pages/Search.tsx
git commit -m "feat: add suggested prompts to search page"
```

---

### Task 11: SEO — Landing Page meta tags

**Why:** Landing Page 零 SEO 代码，搜索引擎无法索引。

**Files:**
- Modify: `index.html`

- [ ] **Step 1: 在 index.html <head> 中添加 meta tags**

```html
<meta name="description" content="Aureon — Enterprise AI Knowledge Base Platform. 96% retrieval accuracy, sub-second response, 24h deployment." />
<meta property="og:title" content="Aureon — Enterprise AI Knowledge Base" />
<meta property="og:description" content="Low-latency enterprise AI search and knowledge intelligence platform." />
<meta property="og:type" content="website" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="Aureon — Enterprise AI Knowledge Base" />
```

- [ ] **Step 2: 添加 JSON-LD 结构化数据**

在 `</head>` 前添加：

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Aureon",
  "applicationCategory": "BusinessApplication",
  "description": "Enterprise AI Knowledge Base Platform — 96% retrieval accuracy, sub-second response",
  "offers": {
    "@type": "Offer",
    "price": "500",
    "priceCurrency": "USD"
  }
}
</script>
```

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: add SEO meta tags and JSON-LD to landing page"
```

---

### Task 12: CrewAI 隐藏

**Why:** CrewAI 功能不完善，从导航菜单隐藏但保留代码。

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: 注释掉导航入口**

将第 42 行：
```tsx
{ path: "/crew", key: "app.nav.crew" },
```
改为：
```tsx
// { path: "/crew", key: "app.nav.crew" },  // hidden: CrewAI not production-ready
```

- [ ] **Step 2: 验证**

`npm run dev`，确认导航栏无 /crew 入口，但 `/crew` 路由仍可手动访问。

- [ ] **Step 3: Commit**

```bash
git add src/App.tsx
git commit -m "chore: hide CrewAI from navigation (code preserved)"
```

---

## Phase 3: 收尾

### Task 13: 目标.md 更新到 v20

**Files:**
- Modify: `目标.md`

- [ ] **Step 1: 更新版本号和更新日志**

在 `目标.md` 顶部更新 `version: "v20"`，添加 v20 更新日志，更新进度仪表盘中 RAG 质量和 P1 指标。

- [ ] **Step 2: Commit**

```bash
git add 目标.md
git commit -m "docs: update to v20 — RAG quality + P1 features"
```

---

## Execution Order

```
Task 1  (cosine_score metadata)     ← 无依赖
Task 2  (Negative Detection)        ← 依赖 Task 1
Task 3  (BM25 阈值)                 ← 无依赖，可与 Task 1 并行
Task 4  (Precision@3)               ← 依赖 Task 1
Task 5  (RRF_K)                     ← 无依赖，可并行
Task 6  (Benchmark 验证)            ← 依赖 Task 2-5
Task 7  (MODEL_REGISTRY)            ← 无依赖，可与 Phase 1 并行
Task 8  (Chat API model)            ← 依赖 Task 7
Task 9  (Suggestions 后端)          ← 无依赖
Task 10 (Suggestions 前端)          ← 依赖 Task 9
Task 11 (SEO)                       ← 无依赖
Task 12 (CrewAI 隐藏)              ← 无依赖
Task 13 (目标.md 更新)              ← 依赖 Task 6
```

Phase 1 (Task 1-6) 和 Phase 2 (Task 7-12) 可部分并行。
