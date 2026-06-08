# Aureon RAG 综合优化指南

**基于**: 192 QA Benchmark 结果 + 4 篇核心论文 + Upwork KRL-Dutch 项目需求（200 并发）
**日期**: 2026-06-08
**核心参考论文**:
- RGB Benchmark (AAAI 2024) — RAG 四大能力定义
- Self-RAG (ICLR 2024) — Reflection Tokens 自省机制
- CRAG (arXiv:2401.15884) — 检索质量三路分支
- Adaptive-RAG (NAACL 2024) — Query 复杂度分类路由

---

## 一、问题诊断总览

| 问题 | 当前值 | 目标值 | 根因 | 优先级 |
|------|--------|--------|------|--------|
| **Negative Detection** | 50% | ≥90% | 关键词 heuristic 覆盖不足，无法处理语义层面的"知识库外"查询 | 🔴 P0 |
| **Answer Relevance** | 0.21 | >0.50 | Generator 端问题：prompt 缺少"不要总结"禁令，LLM 倾向堆砌上下文而非回答问题 | 🔴 P0 |
| **Cross-article Recall** | 85.7% | ≥90% | 规则级查询拆分不够，缺少 LLM 级 Multi-Query Expansion | 🟡 P1 |
| **Scale Degradation** | 96.5%→77.7% (1000 docs) | 减缓衰减 | 向量空间稀释 + BM25 候选池膨胀 | 🟡 P1 |
| **200 并发支撑** | 5 并发饱和 | 200+ WebSocket | 缺少 Semaphore 限流 + 多 Worker 架构 | 🟡 P1 |

---

## 二、Negative Detection 优化（50% → ≥90%）

### 2.1 核心原理

RGB Benchmark (AAAI 2024) 将 Negative Rejection 定义为 RAG 四大基础能力之一，发现 LLM 在此能力上表现最差。CRAG 论文提出用轻量级 retrieval evaluator 对检索质量打分，根据置信度触发 Correct / Incorrect / Ambiguous 三路分支。

**当前 Aureon 管道**:
```
Query → [关键词 heuristic] → [LLM 分类器 (cached)] → 检索 → 生成
```

**问题**: 关键词 heuristic 只能覆盖"定价""团队规模"等明显超范围场景，无法处理语义层面的模糊查询（如"最新版本号""GitHub Stars"）。

### 2.2 推荐方案：三层防御 + CRAG 置信度门控

```
Query → [Layer 0: 空结果检查]
      → [Layer 1: 关键词 heuristic (<1ms)]
      → [Layer 2: LLM 意图分类器 (200-400ms, cached)]
      → 检索
      → [Layer 3: 检索质量置信度门控 (<1ms, CRAG 风格)]
         ├─ High confidence (score ≥ 0.05) → 直接生成
         ├─ Ambiguous (0.01 ≤ score < 0.05) → 生成 + 自省标记
         └─ Low confidence (score < 0.01) → 拒绝回答
      → 生成
      → [Layer 4: Post-Generation 自省验证 (可选, +200-500ms)]
```

### 2.3 具体实现

#### Layer 2: 增强 LLM 意图分类器

当前 `_is_negative_by_keywords` 只匹配固定关键词。增加 LLM 二分类 prompt：

```python
NEGATIVE_CLASSIFIER_PROMPT = """判断以下用户问题是否能从给定的知识库主题范围中找到答案。

知识库主题范围：
{knowledge_scope}

用户问题：{query}

规则：
1. 如果问题明确在知识库主题范围内，回答 YES
2. 如果问题涉及知识库明确不包含的信息（如实时数据、价格、团队信息），回答 NO
3. 如果不确定，回答 YES（宁可多检索，不错拒）

只回答 YES 或 NO，不要其他内容。"""
```

**关键参数**:
- `temperature=0`
- 缓存 TTL: 10-30 分钟（相同 query 不重复调用）
- Fallback: 分类器失败时默认 YES（可回答）
- `knowledge_scope` 需随知识库更新同步维护

#### Layer 3: CRAG 置信度门控（核心新增）

检索完成后，用 top-K 的最高 RRF 分数判断检索质量：

