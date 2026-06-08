# Aureon 并行优化实施方案

**日期**: 2026-06-07
**版本**: v1.0
**目标**: LLM 缓存 + Re-ranking + WebSocket 并行实施

---

## 📊 代码库现状分析

### ✅ 已有实现（可以直接利用）

#### 1. **LLM 缓存** (`backend/app/cache/redis_client.py`)
```python
# 已实现：
✅ Redis Exact Cache（token bag 语义去重）
✅ In-memory Fallback Cache（Redis 不可用时）
✅ 缓存版本管理 (_CACHE_VERSION = "v16")
✅ TTL 过期（默认 1 小时）
✅ 已集成到 qa_chain.py（rag_query_with_cache）

# 缺失：
❌ Semantic Cache（向量相似度缓存）
❌ 缓存命中率统计和监控
❌ Negative detection classifier 缓存（可优化）
```

#### 2. **Re-ranking** (`backend/app/rag/vector_store.py`)
```python
# 已实现：
✅ BGE-Reranker-v2-m3（Cross-Encoder）
✅ GPU Reranker 支持（get_gpu_reranker）
✅ 自适应 Re-ranking（高置信度时跳过）
✅ Reranker 评分和排序

# 缺失：
❌ Semantic Reranker（语义相似度增强）
❌ Query-aware Re-ranking（根据查询复杂度调整策略）
❌ 多 Reranker 集成（ensemble reranking）
```

#### 3. **Streaming**
```python
# 已实现：
✅ SSE Streaming（rag_query_astream）
✅ LangGraph 流式输出
✅ Token-by-token streaming

# 缺失：
❌ WebSocket Streaming（双向实时通信）
❌ 多轮对话实时反馈
❌ Tool Calling 实时交互
```

---

## 🎯 并行实施方案

### **Phase 1: LLM Cache 增强**（第 1 周）

**目标**: 缓存命中率从 30% → 50%+

#### 1.1 Semantic Cache 层（新增）

**位置**: `backend/app/cache/semantic_cache.py`（新文件）

```python
# 核心功能：
1. 向量相似度缓存（基于 embedding cosine similarity）
2. 阈值配置（SIMILARITY_THRESHOLD = 0.92）
3. 双层缓存（Exact → Semantic → LLM）
4. 嵌入缓存复用（使用现有的 embed_texts_llm）

# 集成点：
- qa_chain.py: rag_query_with_cache() 添加 semantic check
- 延迟增加：~5-10ms（vector search）
- 缓存命中率提升：+20-40%
```

**关键设计**:
```python
class SemanticLLMCache:
    def __init__(self, redis_client, embedding_model, threshold=0.92):
        self.redis = redis_client
        self.embedding_model = embedding_model
        self.threshold = threshold
    
    async def get(self, query: str) -> Optional[str]:
        """两层缓存查找"""
        # 1. Exact match (token bag) - 最快
        exact = await self.get_exact(query)
        if exact:
            return exact
        
        # 2. Semantic match (vector similarity) - 中等
        semantic = await self.get_semantic(query)
        if semantic:
            return semantic
        
        return None
    
    async def get_semantic(self, query: str) -> Optional[str]:
        """基于 embedding 相似度的缓存"""
        query_emb = await self.embedding_model.embed(query)
        
        # Redis Vector Search（需要 Redis Stack 或 RediSearch）
        results = await self.redis.vector_search(
            vector=query_emb,
            top_k=1,
            score_threshold=self.threshold
        )
        
        if results and results[0]['score'] >= self.threshold:
            return results[0]['response']
        return None
```

#### 1.2 Negative Detection Classifier 缓存优化

**位置**: `backend/app/rag/qa_chain.py`（修改现有）

```python
# 当前状态：
✅ 已有 classifier cache（_CLASSIFIER_CACHE）
✅ TTL-based expiry（3600s）

# 优化：
1. 缓存持久化到 Redis（重启后保留）
2. 统计缓存命中率
3. 基于 embedding 的语义缓存（相似查询复用）
```

#### 1.3 缓存统计和监控

**位置**: `backend/app/api/rag_stats.py`（修改现有）

```python
# 新增指标：
- cache_hit_rate: 缓存命中率（exact + semantic）
- cache_latency: 缓存查找延迟（p50/p90/p99）
- cache_size: 缓存大小（条目数）
- cache_memory: 内存占用
```

**验收标准**:
- ✅ Semantic cache 延迟 < 10ms
- ✅ 缓存命中率 > 50%（生产环境）
- ✅ 成本节省 > 50%
- ✅ 内存占用可控（< 100MB）

---

### **Phase 2: Re-ranking 增强**（第 1-2 周）

