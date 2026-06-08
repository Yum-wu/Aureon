# KRL-Dutch RAG AI Document Assistant — 交付方案设计

**日期**: 2026-06-08
**版本**: v1.0
**项目**: [KRL-Dutch] RAG AI Document Assistant — Web Chat + Voice
**平台**: Upwork
**预算**: $22-30/hr, 1-3 个月
**策略**: 方案 B — 双轨并行（快速投递 + 深度优化同步）

---

## 一、项目概述

### 1.1 客户需求（来自 JD）

- **行业**: 荷兰金属行业协会（Dutch Metal Industry Association）
- **核心功能**: 质量指南文档问答（Q&A）
- **输入方式**: Text + Voice（browser-native speech-to-text 即可）
- **UI**: 简洁的 Web Chat 界面
- **技术栈**: RAG + Claude/OpenAI API + pgvector + DigitalOcean
- **并发**: 200 用户
- **部署**: DigitalOcean

### 1.2 Aureon 与客户需求匹配度

| 客户需求 | Aureon 现有能力 | 匹配度 | 缺口 |
|----------|----------------|--------|------|
| RAG 文档问答 | 96.5% Recall@3, 0.901 MRR | ⭐⭐⭐⭐⭐ | 无 |
| Web Chat UI | ChatWidget + WebSocket 流式 | ⭐⭐⭐⭐⭐ | 无 |
| Voice 输入 | 无 | ⭐ | Web Speech API 前端实现 |
| 200 并发 | 5 并发饱和 | ⭐⭐ | Semaphore + 多 Worker |
| pgvector | ChromaDB | ⭐⭐⭐ | 可迁移或说服客户用 Chroma |
| DigitalOcean | Railway | ⭐⭐⭐ | Docker 兼容，迁移简单 |
| Claude/OpenAI | DeepSeek + 多 LLM 支持 | ⭐⭐⭐⭐ | MODEL_REGISTRY 已支持 |

**综合匹配度: 85%** — 核心 RAG 能力完全匹配，缺口集中在部署架构和 Voice。

### 1.3 竞争态势

- 20-50 proposals，10 面试中，13 invite 发出
- 客户已经在积极看人 → **时间窗口有限**
- 策略：先投递占位（Week 1），再用深度优化版本升级（Week 3-4）

---

## 二、双轨策略总览

```
Track 1（快速投递）          Track 2（深度优化）
Week 1                       Week 1-3
├─ Prompt 优化               ├─ CRAG 置信度门控
├─ Voice 前端集成            ├─ Multi-Query Expansion
├─ Semaphore 限流            ├─ Post-Generation 自省
├─ WebSocket 管理器          ├─ Query Decomposition
├─ Portfolio MVP             ├─ Gunicorn 多 Worker
├─ Proposal 投递             ├─ Redis Pub/Sub 跨 Worker
└─ 基础测试                  ├─ pgvector 适配
                             ├─ DigitalOcean 部署
                             ├─ 200 并发测试
                             └─ DeepEval 全量回归
                                      │
                              Week 3-4 │
                             ├─ Portfolio 完整版
                             ├─ Demo 视频
                             ├─ Benchmark 白皮书
                             └─ 第二版 Proposal（$25-30/hr）
```

---

## 三、Track 1: 快速投递版（Week 1）

### 3.1 任务清单