```python
# backend/app/rag/qa_chain.py 新增

# 置信度阈值（通过 benchmark 调优）
CRAG_HIGH_CONFIDENCE = 0.05    # 高置信：直接生成
CRAG_LOW_CONFIDENCE = 0.01     # 低置信：拒绝回答
CRAG_AMBIGUOUS_THRESHOLD = 0.03  # 中等置信：生成 + 不确定性标记

def evaluate_retrieval_confidence(retrieved_chunks: list) -> str:
    """
    CRAG-style retrieval quality evaluation.
    Returns: 'correct' | 'ambiguous' | 'incorrect'
    """
    if not retrieved_chunks:
        return "incorrect"

    # 取 top-1 的 RRF 分数（或 reranker 分数）
    top_score = retrieved_chunks[0].get("score", 0)

    if top_score >= CRAG_HIGH_CONFIDENCE:
        return "correct"
    elif top_score >= CRAG_LOW_CONFIDENCE:
        return "ambiguous"
    else:
        return "incorrect"


def build_answer_with_confidence(answer: str, confidence: str) -> str:
    """在答案中注入置信度标记，供前端展示。"""
    if confidence == "ambiguous":
        return f"⚠️ 以下回答基于有限的参考信息，可能不完整：\n\n{answer}"
    elif confidence == "incorrect":
        return "抱歉，知识库中没有找到与您问题相关的信息。请尝试换个问法，或联系管理员确认知识库是否已覆盖该主题。"
    return answer
```

#### Layer 4: Post-Generation 自省（可选，最高精度）

```python
SELF_REFLECTION_PROMPT = """判断以下回答是否被参考文档充分支撑。

用户问题：{query}
参考文档：{context}
生成的回答：{answer}

规则：
1. 如果回答中的每个关键论断都能在参考文档中找到依据，回答 SUPPORTED
2. 如果回答包含推测、编造或文档中没有的信息，回答 NOT_SUPPORTED
3. 如果回答虽然正确但遗漏了重要信息，回答 PARTIAL

只回答 SUPPORTED / NOT_SUPPORTED / PARTIAL，不要其他内容。"""
```

**注意**: 流式输出场景下，Post-Generation 自省需要在完整生成后执行，不影响首 token 延迟。

### 2.4 阈值调优方法

用现有的 20 个 negative QA pairs 做 grid search：

```python
# 遍历阈值组合，找到最优 F1
for high_thresh in [0.03, 0.05, 0.07, 0.10]:
    for low_thresh in [0.005, 0.01, 0.02]:
        precision, recall, f1 = evaluate_negative_detection(
            high_thresh, low_thresh, test_data=GOLDEN_192QA_NEGATIVE
        )
```

**预期效果**: Negative Detection 50% → 85-95%（三层防御叠加）

---

## 三、Answer Relevance 优化（0.21 → >0.50）

### 3.1 根因分析

DeepEval 的 Answer Relevancy 用 statement-level decomposition：
1. 将 answer 拆解为独立语句
2. 逐条判定是否与问题相关
3. 分数 = 相关语句数 / 总语句数

**Aureon 当前 prompt 的问题**:
- 缺少"不要总结"的明确禁令
- LLM 倾向以"文档介绍了..."开头，这些前言被 DeepEval 判定为不相关语句
- 没有正反例对比，LLM 不知道什么是"错误的回答方式"
- Agent 路径（`agent.py:54`）的 prompt 完全没有回答约束

### 3.2 重写 QA_SYSTEM_PROMPT