**目标**: Context Precision 从 0.791 → 0.92+

#### 2.1 Query-Aware Re-ranking 策略

**位置**: `backend/app/rag/qa_chain.py`（修改 hybrid_retrieve）

```python
# 当前状态：
✅ 自适应 Re-ranking（跳过简单查询）
✅ BGE-Reranker-v2-m3（单一模型）

# 增强：
1. 查询复杂度分类（简单/中等/复杂）
2. 动态 Re-ranker 选择（根据复杂度）
3. Ensemble Re-ranking（多模型投票）
```

**策略设计**:
```python
def adaptive_rerank_strategy(query: str, candidates: List[Dict]) -> str:
    """根据查询复杂度决定 Re-ranking 策略"""
    
    # 简单查询：跳过 Re-ranking（延迟优先）
    if is_simple_query(query):
        return "skip"  # ~6ms
    
    # 中等查询：单一 BGE-Reranker（精度/延迟平衡）
    if is_medium_query(query):
        return "single_bge"  # ~30ms
    
    # 复杂查询：Ensemble Re-ranking（精度优先）
    if is_complex_query(query):
        return "ensemble"  # ~80ms
    
    # 默认：单一 BGE-Reranker
    return "single_bge"

def is_simple_query(query: str) -> bool:
    """判断是否为简单查询"""
    # 关键词匹配、短查询、明确意图
    return len(query.split()) < 5 and not is_cross_article_query(query)

def is_complex_query(query: str) -> bool:
    """判断是否为复杂查询"""
    # 比较、对比、多步骤推理
    return is_cross_article_query(query) or len(query.split()) > 15
```

#### 2.2 Ensemble Re-ranking（多模型投票）

**位置**: `backend/app/rag/vector_store.py`（新增）

```python
class EnsembleReranker:
    """多 Reranker 集成，提高鲁棒性"""
    
    def __init__(self):
        self.rerankers = [
            ("bge-v2-m3", BGEReranker("BAAI/bge-reranker-v2-m3")),
            ("jina", JinaReranker()),  # 可选
            ("cohere", CohereReranker()),  # API-based fallback
        ]
    
    def rerank(self, query: str, docs: List[Dict], top_k: int) -> List[Dict]:
        """Ensemble reranking：每个模型独立评分，加权平均"""
        scores = {}
        
        for name, reranker in self.rerankers:
            ranked = reranker.rerank(query, docs, top_k=len(docs))
            for rank, doc in enumerate(ranked):
                key = doc['metadata']['slug']
                if key not in scores:
                    scores[key] = {'doc': doc, 'weighted_score': 0}
                # 加权：BGE 0.6, Jina 0.3, Cohere 0.1
                weight = 0.6 if name == "bge-v2-m3" else 0.3 if name == "jina" else 0.1
                scores[key]['weighted_score'] += (len(docs) - rank) * weight
        
        # 按加权分数排序
        ranked = sorted(scores.values(), key=lambda x: x['weighted_score'], reverse=True)
        return [item['doc'] for item in ranked[:top_k]]
```

#### 2.3 Re-ranking 评估和 A/B 测试

**位置**: `backend/app/evaluation/`（新增模块）

```python
class RerankingEvaluator:
    """评估 Re-ranking 效果"""
    
    def evaluate(self, query: str, expected_docs: List[str], 
                 with_rerank: bool, without_rerank: bool) -> Dict:
        """对比 Re-ranking 前后的精度"""
        
        metrics = {
            "precision_at_3": ...,
            "recall_at_5": ...,
            "mrr": ...,
            "ndcg": ...,
        }
        
        return {
            "with_rerank": metrics,
            "without_rerank": metrics,
            "improvement": ...,
        }
```

**验收标准**:
- ✅ Context Precision 提升 > 15%（从 0.791 → 0.92+）
- ✅ 简单查询延迟不变（跳过 Re-ranking）
- ✅ 复杂查询精度提升 > 20%
- ✅ 平均延迟增加 < 30ms

---

### **Phase 3: WebSocket Streaming**（第 2-3 周）

**目标**: 支持多轮对话和 Tool Calling 实时交互

#### 3.1 WebSocket 服务器

**位置**: `backend/app/api/websocket.py`（新文件）

```python
from fastapi import WebSocket, WebSocketDisconnect
import json

class WebSocketManager:
    """WebSocket 连接管理"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
    
    async def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
    
    async def send_message(self, client_id: str, message: Dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

@app.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """WebSocket 端点：支持多轮对话"""
    manager = WebSocketManager()
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            query = data.get("query", "")
            conversation_id = data.get("conversation_id")
            
            # RAG 检索 + 流式输出
            async for event in rag_query_astream(query, llm, ...):
                await manager.send_message(client_id, event)
            
            # Tool Calling 支持
            if event.get("type") == "tool_call":
                # 执行工具并返回结果
                tool_result = await execute_tool(event["tool"], event["args"])
                await manager.send_message(client_id, {
                    "type": "tool_result",
                    "result": tool_result
                })
    
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
```

