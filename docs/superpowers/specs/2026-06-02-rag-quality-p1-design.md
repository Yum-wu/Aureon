# RAG 质量优化 + P1 功能补齐 设计文档

> **状态**：已批准  
> **日期**：2026-06-02  
> **版本**：v20  
> **范围**：RAG 质量修复（P0）+ 功能补齐（P1）+ 清理（P2）

---

## 一、问题诊断

### 1.1 Negative Detection = 0%

**根因**：`_MIN_RELEVANCE_SCORE = 0.015` 形同虚设。RRF k=60 时 rank-1 得分 = 1/61 = 0.0164，任何检索结果都能通过这个门槛。15 个不可回答查询全部返回 3 个结果。

**代码位置**：`backend/app/rag/qa_chain.py:42`

### 1.2 Precision@3 = 31.3%（BM25 单独 = 65.85%）

**根因**：RRF 是 rank-based 融合，vector rank-1（0.0164）≈ BM25 rank-2（0.0177）。向量检索的无关结果获得与 BM25 正确结果几乎相同的 RRF 分数，将 Precision 从 65% 拖到 31%。

**代码位置**：`backend/app/rag/qa_chain.py:97-104`

### 1.3 其他问题

| 问题 | 现状 | 影响 |
|------|------|------|
| 多 LLM 适配 | 仅 DeepSeek | Portfolio 缺少多 provider 展示 |
| SEO | 零代码 | Landing Page 无法被搜索引擎索引 |
| Suggested Prompts | 未实现 | 搜索页 UX 空白 |
| CrewAI | 有代码但隐藏 | /crew 路由存在但可能不工作 |
| Railway 持久化 | startup 自动重建 | 每次部署冷启动 30-60s |

---

## 二、方案设计

### 2.1 P0：Negative Detection 修复

**策略**：在 RRF 融合**之前**对各检索器设分数门槛，双信号判定。

#### 实现

```python
# qa_chain.py — hybrid_retrieve 函数中，RRF 融合前插入

# Score thresholds: filter before RRF fusion
_VECTOR_MIN_COSINE = float(os.getenv("VECTOR_MIN_COSINE", "0.25"))
_BM25_MIN_RAW_SCORE = float(os.getenv("BM25_MIN_RAW_SCORE", "0.15"))

# Filter vector results by cosine similarity
if vector_results:
    filtered_vector = [
        r for r in vector_results
        if r.get("metadata", {}).get("cosine_score", 1.0) >= _VECTOR_MIN_COSINE
    ]
    if not filtered_vector:
        logger.info("All vector results below cosine threshold %.2f, degrading to BM25-only", _VECTOR_MIN_COSINE)
    vector_results = filtered_vector

# If both empty after filtering → unanswerable
if not bm25_results and not vector_results:
    return []
```

#### 关键值

| 信号 | 阈值 | 来源 | 环境变量 |
|------|------|------|---------|
| Vector cosine similarity | ≥ 0.25 | BGE-small-zh 在 476 chunks 上的实验 | `VECTOR_MIN_COSINE` |
| BM25 raw score | ≥ 0.15 | jieba 分词后关键词重叠判定 | `BM25_MIN_RAW_SCORE` |
| RRF 融合后 | 保留 0.015 | 安全网，仅兜底 | `MIN_RELEVANCE_SCORE` |

#### 预期效果

- Negative Detection：0% → 80%+（部分边界情况仍需系统 prompt 兜底）
- Recall@3：基本不受影响（被过滤的 vector 结果本就是噪音）
- 延迟：零增加（纯数值比较）

#### 降级策略

环境变量可快速回滚：`VECTOR_MIN_COSINE=0.0` + `BM25_MIN_RAW_SCORE=0.01` 恢复原行为。

---

### 2.2 P0：Precision@3 修复

**策略**：限制 vector 参与 RRF 的数量 + 向量分数阈值过滤。

#### 分步实施

**Step 1**：限制 vector 参与数量

```python
# qa_chain.py — RRF 循环处
VECTOR_MAX_CONTRIB = int(os.getenv("VECTOR_MAX_CONTRIB", "3"))

for rank, doc in enumerate(vector_deduped[:VECTOR_MAX_CONTRIB], 1):  # 只取前 3
    key = _doc_key(doc)
    rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
```