```python
QA_SYSTEM_PROMPT_OPTIMIZED = """你是精准的知识库问答助手。你的唯一任务是回答用户的问题。

## 核心原则
- 先理解用户的问题意图，再从参考文档中提取答案
- 每个句子必须直接回应用户的问题
- 如果文档中有答案，直接给出答案
- 如果文档中没有答案，直接说"文档中未提及"

## 回答结构（必须遵守）
1. **直接回答**（1-2 句话，直接回答问题核心）
2. **补充细节**（仅当用户问题需要更详细解释时）
3. **引用来源**（格式：[来源: 文章标题]）

## 禁止行为
- ❌ 禁止以"根据文档"、"文档介绍了"、"参考文档提到"开头
- ❌ 禁止复述文档内容而不回答问题
- ❌ 禁止添加用户未要求的背景信息
- ❌ 禁止使用"总的来说"、"综上所述"、"需要注意的是"等总结性/过渡性语句
- ❌ 禁止在回答开头加前言或铺垫

## 正确示例

用户问："BM25 的核心原理是什么？"
✅ 正确："BM25 通过词频饱和度和文档长度归一化计算关键词匹配分数，核心公式包含 TF（词频）和 IDF（逆文档频率）两个组件。[来源: RAG 优化实战]"
❌ 错误："文档介绍了 RAG 系统中使用的多种检索技术。BM25 是其中一种经典的排序算法，它的核心原理是..."

用户问："如何配置 Redis 缓存？"
✅ 正确："配置步骤：1) 安装 redis-py；2) 设置 REDIS_URL 环境变量；3) 在 config.py 中启用缓存层。[来源: Redis 集成指南]"
❌ 错误："Redis 是一个高性能的内存数据库，在 RAG 系统中常用于缓存。下面文档介绍了如何配置..."

## 负面回答模式
如果参考文档中没有相关信息，直接回答：
"文档中未提及该信息。"

不要猜测、不要补充你认为可能正确的信息。

{lang_instruction}

参考文档：
{context}
"""

QA_SYSTEM_PROMPT_EN_OPTIMIZED = """You are a precise knowledge base QA assistant. Your only task is to answer the user's question.

## Core Principles
- Understand the user's question intent first, then extract the answer from reference documents
- Every sentence must directly address the user's question
- If the documents contain the answer, give it directly
- If the documents don't contain the answer, say "Not mentioned in the documents"

## Answer Structure (mandatory)
1. **Direct answer** (1-2 sentences, addressing the core question)
2. **Supporting details** (only when the user needs more explanation)
3. **Source citation** (format: [Source: Article Title])

## Prohibited Patterns
- ❌ Do NOT start with "Based on the documents", "The documents mention", "According to the reference"
- ❌ Do NOT summarize document content without answering the question
- ❌ Do NOT add background information the user didn't ask for
- ❌ Do NOT use "In summary", "To summarize", "It's worth noting" as transitions
- ❌ Do NOT add preamble or setup before the actual answer

## Examples

User: "What is the core principle of BM25?"
✅ Correct: "BM25 calculates keyword matching scores through term frequency saturation and document length normalization, with TF and IDF as its two core components. [Source: RAG Optimization Guide]"
❌ Wrong: "The documents describe various retrieval techniques used in RAG systems. BM25 is one of the classic ranking algorithms. Its core principle is..."

## Negative Response
If the reference documents don't contain the relevant information, answer directly:
"The documents do not contain information about this topic."

Do not guess or supplement information you think might be correct.

{lang_instruction}

Reference documents:
{context}
"""
```

### 3.3 修复 Agent 路径的 prompt

`backend/app/langgraph/nodes/agent.py` 第 54 行的 `full_query` 构造过于简单：

```python
# 当前（问题代码）
full_query = f"参考上下文：{context}\n\n用户问题：{query}"

# 优化后
AGENT_SYSTEM_PREFIX = """你是知识库问答助手。基于参考上下文回答用户问题。

规则：
1. 直接回答问题，不要以"根据文档"开头
2. 每个句子必须直接回应用户的问题
3. 不要总结文档内容，直接给出答案
4. 引用来源：[来源: 文章标题]

参考上下文：
{context}
"""

full_query = f"{AGENT_SYSTEM_PREFIX.format(context=context)}\n\n用户问题：{query}"
```

### 3.4 问题类型自适应提示

```python
QUERY_TYPE_INSTRUCTIONS = {
    "factual": "给出明确的事实答案（时间、名称、数字）。一句话回答即可。",
    "comparison": "用表格或并列结构对比各项差异。每个维度直接回应用户关心的方面。",
    "how_to": "给出清晰的步骤列表。每步操作直接可执行。",
    "reasoning": "给出推理过程和结论。每个推理步骤都要有文档依据。",
}
```

在 `generate_answer` 中根据 query classification 结果注入对应指令。

### 3.5 预期效果