| # | 任务 | 时间 | 产出文件 | 预期收益 |
|---|------|------|----------|----------|
| T1.1 | 重写 QA_SYSTEM_PROMPT | 2h | `backend/app/rag/qa_chain.py` | Answer Relevance 0.21→0.55+ |
| T1.2 | 修复 Agent 路径 prompt | 1h | `backend/app/langgraph/nodes/agent.py` | Agent 回答质量对齐 |
| T1.3 | Voice 输入集成 | 3h | `src/hooks/useSpeechRecognition.ts`, `src/components/ChatWidget.tsx` | 浏览器语音输入 |
| T1.4 | Semaphore 限流 | 2h | `backend/app/concurrency.py` | 防雪崩，支撑 200 并发 |
| T1.5 | WebSocket 连接管理器 | 3h | `backend/app/api/ws_manager.py` | 300 连接 + heartbeat |
| T1.6 | Portfolio 页面 MVP | 4h | `src/pages/Portfolio.tsx` | 作品展示 |
| T1.7 | Upwork Proposal | 4h | 文档 | KRL-Dutch 投递 |
| T1.8 | 基础测试 | 2h | `backend/tests/test_concurrency.py`, `src/__tests__/` | 回归验证 |

**总工时: ~21h（5 个工作日）**

### 3.2 Prompt 优化方案

#### QA_SYSTEM_PROMPT 重写要点

基于 `RAG_OPTIMIZATION_PROMPT.md` §三：

1. **禁止行为清单**：禁止以"根据文档"开头、禁止复述文档、禁止总结性语句
2. **正反例对比**：给出正确/错误回答示例，LLM 学习正确模式
3. **回答结构强制**：直接回答(1-2句) → 补充细节 → 引用来源
4. **问题类型自适应**：factual/comparison/how_to/reasoning 分别注入指令

#### Agent 路径修复

`agent.py:54` 的 `full_query` 从简单拼接改为带有完整指令的 prompt。

### 3.3 Voice 集成方案

**技术选型**: Web Speech API（浏览器原生）

```typescript
// src/hooks/useSpeechRecognition.ts
// 使用 webkitSpeechRecognition / SpeechRecognition
// 支持荷兰语（nl-NL）和英语（en-US）
// 自动语言检测：根据知识库语言设置
```

**前端改动**:
- ChatWidget 添加麦克风按钮
- 录音中显示波形动画
- 识别结果自动填入输入框
- 支持持续监听模式（说完自动发送）

**后端改动**: 无。Web Speech API 在浏览器端完成 STT，发送的是文本。

### 3.4 并发限流方案

基于 `RAG_OPTIMIZATION_PROMPT.md` §五 §5.3：

```python
# backend/app/concurrency.py
# LLM API 限流（按模型分组）
# - deepseek-chat: Semaphore(30)
# - dashscope-embedding: Semaphore(50)
# RAG Pipeline 限流
# - rag_pipeline: Semaphore(40)
# 排队超时: 30s，超时返回 503
```

### 3.5 WebSocket 管理器

基于 `RAG_OPTIMIZATION_PROMPT.md` §五 §5.4：

- 最大连接数: 300（预留 50% 余量）
- Heartbeat: 每 30s ping，超时断开
- 连接淘汰: 满载时返回 1013 (Server full)
- 淘汰策略: 最久无活动的连接优先淘汰

### 3.6 Proposal 模板

```
Subject: Aureon RAG Expert — Production-Ready AI Knowledge Base for KRL-Dutch

Hi [Client Name],

I've built Aureon, a production-ready Enterprise AI Knowledge Base Platform
with verified benchmarks that directly match your requirements:

✅ 96.5% Recall@3 (192 QA pairs benchmark)
✅ Real-time WebSocket streaming (200+ concurrent connections)
✅ Web Chat UI with voice input (browser-native STT)
✅ Docker deployment (DigitalOcean compatible)
✅ Multi-LLM support (Claude, OpenAI, DeepSeek)

For your Dutch metal industry quality guide Q&A system, I would:

1. Index your quality guide documents with optimized chunking
2. Deploy a clean Web Chat interface with voice input
3. Set up RAG pipeline with hybrid search (BM25 + Vector)
4. Deploy on DigitalOcean with monitoring

Timeline: MVP in 1-2 weeks, Production-ready in 3-4 weeks.
Rate: $20/hr (首单优惠)

Happy to share a live demo or discuss the technical approach.

Best regards,
[Name]
```

### 3.7 Portfolio 页面