预期：Precision@3 31% → 45-55%

**Step 2**：加向量置信度阈值（叠加 Step 1）

```python
_VECTOR_CONFIDENCE_THRESHOLD = float(os.getenv("VECTOR_CONFIDENCE_THRESHOLD", "0.60"))

# 在 RRF 循环中
for rank, doc in enumerate(vector_deduped[:VECTOR_MAX_CONTRIB], 1):
    cosine = doc.get("metadata", {}).get("cosine_score", 1.0)
    if cosine < _VECTOR_CONFIDENCE_THRESHOLD:
        continue  # 跳过低置信度结果
```

预期：Precision@3 → 55-70%

**Step 3**：调整 RRF k 值（可选微调）

```python
_RRF_K = int(os.getenv("RRF_K", "200"))  # 从 60 改到 200
```

效果：放大 BM25 的 10% bonus 影响力（rank-1 vs rank-5 差距从 7.7% 缩到 1.9%，bonus 更有决定性）。

#### 环境变量汇总

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VECTOR_MAX_CONTRIB` | 3 | vector 参与 RRF 的最大结果数 |
| `VECTOR_CONFIDENCE_THRESHOLD` | 0.60 | cosine 低于此值的 vector 结果不参与 |
| `RRF_K` | 200 | RRF 常数 k，越大 BM25 bonus 影响越大 |

#### 预期效果

- Precision@3：31% → 60-70%
- Recall@3：可能微降 1-2%（被过滤的 vector 结果偶尔是对的）
- 延迟：零增加

---

### 2.3 P0：BM25 阈值提升

```python
# vector_store.py
_KW_MIN_RAW_SCORE = float(os.getenv("KW_MIN_RAW_SCORE", "0.15"))  # 从 0.01 提升
```

配合 2.1 的 negative detection 形成完整过滤链。

---

### 2.4 P1：多 LLM 适配

**目标**：支持 DeepSeek / GPT-4o / Claude，Portfolio 展示多 provider 能力。

#### 架构

```python
# backend/app/config.py — 新增 MODEL_REGISTRY
MODEL_REGISTRY = {
    "deepseek-chat": {
        "provider": "deepseek",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.00014,
        "cost_per_1k_output": 0.00028,
    },
    "gpt-4o": {
        "provider": "openai",
        "max_tokens": 16384,
        "cost_per_1k_input": 0.0025,
        "cost_per_1k_output": 0.01,
    },
    "claude-sonnet-4-20250514": {
        "provider": "anthropic",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
    },
}
```

#### 改动范围

| 文件 | 改动 |
|------|------|
| `backend/app/config.py` | 新增 MODEL_REGISTRY |
| `backend/app/rag/llm.py` | `create_llm()` → `init_chat_model` + registry 查询 |
| `backend/app/rag/qa_chain.py` | 接收 model 参数透传 |
| `backend/app/routers/chat.py` | API 端点加 `model` 参数 |
| `src/services/` | 前端加 model 选择器（可选） |

#### 不改动

- `streaming.py` — LangChain `.astream()` 已抹平 SSE 差异
- `qa_chain.py` 的 RAG 逻辑 — 只改 LLM 调用入口

---

### 2.5 P1：Suggested Prompts

**实现**：搜索页加载时从后端获取推荐查询。

#### 后端

```python
# backend/app/routers/rag.py — 新增端点
@router.get("/api/rag/suggestions")
async def get_suggestions():
    """返回基于知识库主题的推荐查询"""
    # 方案 1：静态列表（从知识库文章标题提取）
    # 方案 2：基于热门查询历史
    return {"suggestions": [...]}
```

#### 前端

```tsx
// src/pages/Search.tsx — 加载推荐
useEffect(() => {
  fetch('/api/rag/suggestions').then(r => r.json()).then(setSuggestions);
}, []);
```

推荐查询来源（按优先级）：
1. 知识库文章标题改写的自然语言问题（静态，写入代码）
2. 用户历史热门查询（动态，需 Redis 查询统计）

---

### 2.6 P1：SEO 优化

#### Landing Page

```tsx
// src/pages/Landing.tsx — 添加 meta tags
<Helmet>
  <title>Aureon — Enterprise AI Knowledge Base Platform</title>
  <meta name="description" content="96% retrieval accuracy, sub-second response, 24h deployment. Enterprise AI search and knowledge intelligence." />
  <meta property="og:title" content="Aureon — Enterprise AI Knowledge Base" />
  <meta property="og:description" content="..." />
  <meta property="og:image" content="/og-image.png" />
  <meta property="og:type" content="website" />