- 前言/总结性语句被禁止 → DeepEval statement decomposition 不再扣分
- 正反例对比 → LLM 学习到正确的回答模式
- Agent 路径 prompt 修复 → 两条路径的回答质量对齐
- **预期 Answer Relevance**: 0.21 → 0.55-0.70

---

## 四、Cross-article Recall 优化（85.7% → ≥90%）

### 4.1 核心原理

当用户提出跨文章查询（如"对比 RAG 和 Fine-tuning 的成本"）时，需要从多篇文档中综合信息。当前 `is_cross_article_query()` + `expand_queries_rules()` 只做规则级拆分（基于"比较""和""vs"等连接词），缺少语义级的查询扩展。

### 4.2 推荐方案：LLM Multi-Query + Query Decomposition 组合

```python
# backend/app/rag/query_rewriter.py 新增

async def multi_query_llm_rewrite(
    query: str,
    llm_call_fn,
    n_variants: int = 3
) -> List[str]:
    """
    LLM-based multi-query expansion.
    Returns [original_query] + variants.
    Based on MultiQueryRetriever pattern (LangChain).
    """
    prompt = f"""将以下问题改写为 {n_variants} 个不同的表述，保持语义一致但用词和角度不同。
每个变体应该能独立用于检索，找到与原始问题相关的信息。
只返回 JSON 数组格式，不要其他内容。

原始问题: {query}

示例:
输入: "对比 BM25 和向量检索的优缺点"
输出: ["BM25 关键词检索的优势和局限性", "向量语义检索的性能特点", "BM25 vs Vector Search 各自适用场景"]"""

    resp = await llm_call_fn(prompt)
    try:
        variants = json.loads(resp)
        return [query] + [v for v in variants[:n_variants] if v != query]
    except (json.JSONDecodeError, TypeError):
        return [query]  # fallback: 只用原始查询


async def decompose_complex_query(
    query: str,
    llm_call_fn,
    max_sub_queries: int = 5
) -> List[str]:
    """
    Query Decomposition: break complex/comparative queries into sub-queries.
    Based on Adaptive-RAG (NAACL 2024).
    """
    prompt = f"""将以下复杂问题拆解为 {max_sub_queries} 个独立的子问题，每个子问题可以单独检索回答。
子问题应该覆盖原始问题的不同方面。
只返回 JSON 数组格式，不要其他内容。

原始问题: {query}

示例:
输入: "对比 LangChain 和 LlamaIndex 在 RAG 场景中的优缺点，包括性能、易用性和生态系统"
输出: [
    "LangChain 在 RAG 场景中的主要优势是什么？",
    "LlamaIndex 在 RAG 场景中的主要优势是什么？",
    "LangChain 和 LlamaIndex 的性能对比如何？",
    "LangChain 和 LlamaIndex 哪个更容易上手？",
    "LangChain 和 LlamaIndex 的生态系统和社区支持对比"
]"""

    resp = await llm_call_fn(prompt)
    try:
        sub_queries = json.loads(resp)
        return [q for q in sub_queries[:max_sub_queries] if q]
    except (json.JSONDecodeError, TypeError):
        return [query]
```

### 4.3 集成到检索管道

```python
# backend/app/rag/qa_chain.py 修改

async def retrieve_with_expansion(query: str, llm_call_fn, is_cross_article: bool):
    """
    智能检索：根据查询类型选择扩展策略。
    """
    if is_cross_article:
        # 跨文章查询：Multi-Query + Query Decomposition 组合
        expanded = await multi_query_llm_rewrite(query, llm_call_fn, n_variants=2)
        if len(query) > 50:  # 长查询进一步拆分
            sub_queries = await decompose_complex_query(query, llm_call_fn)
            expanded.extend(sub_queries[:3])

        # 去重
        expanded = list(dict.fromkeys(expanded))[:6]  # 最多 6 个变体
    else:
        expanded = [query]

    # 并行检索所有变体
    all_results = await asyncio.gather(*[
        hybrid_retrieve(q, top_k=10) for q in expanded
    ])

    # RRF 融合 + 去重
    merged = merge_rrf_results(all_results)
    return merged[:30]  # 候选池上限
```

### 4.4 关键配置