**路由**: `/portfolio`
**布局**:

```
┌─────────────────────────────────────────┐
│  Hero: Enterprise AI Knowledge Base     │
│  "96.5% Recall · 0.901 MRR · 3-5ms"   │
├─────────────────────────────────────────┤
│  4 指标卡片: Recall / MRR / nDCG / WS  │
├─────────────────────────────────────────┤
│  技术架构图（交互式）                    │
├─────────────────────────────────────────┤
│  Demo 截图: Chat + Dashboard + Analytics│
├─────────────────────────────────────────┤
│  Benchmark 数据: 7 个测试结果            │
├─────────────────────────────────────────┤
│  技术栈: React + FastAPI + LangGraph    │
├─────────────────────────────────────────┤
│  Contact: Upwork Profile                │
└─────────────────────────────────────────┘
```

---

## 四、Track 2: 深度优化版（Week 1-3）

### 4.1 RAG 核心优化（Week 1-2）

基于 `RAG_OPTIMIZATION_PROMPT.md` §二~§四：

| # | 任务 | 论文依据 | 预期收益 |
|---|------|----------|----------|
| T2.1 | CRAG 置信度门控 | CRAG (arXiv:2401.15884) | Negative Detection 50%→85%+ |
| T2.2 | LLM Multi-Query Expansion | MultiQueryRetriever | Cross-article 85.7%→90%+ |
| T2.3 | 问题类型自适应 prompt | Adaptive-RAG (NAACL 2024) | Answer Relevance 进一步提升 |
| T2.4 | Post-Generation 自省 | Self-RAG (ICLR 2024) | Negative Detection→90%+ |
| T2.5 | Query Decomposition | Adaptive-RAG | 复杂查询质量提升 |
| T2.6 | 阈值自动调优脚本 | Grid Search | CRAG 阈值最优 F1 |

#### CRAG 置信度门控

```
检索完成 → evaluate_retrieval_confidence()
├─ score ≥ 0.05 → "correct" → 直接生成
├─ 0.01 ≤ score < 0.05 → "ambiguous" → 生成 + ⚠️ 标记
└─ score < 0.01 → "incorrect" → 拒绝回答
```

#### Multi-Query Expansion

```
跨文章查询 → multi_query_llm_rewrite(query, n=3)
→ 并行检索 [q_original, q_v1, q_v2, q_v3]
→ RRF 融合 + 去重
→ top-30 候选池
```

#### Post-Generation 自省

```
生成完成 → SELF_REFLECTION_PROMPT
→ SUPPORTED → 直接输出
→ NOT_SUPPORTED → 标记"信息可能不准确"
→ PARTIAL → 标记"回答可能不完整"
```

### 4.2 并发 + 部署架构（Week 2-3）

基于 `RAG_OPTIMIZATION_PROMPT.md` §五：

| # | 任务 | 预期收益 |
|---|------|----------|
| T2.7 | Gunicorn + 4 Uvicorn Workers | 并发线性扩展 |
| T2.8 | Redis Pub/Sub 跨 Worker | WebSocket 广播 |
| T2.9 | Nginx WebSocket 代理 | 生产级反向代理 + SSL |
| T2.10 | pgvector 适配层 | VectorStoreInterface 抽象 |
| T2.11 | DigitalOcean 部署脚本 | Docker Compose + DO CLI |
| T2.12 | Prometheus + Grafana | 生产监控 |

#### 架构目标

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
                    │   Redis Stack     │  Semantic Cache + Pub/Sub
                    └──────────────────┘
                        │          │
                    ┌───▼────┐ ┌──▼───┐
                    │ Qdrant │ │Qdrant│  gRPC 协议
                    └────────┘ └──────┘