#### 3.2 前端 WebSocket 客户端

**位置**: `src/services/websocket.ts`（新文件）

```typescript
class AureonWebSocket {
    private ws: WebSocket;
    private clientId: string;
    
    constructor(clientId: string) {
        this.clientId = clientId;
        this.ws = new WebSocket(`ws://localhost:8000/ws/chat/${clientId}`);
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };
    }
    
    send(query: string, conversationId?: string) {
        this.ws.send(JSON.stringify({
            query,
            conversation_id: conversationId
        }));
    }
    
    private handleMessage(data: any) {
        switch (data.type) {
            case 'sources':
                // 显示引用来源
                break;
            case 'text':
                // 逐 token 显示回答
                break;
            case 'tool_call':
                // 显示工具调用
                break;
            case 'tool_result':
                // 显示工具结果
                break;
        }
    }
}
```

#### 3.3 SSE → WebSocket 迁移策略

```python
# 渐进式迁移：
1. Phase 1: 保持 SSE（现有功能不变）
2. Phase 2: WebSocket 作为可选（通过 query param 启用）
3. Phase 3: 默认使用 WebSocket（多轮对话场景）
4. Phase 4: SSE 降级为 fallback（WebSocket 不可用时）

# 代码位置：
- backend/app/routers/chat.py: 添加 WebSocket 支持
- backend/app/langgraph/streaming.py: 改造为支持两种模式
- src/services/api.ts: 前端支持两种 streaming 方式
```

**验收标准**:
- ✅ WebSocket 连接延迟 < 100ms
- ✅ 多轮对话状态保持
- ✅ Tool Calling 实时交互
- ✅ SSE 降级支持（兼容旧客户端）
- ✅ 并发连接支持 > 200

---

## 📅 实施时间表

### Week 1: LLM Cache 增强

| 天数 | 任务 | 产出 |
|------|------|------|
| Day 1-2 | Semantic Cache 实现 | `semantic_cache.py` |
| Day 3 | Negative Detection Cache 优化 | `qa_chain.py` 修改 |
| Day 4 | 缓存统计和监控 | `rag_stats.py` 增强 |
| Day 5 | 测试和调优 | 缓存命中率 > 50% |

### Week 1-2: Re-ranking 增强

| 天数 | 任务 | 产出 |
|------|------|------|
| Day 6-7 | Query-Aware 策略实现 | `qa_chain.py` 修改 |
| Day 8-9 | Ensemble Re-ranking | `vector_store.py` 新增 |
| Day 10 | A/B 测试框架 | `reranking_evaluator.py` |
| Day 11-12 | 评估和调优 | Context Precision > 0.92 |

### Week 2-3: WebSocket Streaming

| 天数 | 任务 | 产出 |
|------|------|------|
| Day 13-14 | WebSocket 服务器 | `websocket.py` |
| Day 15-16 | 前端 WebSocket 客户端 | `websocket.ts` |
| Day 17-18 | 多轮对话支持 | `conversation_manager.py` |
| Day 19-20 | Tool Calling 集成 | `tool_executor.py` |
| Day 21 | 测试和文档 | E2E 测试通过 |

---

## 💰 成本效益分析

### 并行实施的 ROI

| 优化项 | 开发成本 | 月度节省 | 12 月 ROI |
|--------|----------|---------|----------|
| LLM Cache 增强 | 40-50 小时 | $150-400/月 | **5-10x** |
| Re-ranking 增强 | 50-70 小时 | 精度提升 → 客户满意度 | **长期价值** |
| WebSocket Streaming | 60-80 小时 | 用户体验提升 | **竞争力** |
| **总计** | **150-200 小时** | **$200-500/月 + 竞争力** | **6-12x** |

### 风险和缓解

| 风险 | 概率 | 缓解策略 |
|------|------|----------|
| Semantic Cache 精度不足 | 25% | 阈值调优 + A/B 测试 |
| Re-ranking 延迟过高 | 30% | 自适应策略 + 轻量级模型 |
| WebSocket 兼容性问题 | 20% | SSE 降级支持 |
| 并行实施冲突 | 15% | 模块化设计 + 代码审查 |

---

## 🔧 技术细节

### A.1 Semantic Cache 实现

```python
# backend/app/cache/semantic_cache.py