| 参数 | 值 | 说明 |
|------|-----|------|
| `n_variants` | 2-3 | 每个查询的变体数 |
| `max_sub_queries` | 3-5 | 复杂查询的子问题数 |
| `per_variant_top_k` | 10 | 每个变体的召回数 |
| `merged_pool_size` | 30 | 融合后候选池上限 |
| `embedding_threshold` | 0.10 | 预过滤极低分候选 |
| **延迟增量** | +200-500ms | 1 次 LLM 改写 + N 次并行检索 |
| **成本增量** | +1 LLM 调用 | 每次跨文章查询 |

### 4.5 预期效果

- 跨文章 Recall@3: 85.7% → 90-95%
- **延迟增量可控**: Multi-Query 并行检索，总延迟 ≈ max(各变体延迟) + LLM 改写延迟

---

## 五、高并发架构（200+ WebSocket 连接）

### 5.1 Upwork KRL-Dutch 项目需求

项目要求：Web Chat + Voice，200 并发用户，部署在 DigitalOcean。

### 5.2 架构设计

```
                    ┌──────────────────┐
   Clients (200+)  │  Nginx (反向代理)  │ WebSocket proxy + SSL
                    └────┬────────┬────┘
                         │        │
                    ┌────▼───┐ ┌──▼────┐
                    │Uvicorn │ │Uvicorn│  Gunicorn + 4 Workers
                    │Worker 1│ │Worker 2│
                    └───┬────┘ └───┬───┘
                        │          │
                    ┌───▼──────────▼───┐
                    │   Redis Stack     │  Semantic Cache + Pub/Sub + Session
                    └──────────────────┘
                        │          │
                    ┌───▼────┐ ┌──▼───┐
                    │ Qdrant │ │Qdrant│  gRPC 协议（比 REST 快 2-3x）
                    └────────┘ └──────┘
```

### 5.3 并发限流（Semaphore）

```python
# backend/app/concurrency.py

import asyncio
import time
from fastapi import HTTPException

# === LLM API 限流（按模型分组） ===
# DeepSeek: RPM 300, 每请求 ~3-10s → 30 并发安全
# DashScope Embedding: RPM 较高 → 50 并发
_LLM_SEMAPHORES = {
    "deepseek-chat": asyncio.Semaphore(30),
    "deepseek-reasoner": asyncio.Semaphore(10),
    "zhipu-glm4": asyncio.Semaphore(20),
    "dashscope-embedding": asyncio.Semaphore(50),
}

# === RAG Pipeline 限流 ===
# 向量库 + Reranker 综合瓶颈
_RAG_SEMAPHORE = asyncio.Semaphore(40)

# === 排队超时 ===
QUEUE_TIMEOUT_SECONDS = 30


async def llm_call_with_semaphore(model: str, coro):
    """LLM API call with rate limiting."""
    sem = _LLM_SEMAPHORES.get(model, asyncio.Semaphore(20))
    try:
        await asyncio.wait_for(sem.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="System busy. Please try again later."
        )
    try:
        return await coro
    finally:
        sem.release()


async def rag_pipeline_with_semaphore(coro):
    """RAG pipeline with rate limiting."""
    sem = _RAG_SEMAPHORE
    try:
        await asyncio.wait_for(sem.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline busy. Please try again later."
        )
    try:
        return await coro
    finally:
        sem.release()
```

### 5.4 WebSocket 连接管理

```python
# backend/app/api/ws_manager.py

import asyncio
from fastapi import WebSocket
from typing import Dict

class ConnectionManager:
    """200+ WebSocket 连接管理器。"""

    def __init__(self, max_connections: int = 300):
        self.active: Dict[str, WebSocket] = {}
        self._max = max_connections
        self._heartbeat_task = None

    async def connect(self, client_id: str, ws: WebSocket):
        if len(self.active) >= self._max:
            await ws.close(code=1013, reason="Server full")
            return False
        await ws.accept()
        self.active[client_id] = ws
        return True

    async def disconnect(self, client_id: str):
        self.active.pop(client_id, None)

    async def send_json(self, client_id: str, data: dict):
        ws = self.active.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                await self.disconnect(client_id)

    async def broadcast(self, data: dict):
        stale = []
        for cid, ws in self.active.items():
            try:
                await ws.send_json(data)
            except Exception:
                stale.append(cid)
        for cid in stale:
            await self.disconnect(cid)

    async def heartbeat_loop(self, interval: int = 30, timeout: int = 300):
        """每 30s ping，超时断开。"""
        while True:
            stale = []
            for cid, ws in list(self.active.items()):
                try:
                    await asyncio.wait_for(
                        ws.send_json({"type": "ping"}),
                        timeout=5
                    )
                except Exception:
                    stale.append(cid)
            for cid in stale:
                await self.disconnect(cid)
            await asyncio.sleep(interval)

manager = ConnectionManager(max_connections=300)
```