```

#### pgvector 适配策略

**推荐策略：说服客户使用 Chroma**（理由见 §1.2 匹配度分析）。
**备选策略：如果客户坚持 pgvector**，实现 PgVectorStore 适配层（约 4h 工作量）。
**决策时机：** 客户沟通后确认，不阻塞 Track 1 投递。

```python
class VectorStoreInterface:
    """向量存储抽象层，支持 Chroma/pgvector 插拔切换。"""
    async def search(self, query_embedding, top_k, filters=None) -> List[Chunk]
    async def upsert(self, chunks: List[Chunk]) -> None
    async def delete(self, ids: List[str]) -> None
    async def count(self) -> int

class ChromaVectorStore(VectorStoreInterface): ...  # 现有实现
class PgVectorStore(VectorStoreInterface): ...      # 备选，asyncpg + pgvector（仅在客户要求时实现）
```

#### DigitalOcean 部署

- **Droplet**: 4GB RAM ($24/mo) 或 8GB ($48/mo)
- **Services**: App + Redis Stack + Qdrant (Docker Compose)
- **SSL**: Let's Encrypt + Certbot
- **备份**: DO Snapshots + pg_dump (if pgvector)

### 4.3 测试验证（Week 2-3）

| # | 任务 | 目标 |
|---|------|------|
| T2.13 | DeepEval 全量回归 | Negative Detection ≥90%, Answer Relevance >0.50 |
| T2.14 | 200 并发 WebSocket 测试 | 连接稳定 + QPS ≥20 |
| T2.15 | E2E Benchmark v32 | 全套 Benchmark 通过 |
| T2.16 | KRL-Dutch Demo 数据 | 荷兰金属行业示例数据跑通 |

---

## 五、商业准备（Week 3-4）

### 5.1 Portfolio 完整版

在 MVP 基础上添加：
- Benchmark 白皮书（可下载 PDF）
- Demo 视频（60s：Web Chat + Voice + RAG + Dashboard）
- Case Study 模板（KRL-Dutch 交付后填写）

### 5.2 Demo 视频方案

**工具**: Screen Studio 或 OBS Studio
**时长**: 60s
**内容流程**:
1. (0-10s) Landing Page 展示 → "Enterprise AI Knowledge Base Platform"
2. (10-25s) Web Chat 演示 → 输入问题 → 流式回答 + Source 引用
3. (25-35s) Voice 输入演示 → 点击麦克风 → 语音提问 → 回答
4. (35-45s) Dashboard 展示 → 实时指标 + Analytics
5. (45-55s) Benchmark 数据 → 96.5% Recall / 0.901 MRR 大字展示
6. (55-60s) Contact 信息 + CTA

### 5.3 第二版 Proposal

```
报价升级: $25-30/hr
新增卖点:
1. 完整 Benchmark 白皮书（可验证的性能数据）
2. Demo 视频展示
3. Production 部署方案（DO + monitoring + CI/CD）
4. SLA 承诺（Recall≥95%, P99<5s, 99.9% uptime）
5. 200 并发已验证（并发负载测试报告）
```

### 5.3 定价分层

| 阶段 | 范围 | 报价 | 周期 |
|------|------|------|------|
| Phase 1: MVP | Web Chat + Voice + RAG + 基础部署 | $20/hr × 40h = $800 | 1-2 周 |
| Phase 2: Production | 200 并发 + 监控 + pgvector | $25/hr × 40h = $1,000 | 2-3 周 |
| Phase 3: 维护 | 内容更新 + 监控 + 优化 | $200-500/mo | 持续 |

### 5.4 中国市场内容（同步进行）

| 平台 | 频率 | 内容方向 |
|------|------|----------|
| 小红书 | 2-3 篇/周 | "企业 AI 知识库搭建"系列 |
| 知乎 | 1 篇/周 | "RAG 从 0 到 Production"技术深度 |
| V2EX | 1 篇/2 周 | 技术讨论 + 经验分享 |

---

## 六、时间线与里程碑

### Week 1 (6/9-6/15): 快速投递

| Day | 任务 | 里程碑 |
|-----|------|--------|
| Day 1-2 | Prompt 优化 + Voice 集成 + Semaphore | 核心功能就绪 |
| Day 3-4 | WebSocket 管理器 + Portfolio MVP | 展示页面就绪 |
| Day 5 | Proposal 投递 + 基础测试 | ✅ KRL-Dutch 第一版已投递 |

### Week 2 (6/16-6/22): RAG 深度优化

| Day | 任务 | 里程碑 |
|-----|------|--------|
| Day 1-3 | CRAG + Multi-Query + 自适应 prompt | 检索质量提升 |
| Day 4-5 | Post-Generation 自省 + Query Decomposition | 生成质量提升 |
| Day 6-7 | 阈值调优 + 回归测试 | ✅ RAG 核心指标全面提升 |

### Week 3 (6/23-6/29): 并发 + 部署

| Day | 任务 | 里程碑 |
|-----|------|--------|
| Day 1-2 | Gunicorn 多 Worker + Redis Pub/Sub | 并发架构就绪 |
| Day 3-4 | pgvector 适配 + DigitalOcean 部署 | 部署方案就绪 |
| Day 5-7 | 200 并发测试 + DeepEval 回归 + Demo 数据 | ✅ Production-ready |

### Week 4 (6/30-7/6): 商业收尾

| Day | 任务 | 里程碑 |
|-----|------|--------|
| Day 1-2 | Portfolio 完整版 + Benchmark 白皮书 | 展示材料就绪 |
| Day 3-4 | Demo 视频 + Case Study | 营销材料就绪 |
| Day 5-7 | 第二版 Proposal + 投递 | ✅ 高报价投递 / 新项目 |

---

## 七、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| KRL-Dutch 被抢 | 高 | 高 | Week 1 快速投递占位；即使不中，优化成果可用于下一个项目 |
| pgvector 适配耗时 | 中 | 中 | 优先说服客户用 Chroma；pgvector 作为 Phase 2 交付 |
| 200 并发达不到 | 低 | 中 | Gunicorn + Redis Pub/Sub 是成熟方案，风险可控 |
| Voice 在部分浏览器不兼容 | 低 | 低 | Web Speech API 在 Chrome/Edge/Safari 都支持；Firefox 降级为文本输入 |
| 客户预算低于预期 | 中 | 中 | $20/hr 首单已是底线，不再降价；可调整范围而非价格 |

---

## 八、成功标准

### 投递阶段

- [ ] Week 1 结束前 Proposal 已投递
- [ ] Portfolio 页面上线
- [ ] Voice 功能在 Chrome/Edge 可用

### 优化阶段

- [ ] Negative Detection ≥90%（当前 50%）
- [ ] Answer Relevance >0.50（当前 0.21）
- [ ] Cross-article Recall ≥90%（当前 85.7%）
- [ ] 200 WebSocket 连接稳定
- [ ] E2E Latency <2,500ms（当前 3,104ms）
- [ ] DeepEval Pass Rate 100%（当前 100%，保持）

### 交付阶段

- [ ] KRL-Dutch 客户满意交付
- [ ] 评价 ≥4.8/5.0
- [ ] 后续维护合同（$200-500/mo）

---

## 九、参考文献

| 资源 | 用途 |
|------|------|
| `docs/RAG_OPTIMIZATION_PROMPT.md` | RAG 优化技术方案（本设计的技术基础） |
| `目标.md` v31 | Aureon 商业路线图 + Benchmark 数据 |
| CRAG (arXiv:2401.15884) | 检索质量三路分支 |
| Self-RAG (ICLR 2024) | Post-Generation 自省 |
| Adaptive-RAG (NAACL 2024) | Query 复杂度分类 + Decomposition |
| RGB Benchmark (AAAI 2024) | Negative Rejection 定义 |

---

*设计版本: v1.0*
*最后更新: 2026-06-08*
*策略: 方案 B — 双轨并行*
