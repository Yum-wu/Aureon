# Aureon Railway + HuggingFace Spaces 微服务架构方案

> 日期：2026-06-09
> 状态：✅ 已实施（DashScope API 方案）
> 作者：Aureon Team

---

## 0. 实施结论

> **最终方案：DashScope API 全量接管（2026-06-10）**
>
> - Embedding: DashScope `text-embedding-v4` (768d, Singapore compatible-mode endpoint)
> - Reranker: DashScope `qwen3-rerank` (compatible-api endpoint)
> - 向量库: Qdrant Cloud (Australia Southeast, free tier)
> - `SKIP_LOCAL_EMBED=true` + `RERANK_BACKEND=api` → Railway 上零本地模型加载，释放 ~1.5GB 内存
> - 语义缓存降级为精确匹配（`SKIP_LOCAL_EMBED=true` 时跳过本地 BGE embedding）
>
> 原 SiliconFlow P0 方案未采用，DashScope 连通性和质量均优于预期。

---

## 1. 问题背景

### 1.1 当前 Railway 部署状态

| 功能 | 状态 | 说明 |
|------|------|------|
| Health API | ✅ 正常 | `/api/health` 200 |
| Chat API | ✅ 正常 | DeepSeek 流式响应 |
| WebSocket | ✅ 正常 | 实时聊天 |
| RAG 查询 | ❌ 不可用 | Embedding API 不可达 + CrossEncoder OOM |
| 语义缓存 | ⚠️ 降级 | 仅精确匹配，跳过语义向量 |

### 1.2 根本原因

```
Railway Free Tier: 512MB RAM
├── nginx: ~10MB
├── uvicorn + FastAPI: ~100MB
├── BM25 索引 (476 chunks): ~20MB
├── Redis 连接: ~5MB
├── 其他依赖: ~50MB
└── 剩余: ~335MB

需要的模型内存:
├── BAAI/bge-large-zh-v1.5 (Embedding): ~1.3GB  ← OOM
├── BAAI/bge-reranker-v2-m3 (Reranking): ~2.2GB  ← OOM
└── 总计: ~3.5GB  ← 远超 512MB 限制
```

**结论：Railway Free Tier 无法运行本地 ML 模型。**

### 1.3 额外问题：DashScope API 不可达

即使跳过本地模型，使用 DashScope API 做 embedding 也失败：
- `Connection reset by peer`（连接被重置）
- `SSL UNEXPECTED_EOF_WHILE_READING`（SSL 握手失败）
- `Read timeout 90s`（读取超时）

原因：Railway 亚太节点到阿里云 DashScope 的网络链路不稳定。

---

## 2. 架构方案

### 2.1 目标架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户浏览器                              │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Railway: API Server (512MB, $0)                         │
│                                                         │
│  nginx → uvicorn                                        │
│  ├── Chat API ──────────────▶ DeepSeek API              │
│  ├── WebSocket                                            │
│  ├── BM25 检索 (内存)                                      │
│  ├── 语义缓存 (Redis)                                     │
│  └── RAG Pipeline                                        │
│        ├── ① Embedding ─────▶ SiliconFlow API (免费)      │
│        ├── ② 向量检索 ───────▶ Qdrant (本地 volume)       │
│        ├── ③ Reranking ─────▶ SiliconFlow API (免费)      │
│        └── ④ LLM 生成 ──────▶ DeepSeek API              │
└─────────────────────────────────────────────────────────┘

备用方案（本地模型推理）:

┌─────────────────────────────────────────────────────────┐
│  HuggingFace Spaces: Model Server (16GB RAM, $0)         │
│                                                         │
│  Gradio API Server                                      │
│  ├── BAAI/bge-large-zh-v1.5 (Embedding, ~1.3GB)         │
│  └── BAAI/bge-reranker-v2-m3 (Reranking, ~2.2GB)        │
│                                                         │
│  POST /api/embed   → 返回向量                             │
│  POST /api/rerank  → 返回重排结果                          │
│  GET  /api/health  → 健康检查                             │
└─────────────────────────────────────────────────────────┘
```

### 2.2 推荐优先级

| 优先级 | 方案 | 成本 | 延迟 | 可靠性 | 实施难度 |
|--------|------|------|------|--------|----------|
| **P0** | SiliconFlow API（embedding + reranking） | 免费 | 100-300ms | 中等 | ⭐ 最简单 |
| **P1** | HuggingFace Spaces（本地模型） | 免费 | 50-500ms | 中等 | ⭐⭐ 中等 |
| **P2** | Modal（GPU 推理） | $30 免费额度 | 50-200ms | 高 | ⭐⭐⭐ 较高 |

**建议：先实施 P0（SiliconFlow API），10 分钟内让 RAG 工作。P1 作为备用方案。**

---

## 3. SiliconFlow 模型分析

### 3.1 Aureon 需要的三个模型

| 用途 | 当前模型 | 问题 | SiliconFlow 替代 |
|------|----------|------|------------------|
| Embedding | BAAI/bge-large-zh-v1.5 | 本地加载 OOM | Qwen3-Embedding-8B 或 bge-m3 |
| Reranking | BAAI/bge-reranker-v2-m3 | 本地加载 OOM | Qwen3-Reranker-8B 或 bge-reranker-v2-m3 |
| LLM | DeepSeek V4 Flash | 正常但可优化 | Qwen3-30B-A3B 或 Qwen3-32B |

### 3.2 Embedding 模型对比

| 模型 | 参数量 | 维度 | 最大 Token | 中文优化 | 免费 | 推荐度 |
|------|--------|------|-----------|----------|------|--------|
| **Qwen3-Embedding-8B** | 8B | 未确认 | 未确认 | ✅ | 待确认 | ⭐⭐⭐⭐⭐ |
| **BAAI/bge-m3** | 0.5B | 1024 | **8192** | ✅ | ✅ 免费 | ⭐⭐⭐⭐ |
| BAAI/bge-large-zh-v1.5 | 0.3B | 1024 | 512 | ✅ | ✅ 免费 | ⭐⭐⭐ |
| Qwen3-Embedding-4B | 4B | 未确认 | 未确认 | ✅ | 待确认 | ⭐⭐⭐⭐ |
| Qwen3-Embedding-0.6B | 0.6B | 未确认 | 未确认 | ✅ | 待确认 | ⭐⭐⭐ |

**推荐选择：BAAI/bge-m3**

理由：
- ✅ 确认免费
- ✅ 8192 token 上下文（bge-large 只有 512）
- ✅ 支持 dense + sparse + multi-vector 检索
- ✅ 100+ 语言支持（未来扩展英文内容）
- ⚠️ 1024 维度（与当前索引兼容）
- 🔄 需要重建向量索引（维度可能不同）

**如果 bge-m3 维度不兼容，退回 bge-large-zh-v1.5（完全兼容）。**

### 3.3 Reranking 模型对比

| 模型 | 参数量 | 中文优化 | 免费 | 推荐度 |
|------|--------|----------|------|--------|
| **Qwen3-Reranker-8B** | 8B | ✅ | 待确认 | ⭐⭐⭐⭐⭐ |
| **BAAI/bge-reranker-v2-m3** | 0.5B | ✅ | 待确认 | ⭐⭐⭐⭐ |
| Qwen3-Reranker-4B | 4B | ✅ | 待确认 | ⭐⭐⭐⭐ |
| Qwen3-Reranker-0.6B | 0.6B | ✅ | 待确认 | ⭐⭐⭐ |

**推荐选择：Qwen3-Reranker-8B（如果免费）或 bge-reranker-v2-m3（确认可用）**

理由：
- Qwen3-Reranker-8B 是最新模型，质量最高
- bge-reranker-v2-m3 已经过验证，稳定可靠
- 两者都通过 SiliconFlow 的 `/v1/rerank` API 调用

### 3.4 LLM 模型对比（用于 RAG 生成）

| 模型 | 参数量 | 类型 | 中文质量 | 推理速度 | 价格 | 推荐度 |
|------|--------|------|----------|----------|------|--------|
| **Qwen3-30B-A3B** | 30B(3B 激活) | MoE | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 低 | ⭐⭐⭐⭐⭐ |
| **Qwen3-32B** | 32B | Dense | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 中 | ⭐⭐⭐⭐ |
| DeepSeek-V3/V3.2 | 671B(37B 激活) | MoE | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | ⭐⭐⭐⭐ |
| DeepSeek-R1 | 671B | MoE | ⭐⭐⭐⭐⭐ | ⭐⭐ | 高 | ⭐⭐⭐ |
| Qwen3-14B | 14B | Dense | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 低 | ⭐⭐⭐⭐ |
| Qwen2.5-72B | 72B | Dense | ⭐⭐⭐⭐⭐ | ⭐⭐ | 高 | ⭐⭐⭐ |

**推荐选择：Qwen3-30B-A3B（主）+ DeepSeek-V3（备）**

理由：
- **Qwen3-30B-A3B**：MoE 架构，总参数 30B 但每次只激活 3B，推理极快
  - 适合 RAG 场景：需要快速生成答案，不需要深度推理
  - 中文质量好，Qwen3 系列最新
  - 价格低（激活参数少 = 计算成本低）

- **DeepSeek-V3**：保留作为 fallback
  - 已验证可用
  - 质量最高
  - 作为 Qwen3 不可用时的备选

- **Qwen3-32B**：适合需要复杂推理的场景（可选）
  - 支持 thinking 模式（类似 o1）
  - 适合 "分析 XXX 的优缺点" 这类复杂问题
  - 可作为"高级模式"可选

### 3.5 延迟对比：SiliconFlow vs DeepSeek

| 指标 | DeepSeek 直连 | SiliconFlow | 说明 |
|------|--------------|-------------|------|
| TTFT (首 token 延迟) | 0.3-1.0s | 0.5-2.0s | DeepSeek 自家基础设施更快 |
| 输出速度 | 40-80 tok/s | 30-60 tok/s | 取决于模型和负载 |
| Embedding 延迟 | N/A (DeepSeek 不提供) | 50-200ms | SiliconFlow 有 Embedding API |
| Reranking 延迟 | N/A (DeepSeek 不提供) | 100-500ms | SiliconFlow 有 Rerank API |
| 可用性 | 偶尔过载 | 华为云基础设施 | SiliconFlow 在国内更稳定 |
| 价格 | 最低 | 略高 10-30% | SiliconFlow 有免费模型抵消 |

**结论：**
- LLM 延迟：DeepSeek 直连略快（100-300ms 差距），但 SiliconFlow 可接受
- **核心优势：SiliconFlow 同时提供 Embedding + Reranking + LLM**，一个 API key 解决三个需求
- 国内访问：SiliconFlow（华为云）可能比 DeepSeek API 更稳定

---

## 4. 实施方案

### 4.1 Phase 1：SiliconFlow API 集成（30 分钟）

**目标：用 SiliconFlow API 替代本地模型，立即让 RAG 工作。**

#### 步骤 1：注册 SiliconFlow 并获取 API Key

```bash
# 1. 访问 https://cloud.siliconflow.cn/ 注册
# 2. 新用户获得 ~14 RMB 免费额度
# 3. 在 API Keys 页面创建 key
```

#### 步骤 2：Railway 添加环境变量

```bash
railway variables set SILICONFLOW_API_KEY=sk-xxxxxxxx
```

#### 步骤 3：添加 SiliconFlow 客户端

创建 `backend/app/rag/siliconflow_client.py`：

```python
"""SiliconFlow API client for embedding and reranking."""