### 5.5 跨 Worker 通信

WebSocket 连接绑定在单个 Uvicorn Worker 上。多 Worker 场景下，通过 Redis Pub/Sub 广播消息：

```python
# 每个 Worker 启动时订阅 Redis channel
async def subscribe_broadcast(redis_client, manager: ConnectionManager):
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("chat:broadcast")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            target = data.get("target_client")
            if target and target in manager.active:
                await manager.send_json(target, data)
```

### 5.6 部署配置

**Gunicorn + Uvicorn（推荐）**:
```bash
gunicorn app.main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --graceful-timeout 30 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

**Nginx WebSocket 代理**:
```nginx
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl;
    server_name chat.example.com;

    location /ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / {
        proxy_pass http://backend;
    }
}
```

### 5.7 关键阈值汇总

| 指标 | 值 | 说明 |
|------|-----|------|
| WebSocket 最大连接数 | 300 | 预留 50% 余量 |
| LLM API Semaphore | 30 | DeepSeek-chat |
| Embedding Semaphore | 50 | DashScope |
| RAG Pipeline Semaphore | 40 | 向量检索 + Rerank |
| Uvicorn Workers | 4 | 2-4 vCPU |
| 排队超时 | 30s | 超时返回 503 |
| 心跳间隔 | 30s | WebSocket |
| 连接超时 | 300s | 无活动断开 |
| Gunicorn timeout | 120s | Worker 超时 |
| Qdrant 协议 | gRPC | 比 REST 快 2-3x |

---

## 六、延迟优化（E2E 3,104ms → 目标 <2,500ms）

### 6.1 当前延迟分布

```
检索 (RRF):     ~154ms  (5%)
LLM 生成:       ~2,868ms (92%)
嵌入+格式化:     ~82ms  (3%)
─────────────────────────
总计:           ~3,104ms
```

**瓶颈在 LLM，不在检索。** 检索优化空间已很小。

### 6.2 优化策略

| 策略 | 延迟影响 | 实现难度 | 优先级 |
|------|----------|----------|--------|
| **Streaming 输出** | 感知延迟 -50%+ | 低（已有 SSE） | P0 |
| **Prompt Caching** | TTFT -50%+ | 低（DeepSeek 支持） | P0 |
| **Query 复杂度路由** | 简单 query -60% | 中 | P1 |
| **Prompt 压缩** | 减少 token 数 | 中 | P1 |
| **小模型路由** | 简单 query -70% | 中 | P2 |

### 6.3 Query 复杂度路由（Adaptive RAG）

```python
# 简单事实查询 → 跳过 RAG，LLM 直接回答
# 中等查询 → 标准 RAG pipeline
# 复杂查询 → Multi-Query + Decomposition + CRAG

QUERY_ROUTING = {
    "simple": {"retrieval": False, "model": "deepseek-chat"},
    "medium": {"retrieval": True, "model": "deepseek-chat"},
    "complex": {"retrieval": True, "multi_query": True, "model": "deepseek-chat"},
}
```

---

## 七、Scale Degradation 缓解（96.5%→77.7% @1000 docs）

### 7.1 根因

随着文档数增加：
- 向量空间稀释：embedding 相似度分布变得更平坦
- BM25 候选池膨胀：更多文档产生更多噪声匹配
- Reranker 压力增大：top-K 候选中噪声比例上升

### 7.2 缓解策略

| 策略 | 说明 | 优先级 |
|------|------|--------|
| **元数据分区** | 按文档类型/主题分 collection，检索时先过滤 | P1 |
| **HNSW 参数调优** | `ef_construction=200`, `m=32` 提升召回 | P1 |
| **动态 top-K** | 根据文档规模自动调整召回数（小库 top-10，大库 top-30） | P2 |
| **Contextual Retrieval** | 已实现，有效降低检索失败率 35-49% | ✅ 已有 |

### 7.3 元数据分区示例

```python
# 按文档类型分 collection
COLLECTIONS = {
    "technical": "aureon_tech",      # 技术文章
    "business": "aureon_business",   # 商业文档
    "general": "aureon_general",     # 通用知识
}