</Helmet>
```

#### 结构化数据

```json
// JSON-LD for Landing Page
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Aureon",
  "applicationCategory": "BusinessApplication",
  "description": "Enterprise AI Knowledge Base Platform"
}
```

#### 改动范围

- `src/pages/Landing.tsx` — meta tags + JSON-LD
- `index.html` — 默认 meta tags
- 新增 `react-helmet-async` 依赖（或直接在 index.html 中写死）

---

### 2.7 P1：CrewAI 隐藏

从导航菜单移除 `/crew` 入口，代码保留。

#### 改动

```tsx
// src/App.tsx — 注释掉 /crew 路由条目
// { path: "/crew", key: "app.nav.crew" },  // hidden: CrewAI not production-ready
```

不删除代码、不删除后端端点。用户手动访问 `/crew` 仍可使用。

---

### 2.8 P1：Railway Volume 持久化

#### 方案

Railway 支持 Volume 挂载。在 `railway.toml` 或 Dashboard 中配置：

```toml
[[volume]]
mountPath = "/app/data/chroma"
name = "chroma-persist"
```

#### 改动

- `backend/app/rag/vector_store.py` — ChromaDB persist 目录改为 `/app/data/chroma`（通过环境变量 `CHROMA_PERSIST_DIR` 控制）
- Railway Dashboard — 创建 Volume 并挂载
- 移除 startup 自动重建逻辑（或改为仅首次启动时触发）

---

## 三、实施顺序

```
Phase 1: RAG 质量（P0）
├── A1. Negative Detection 修复（qa_chain.py 阈值过滤）
├── A2. Precision@3 修复（VECTOR_MAX_CONTRIB + VECTOR_CONFIDENCE_THRESHOLD）
├── A3. BM25 阈值提升
└── A4. 跑 benchmark 验证

Phase 2: 功能补齐（P1）
├── B1. 多 LLM 适配（config + llm.py + API）
├── B2. Suggested Prompts（后端端点 + 前端）
├── B3. SEO（meta tags + JSON-LD）
├── B4. CrewAI 隐藏
└── B5. Railway Volume

Phase 3: 收尾
├── 目标.md 更新到 v20
├── benchmark 文档同步
└── Memory 更新
```

---

## 四、验收标准

### Phase 1

| 指标 | 当前 | 目标 | 测试方法 |
|------|------|------|---------|
| Recall@3 | 93.9% | ≥93%（允许微降） | `run_benchmark.py` |
| Precision@3 | 31.3% | ≥60% | `run_benchmark.py` |
| Negative Detection | 0% | ≥80% | 15 个负面查询 |
| Hybrid Latency | 4.9ms | ≤10ms | `run_benchmark.py` |

### Phase 2

- [ ] 多 LLM：GPT-4o 和 Claude 能正常流式响应
- [ ] Suggested Prompts：搜索页显示 3-5 个推荐查询
- [ ] SEO：Landing Page meta tags 正确渲染
- [ ] CrewAI：导航菜单无 /crew 入口
- [ ] Railway Volume：重新部署后索引不丢失

---

## 五、风险与降级

| 风险 | 影响 | 降级方案 |
|------|------|---------|
| 向量阈值过滤导致 Recall 下降 | 检索质量降低 | 环境变量快速回滚阈值 |
| RRF_K 调大破坏现有排序 | Precision/Recall 双降 | 默认值保持 60 |
| GPT-4o/Claude prompt 不兼容 | 回答质量下降 | 保持 DeepSeek 为默认 |
| Railway Volume 配置错误 | 部署失败 | 保持自动重建兜底 |

所有阈值均可通过环境变量调整，无需改代码回滚。

---

*设计文档版本: v1*  
*最后更新: 2026-06-02*