import os
import json
import httpx
import structlog
import numpy as np
from typing import List, Dict, Any, Optional

logger = structlog.get_logger()

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

_client: Optional[httpx.AsyncClient] = None

def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client

def _get_api_key() -> str:
    return os.environ.get("SILICONFLOW_API_KEY", "")


async def embed_texts(texts: List[str], model: str = "BAAI/bge-large-zh-v1.5") -> np.ndarray:
    """Embed texts using SiliconFlow API.
    
    OpenAI-compatible /v1/embeddings endpoint.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("SILICONFLOW_API_KEY not configured")
    
    client = _get_client()
    resp = await client.post(
        f"{SILICONFLOW_BASE_URL}/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": texts,
            "encoding_format": "float",
        },
    )
    resp.raise_for_status()
    
    data = resp.json()["data"]
    # Sort by index to maintain order
    embeddings = [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]
    return np.array(embeddings, dtype=np.float32)


async def rerank(
    query: str,
    documents: List[str],
    model: str = "BAAI/bge-reranker-v2-m3",
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Rerank documents using SiliconFlow API.
    
    Cohere-compatible /v1/rerank endpoint.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("SILICONFLOW_API_KEY not configured")
    
    client = _get_client()
    resp = await client.post(
        f"{SILICONFLOW_BASE_URL}/rerank",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "return_documents": True,
        },
    )
    resp.raise_for_status()
    
    results = resp.json()["results"]
    return [
        {
            "text": r["document"]["text"] if "document" in r else documents[r["index"]],
            "score": r["relevance_score"],
            "index": r["index"],
        }
        for r in results
    ]
```

#### 步骤 4：修改 RAG Pipeline

修改 `backend/app/rag/vector_store.py`，在 DashScope 失败时 fallback 到 SiliconFlow：

```python
# 在 embed_texts_llm() 的 API fallback chain 中添加：

# 4. SiliconFlow fallback
if embeddings is None:
    try:
        from app.rag.siliconflow_client import embed_texts
        embeddings = await embed_texts(uncached_texts)
        logger.info("Embedding via SiliconFlow: %d texts, dim=%d", len(texts), embeddings.shape[1])
    except Exception as e:
        logger.warning("SiliconFlow embedding failed: %s", e)

# 修改 rerank() 函数，使用 SiliconFlow API：
async def rerank_api(query: str, chunks: List[Dict], top_k: int = 3) -> List[Dict]:
    """Rerank using SiliconFlow API (remote CrossEncoder)."""
    from app.rag.siliconflow_client import rerank
    
    docs = [c["text"] for c in chunks]
    results = await rerank(query, docs, top_n=min(len(docs), top_k * 3))
    
    # 重建 chunks 顺序
    result_map = {r["text"]: r["score"] for r in results}
    for chunk in chunks:
        chunk["rerank_score"] = result_map.get(chunk["text"], 0.0)
    
    return sorted(chunks, key=lambda x: x.get("rerank_score", 0), reverse=True)[:top_k]
```

#### 步骤 5：测试

```bash
# 本地测试
export SILICONFLOW_API_KEY=sk-xxxxxxxx
cd backend && uvicorn app.main:app --reload --port 8000

# 测试 embedding
curl -X POST http://localhost:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是 RAG"}'

# 测试 reranking
python -c "
import asyncio
from app.rag.siliconflow_client import rerank
result = asyncio.run(rerank('什么是 RAG', ['文档1', '文档2', '文档3']))
print(result)
"
```

### 4.2 Phase 2：HuggingFace Spaces 模型服务（备用方案，1 小时）

**目标：当 SiliconFlow API 不可用时，使用 HF Spaces 运行本地模型。**

#### HF Spaces 项目结构

```
hf-model-server/
├── app.py              # Gradio 主应用
├── requirements.txt
├── README.md           # HF Spaces 配置
└── Dockerfile          # 可选，自定义构建
```

**app.py**：

```python
import gradio as gr
import numpy as np
import json
import time
import logging

logger = logging.getLogger(__name__)

# ── 全局模型单例 ──
_embedder = None
_reranker = None

def _load_embedder():
    global _embedder
    if _embedder is None:
        logger.info("Loading BAAI/bge-large-zh-v1.5 ...")
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("BAAI/bge-large-zh-v1.5")
        logger.info("Embedder loaded")

def _load_reranker():
    global _reranker
    if _reranker is None:
        logger.info("Loading BAAI/bge-reranker-v2-m3 ...")
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
        logger.info("Reranker loaded")

# ── API 端点 ──

def embed(texts_json: str) -> str:
    """Embed texts. Input: JSON array of strings. Output: JSON 2D array."""
    _load_embedder()
    texts = json.loads(texts_json)
    if not isinstance(texts, list):
        texts = [texts]
    
    start = time.time()
    vectors = _embedder.encode(texts, normalize_embeddings=True, batch_size=32)
    elapsed = int((time.time() - start) * 1000)
    logger.info("Embedded %d texts in %dms", len(texts), elapsed)
    
    return json.dumps(vectors.tolist())

def rerank(query: str, documents_json: str, top_k: int = 5) -> str:
    """Rerank documents. Output: JSON array of {text, score}."""
    _load_reranker()
    docs = json.loads(documents_json)
    if not isinstance(docs, list):
        docs = [docs]
    
    start = time.time()
    pairs = [(query, doc) for doc in docs]
    scores = _reranker.predict(pairs)
    elapsed = int((time.time() - start) * 1000)
    
    ranked = sorted(zip(docs, scores), key=lambda x: -float(x[1]))
    results = [{"text": doc, "score": float(score)} for doc, score in ranked[:top_k]]
    logger.info("Reranked %d docs in %dms", len(docs), elapsed)
    
    return json.dumps(results)

def health() -> str:
    return json.dumps({
        "status": "ok",
        "embedder": _embedder is not None,
        "reranker": _reranker is not None,
    })

# ── 启动时预加载 ──
_load_embedder()
_load_reranker()

# ── Gradio UI ──
with gr.Blocks(title="Aureon Model Server") as demo:
    gr.Markdown("# Aureon Model Server (Embedding + Reranking)")
    
    with gr.Tab("Health"):
        gr.Button("Check").click(fn=health, outputs=gr.Textbox())
    
    with gr.Tab("Embed"):
        inp = gr.Textbox(label="Texts (JSON)", placeholder='["text1"]')
        out = gr.Textbox(label="Embeddings")
        gr.Button("Embed").click(fn=embed, inputs=inp, outputs=out)
    
    with gr.Tab("Rerank"):
        q = gr.Textbox(label="Query")
        d = gr.Textbox(label="Documents (JSON)")
        k = gr.Slider(1, 20, value=5, label="Top K")
        out = gr.Textbox(label="Results")
        gr.Button("Rerank").click(fn=rerank, inputs=[q, d, k], outputs=out)

demo.launch()
```

**requirements.txt**：

```
sentence-transformers>=3.0.0
gradio>=4.0.0
numpy
```

**README.md**：

```yaml
---
title: Aureon Model Server
emoji: 🧠
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: apache-2.0
---
```

#### 部署命令

```bash
# 1. 安装 HF CLI
pip install huggingface_hub

# 2. 登录
huggingface-cli login

# 3. 创建 Space
huggingface-cli repo create aureon-model-server --type space --space-sdk gradio

# 4. 推送代码
cd hf-model-server
git init
git remote add hf https://huggingface.co/spaces/<your-username>/aureon-model-server
git add .
git commit -m "Initial: Aureon model server with embedding + reranking"
git push hf main

# 5. 等待构建完成（3-5 分钟）
# 访问 https://<your-username>-aureon-model-server.hf.space
```

### 4.3 Phase 3：LLM 模型优化（可选，按需）

**如果想用 Qwen3 替代或补充 DeepSeek：**

修改 `backend/app/agent/llm.py`：

```python
# 添加 Qwen3-30B-A3B 作为可选 LLM
QWEN3_MODELS = {
    "qwen3-30b-a3b": {
        "model": "Qwen/Qwen3-30B-A3B-Instruct",
        "base_url": "https://api.siliconflow.cn/v1",
    },
    "qwen3-32b": {
        "model": "Qwen/Qwen3-32B",
        "base_url": "https://api.siliconflow.cn/v1",
    },
    "qwen3-14b": {
        "model": "Qwen/Qwen3-14B",
        "base_url": "https://api.siliconflow.cn/v1",
    },
}

# 用户可通过 model 参数选择
# 例如: {"model": "qwen3-30b-a3b", "message": "..."}
```

---

## 5. 决策矩阵

### 5.1 Embedding 模型选择

| 场景 | 推荐 | 理由 |
|------|------|------|
| **立即可用** | BAAI/bge-large-zh-v1.5 (SiliconFlow) | 免费，与现有索引兼容 |
| **最佳质量** | Qwen3-Embedding-8B (SiliconFlow) | 最新 8B 模型，质量最高 |
| **最长上下文** | BAAI/bge-m3 (SiliconFlow) | 8192 token，多语言 |
| **HF Spaces 部署** | BAAI/bge-large-zh-v1.5 (本地) | 1.3GB，16GB RAM 够用 |

### 5.2 Reranking 模型选择

| 场景 | 推荐 | 理由 |
|------|------|------|
| **立即可用** | BAAI/bge-reranker-v2-m3 (SiliconFlow) | 已验证，Cohere 兼容 API |
| **最佳质量** | Qwen3-Reranker-8B (SiliconFlow) | 最新 8B 模型 |
| **HF Spaces 部署** | BAAI/bge-reranker-v2-m3 (本地) | 2.2GB，16GB RAM 够用 |

### 5.3 LLM 模型选择

| 场景 | 推荐 | 理由 |
|------|------|------|
| **当前方案** | DeepSeek V4 Flash (直连) | 最低延迟，已验证 |
| **性价比** | Qwen3-30B-A3B (SiliconFlow) | MoE 快速，中文好 |
| **最高质量** | Qwen3-32B (SiliconFlow) | 支持 thinking 模式 |
| **复杂推理** | DeepSeek-R1 (SiliconFlow) | 最强推理，但慢 |

---

## 6. 延迟估算

### 6.1 当前方案（本地模型，已 OOM）

```
用户查询 → BM25(10ms) + Embedding(本地, OOM) + 向量检索(10ms) + Rerank(本地, OOM) + LLM(2s)
总计: 不可用
```

### 6.2 SiliconFlow API 方案（推荐）

```
用户查询
  ├── BM25 检索: ~10ms (内存)
  ├── Embedding (SiliconFlow API): ~100-200ms
  ├── 向量检索 (Qdrant): ~10-20ms
  ├── Reranking (SiliconFlow API): ~200-400ms
  └── LLM 生成 (DeepSeek): ~1500-3000ms
  
总计: ~2-4 秒（可接受）
```

### 6.3 HF Spaces 方案（备用）

```
用户查询
  ├── BM25 检索: ~10ms
  ├── Embedding (HF Spaces CPU): ~200-500ms (含网络)
  ├── 向量检索: ~10-20ms
  ├── Reranking (HF Spaces CPU): ~300-800ms (含网络)
  └── LLM 生成 (DeepSeek): ~1500-3000ms
  
总计: ~2.5-5 秒（首次冷启动 +1-2 分钟）
```

---

## 7. 成本分析

### 7.1 当前月度成本

| 服务 | 费用 | 说明 |
|------|------|------|
| Railway | $0 | Free tier |
| DeepSeek API | ~¥0.001/query | ~¥0.1/1000 次 |
| DashScope | ¥0 (不可用) | Embedding 失败 |
| **总计** | **~¥0.1/1000 次** | 仅 Chat 工作 |

### 7.2 SiliconFlow 方案月度成本

| 服务 | 费用 | 说明 |
|------|------|------|
| Railway | $0 | Free tier |
| SiliconFlow Embedding | **¥0** | bge-large-zh-v1.5 免费 |
| SiliconFlow Reranking | **待确认** | bge-reranker-v2-m3 可能免费 |
| SiliconFlow LLM (备选) | ~¥0.002/query | Qwen3-30B-A3B |
| DeepSeek API (主 LLM) | ~¥0.001/query | 保持不变 |
| **总计** | **~¥0.1-0.3/1000 次** | Embedding 免费是关键 |

### 7.3 HF Spaces 方案月度成本

| 服务 | 费用 | 说明 |
|------|------|------|
| Railway | $0 | Free tier |
| HF Spaces CPU | **$0** | 16GB RAM 免费 |
| DeepSeek API | ~¥0.001/query | 不变 |
| **总计** | **~¥0.1/1000 次** | 全免费 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| SiliconFlow API 限流 | RAG 查询失败 | 实现重试 + 降级到 HF Spaces |
| SiliconFlow API 不可用 | RAG 完全不可用 | DeepSeek Embedding 作为 fallback |
| HF Spaces 48h 休眠 | 首次请求延迟 +2 分钟 | 定时 ping 保活 |
| Qwen3 模型质量不如 DeepSeek | 回答质量下降 | 保留 DeepSeek 作为主 LLM |
| 向量索引需要重建 | 迁移工作量 | 先用相同维度模型(bge-large) |

---

## 9. 实施检查清单

### Phase 1：SiliconFlow API（30 分钟）

- [ ] 注册 SiliconFlow 账号
- [ ] 获取 API Key
- [ ] Railway 添加 `SILICONFLOW_API_KEY`
- [ ] 创建 `siliconflow_client.py`
- [ ] 修改 `vector_store.py` 添加 SiliconFlow fallback
- [ ] 本地测试 embedding + reranking
- [ ] 部署到 Railway
- [ ] 测试端到端 RAG 查询

### Phase 2：HF Spaces 备用（1 小时）

- [ ] 创建 HuggingFace 账号
- [ ] 创建 `aureon-model-server` Space
- [ ] 部署 Gradio 应用
- [ ] 测试 /api/embed 和 /api/rerank
- [ ] 添加 `HF_MODEL_SERVER_URL` 到 Railway
- [ ] 实现 fallback 逻辑
- [ ] 添加定时 ping 保活

### Phase 3：LLM 优化（按需）

- [ ] 测试 Qwen3-30B-A3B 在 SiliconFlow 的延迟
- [ ] 对比回答质量 vs DeepSeek
- [ ] 决定是否切换或添加为可选模型
- [ ] 修改 `llm.py` 支持多模型选择

---

## 10. 相关资源

| 资源 | URL |
|------|-----|
| SiliconFlow 定价 | https://siliconflow.cn/pricing |
| SiliconFlow API 文档 | https://docs.siliconflow.cn |
| SiliconFlow 模型中心 | https://siliconflow.cn/models |
| HuggingFace Spaces | https://huggingface.co/spaces |
| DeepSeek API 定价 | https://platform.deepseek.com/api-docs/pricing |
| Qwen3 模型卡 | https://huggingface.co/Qwen |
| BGE 模型卡 | https://huggingface.co/BAAI |