import numpy as np
from typing import Optional
from app.rag.vector_store import embed_texts_llm

class SemanticLLMCache:
    """向量相似度缓存"""
    
    def __init__(self, redis_client, threshold: float = 0.92):
        self.redis = redis_client
        self.threshold = threshold
    
    async def get(self, query: str) -> Optional[str]:
        """查找语义相似的缓存"""
        # 1. Embed query
        query_emb = embed_texts_llm([query])[0]
        
        # 2. Redis Vector Search（使用 RediSearch 或 Redis Stack）
        # 注意：需要 Redis Stack 支持向量搜索
        try:
            results = await self.redis.ft("idx:llm_cache").search(
                f"@embedding:[{query_emb.tolist()}] => [KNN 1 @embedding score]",
                {"score_field": "score"}
            )
            
            if results and results.docs[0].score >= self.threshold:
                return results.docs[0]['response']
        except Exception as e:
            logger.debug("Semantic cache search failed: %s", e)
        
        return None
    
    async def set(self, query: str, response: str, ttl: int = 3600):
        """存储缓存"""
        query_emb = embed_texts_llm([query])[0]
        
        key = f"llm_cache:semantic:{hash(query)}"
        await self.redis.hset(key, mapping={
            'query': query,
            'response': response,
            'embedding': query_emb.tobytes(),
            'timestamp': time.time()
        })
        await self.redis.expire(key, ttl)
```

### A.2 Query-Aware Re-ranking

```python
# backend/app/rag/qa_chain.py（修改）

def hybrid_retrieve_with_strategy(query: str, top_k: int = 3) -> List[Dict]:
    """带策略的 Hybrid Retrieval"""
    
    # 1. 检索候选
    candidates = hybrid_retrieve(query, top_k=top_k * 3)
    
    # 2. 查询复杂度分类
    strategy = adaptive_rerank_strategy(query, candidates)
    
    # 3. 根据策略 Re-ranking
    if strategy == "skip":
        return candidates[:top_k]
    elif strategy == "single_bge":
        return rerank(query, candidates, top_k=top_k)
    elif strategy == "ensemble":
        return ensemble_rerank(query, candidates, top_k=top_k)
    else:
        return candidates[:top_k]
```

### A.3 WebSocket Streaming

```python
# backend/app/api/websocket.py（新文件）

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any
import json

class WebSocketManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info("WebSocket connected: %s", client_id)
    
    async def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info("WebSocket disconnected: %s", client_id)
    
    async def send_json(self, client_id: str, data: Dict[str, Any]):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(data)

@app.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """WebSocket 端点"""
    manager = WebSocketManager()
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()
            
            # 处理 RAG 查询
            query = data.get("query", "")
            conversation_id = data.get("conversation_id")
            
            # 流式输出
            async for event in rag_query_astream(query, llm, ...):
                await manager.send_json(client_id, event)
            
            # Tool Calling 支持
            if event.get("type") == "tool_call":
                tool_result = await execute_tool(event["tool"], event["args"])
                await manager.send_json(client_id, {
                    "type": "tool_result",
                    "result": tool_result
                })
    
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
```

---

## 📊 预期成果

### 优化后指标

| 指标 | 当前 | 优化后 | 改善 |
|------|------|--------|------|
| **LLM Cache 命中率** | 30% | **50-60%** | +67% |
| **缓存延迟** | 310ms | **3-5ms**（命中时） | -98% |
| **Context Precision** | 0.791 | **0.92-0.96** | +15-22% |
| **TTFT** | 310ms | **<100ms**（缓存） | -68% |
| **API 成本** | $0.001/query | **~$0.0003** | -70% |
| **WebSocket 连接** | 0 | **200+** | ✅ |
| **多轮对话** | ❌ | **✅** | ✅ |
| **Tool Calling** | 有限 | **实时** | ✅ |

---

## 🎯 立即行动

### 本周开始（Day 1-5）

1. ✅ **Semantic Cache 实现** - 最高 ROI
2. ✅ **Negative Detection Cache 优化** - 重新启用（目标文件要求）
3. ✅ **缓存统计** - 监控命中率

### 下周（Day 6-12）

4. ✅ **Query-Aware Re-ranking** - 智能策略
5. ✅ **Ensemble Re-ranking** - 多模型集成
6. ✅ **A/B 测试** - 效果验证

### 第三周（Day 13-21）

7. ✅ **WebSocket 服务器** - 双向通信
8. ✅ **前端 WebSocket 客户端** - 实时交互
9. ✅ **多轮对话** - 状态保持

---

**文档版本**: v1.0
**预计审阅时间**: 15-20 分钟
**下一步**: 确认后进入 writing-plans 阶段