# 检索时先过滤
def search_with_metadata_filter(query, doc_type=None):
    if doc_type:
        results = vector_store.search(
            query, collection=COLLECTIONS[doc_type], top_k=20
        )
    else:
        # 跨 collection 检索 + RRF 融合
        results = parallel_search_all_collections(query)
    return results
```

---

## 八、实施优先级路线图

### Phase 1: 立即执行（1-2 天）— 最高 ROI

| # | 任务 | 预期收益 | 文件 |
|---|------|----------|------|
| 1 | 重写 QA_SYSTEM_PROMPT（加入禁令 + 正反例） | Answer Relevance 0.21 → 0.55+ | `qa_chain.py` |
| 2 | 修复 Agent 路径 prompt | Agent 回答质量对齐 | `agent.py` |
| 3 | 加 asyncio.Semaphore 限流 | 防雪崩，支撑 200 并发 | 新建 `concurrency.py` |
| 4 | WebSocket 连接管理器 | 支撑 200+ 连接 | `ws_manager.py` |

### Phase 2: 本周完成（3-5 天）— 核心提升

| # | 任务 | 预期收益 | 文件 |
|---|------|----------|------|
| 5 | CRAG 置信度门控 | Negative Detection 50% → 85%+ | `qa_chain.py` |
| 6 | LLM Multi-Query Expansion | Cross-article 85.7% → 90%+ | `query_rewriter.py` |
| 7 | 问题类型自适应 prompt | Answer Relevance 进一步提升 | `qa_chain.py` |
| 8 | Gunicorn + 多 Worker 部署 | 并发线性扩展 | `Dockerfile` |

### Phase 3: 下周完成（5-7 天）— 生产加固

| # | 任务 | 预期收益 | 文件 |
|---|------|----------|------|
| 9 | Post-Generation 自省 | Negative Detection → 90%+ | `qa_chain.py` |
| 10 | Query Decomposition | 复杂查询质量提升 | `query_rewriter.py` |
| 11 | Redis Pub/Sub 跨 Worker | 多 Worker 下 WebSocket 广播 | `ws_manager.py` |
| 12 | 阈值自动调优脚本 | 阈值最优 F1 | 新建 `tune_thresholds.py` |

---

## 九、参考文献

| 论文/资源 | 来源 | 核心贡献 |
|-----------|------|----------|
| RGB Benchmark | AAAI 2024 | 定义 RAG 四大能力：Noise Robustness, Negative Rejection, Information Integration, Counterfactual Robustness |
| Self-RAG | ICLR 2024 (Asai et al.) | Reflection Tokens（IsRel, IsSup）让 LLM 自我判断检索相关性和生成支撑度 |
| CRAG | arXiv:2401.15884 (Yan et al.) | 检索质量三路分支（Correct/Ambiguous/Incorrect），Decompose-then-Recompose 过滤 |
| Adaptive-RAG | NAACL 2024 (Jeong et al.) | Query 复杂度分类器，动态选择 No-retrieval / Single-step / Multi-step |
| ClashEval | arXiv:2404.10198 (Wu et al.) | LLM 先验 vs 外部证据冲突量化，token probability 作为置信度信号 |
| ChainPoll | Galileo/RealHall 2023 | Adherence 指标评估 RAG 中 LLM 是否忠于检索内容 |
| Anthropic Contextual Retrieval | Anthropic Blog 2024 | Chunk-specific 上下文前缀，检索失败率降低 49-67% |
| GraphRAG | Microsoft Research 2024 | 知识图谱 + Leiden 社区划分，多跳推理 |
| DeepEval Answer Relevancy | DeepEval Docs | Statement-level decomposition，语句级相关性判定 |
| RAGAS | arXiv:2309.15217 | Reverse-engineered question similarity 评估 Answer Relevancy |
