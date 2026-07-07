# Aureon 架构说明

本文档是 Aureon 的技术架构概述，介绍运行时架构、主要子系统和核心请求流。

## 概览

Aureon 是一个全栈企业级 AI 知识库平台：

- 前端：React 19、TypeScript、Vite、Tailwind CSS 4
- 后端：FastAPI、LangGraph、LangChain
- 检索：Qdrant 稀疏 + 稠密混合检索
- 缓存：Redis
- 部署：Docker + GitHub Actions + Railway

## 高层架构

```text
┌─────────────────────────────────────────────────────────────┐
│                    浏览器 (React 19)                          │
│   Landing  Search  Chat  Documents  Analytics  Admin         │
│   Tailwind CSS 4  ·  i18n (en/zh)  ·  Zustand 状态管理      │
└──────────┬──────────────────────────────────────────────────┘
           │  HTTP/SSE /ws
           ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI API 层 (ASGI)                           │
│                                                              │
│  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Auth/MW    │ │ Middleware  │ │ Routers  │ │ SSE Stream │ │
│  │ JWT + API  │ │ CORS/Tenant│ │ chat/rag │ │ 零缓冲推送 │ │
│  │ Key + RBAC │ │ Rate Limit │ │ crew/... │ │            │ │
│  └────────────┘ └────────────┘ └─────┬────┘ └────────────┘ │
└──────────────────────────────────────┼──────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│              LangGraph 工作流引擎                             │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Agent 层      │  │ 工具调用层    │  │ 工作流编排          │  │
│  │ LLM Factory   │  │ @tool 装饰器  │  │ 有状态图编排        │  │
│  │ 多模型支持     │  │ 可组合函数    │  │ 条件路由/分支       │  │
│  │ Qwen3/GLM4/  │  │ 安全沙箱      │  │ 循环/中断/恢复     │  │
│  │ Reasoning    │  │              │  │                    │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└──────────────────────────────────────┬──────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    RAG 检索管线                                │
│                                                              │
│  ┌──────────┐  ┌────────────┐  ┌────────────┐ ┌──────────┐  │
│  │Query     │→ │ 混合检索    │→ │ 后处理      │→│ 答案生成   │  │
│  │Router    │  │ (Hybrid)   │  │ (Post-    │ │ (QA Chain)│  │
│  │简单→稀疏  │  │            │  │ retrieval) │ │          │  │
│  │中等→混合  │  │ 稠密向量    │  │ Reranking  │ │ HyDE     │  │
│  │复杂→HyDE │  │ BGE-M3     │  │ CRAG评估   │ │ 增强prompt│  │
│  │ +MultiQ  │  │ 1024d      │  │ 负例检测    │ │ 引用来源   │  │
│  │          │  │ 稀疏向量    │  │ 上下文压缩  │ │          │  │
│  └──────────┘  │ BM25-like  │  └────────────┘ └──────────┘  │
│                └────────────┘                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Qdrant 向量数据库 (SaaS Cloud)                       │    │
│  │  HNSW m=32 · INT8 量化 · 稀疏+稠密混合 (RRF 融合)      │    │
│  │  文档摄取管线: Extractor → Normalizer → Chunk → QC    │    │
│  │  ParentChildSplitter (1500/512) · Contextual Prefix   │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────┬──────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   基础设施与支撑层                              │
│                                                              │
│  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ 记忆系统   │ │ 缓存层    │ │ 安全层    │ │ 可观测性      │  │
│  │ L0 原始对话│ │ Redis    │ │ PII脱敏   │ │ LangFuse     │  │
│  │ L1 原子事实│ │ 内存缓存  │ │ Prompt    │ │ 全链路追踪    │  │
│  │ L2 场景总结│ │ 语义缓存  │ │ Injection │ │ 延迟/成本/    │  │
│  │ L3 用户画像│ │ 去重     │ │ Guardrails│ │ 质量指标     │  │
│  │ 上下文卸载 │ │          │ │ SSO/JWT   │ │              │  │
│  └───────────┘ └──────────┘ └───────────┘ └──────────────┘  │
│                                                              │
│  ┌───────────┐ ┌────────────┐ ┌───────────┐                │
│  │ 多租户    │ │ 可靠性      │ │ 成本管理   │                │
│  │ JWT 签名  │ │ 熔断器     │ │ Redis TS  │                │
│  │ Tenant    │ │ Event Src  │ │ Budget    │                │
│  │ 隔离      │ │ SLO 监控   │ │ 限流      │                │
│  └───────────┘ └────────────┘ └───────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## 主要子系统

### 前端

用户界面层基于 React 19，涵盖以下功能模块：

- **落地页与 Demo 搜索入口**：产品展示与快速体验
- **Chat 对话界面**：消息输入框、流式渲染 Markdown、引用标注悬浮卡 (hover card)、操作栏（复制/重新生成/投票）
- **搜索功能**：增删查询参数、知识探索视图
- **Support Widget**：FAB 浮动按钮 → 聊天面板、消息持久化 (localStorage)、10s 延迟问候、未读徽章 (99+)
- **文档管理**：上传、列表、搜索、删除
- **引导流程**：Viewer 3 步 / Editor+ 5 步
- **分析仪表盘**：RAG 使用统计、Token 用量、延迟监控
- **管理与配置面板**：用户管理、系统设置
- **国际化**：中英文双语界面，34 个 Support 模块键
- **样式系统**：Tailwind CSS 4 + tailwindcss-animate、Design Token (oklch 色域)、Plus Jakarta Sans / Inter / JetBrains Mono 字体

### 后端

FastAPI 应用为无状态 REST + SSE 并行服务，结构化模块如下：

| 层 | 模块 | 职责 |
|---|------|------|
| **API** | `routers/` | chat/rag/crew/support 端点，SSE 流式输出 |
| **Agent** | `agent/` | LLM 工厂 (multi-model)、Agent 工厂、流式执行器 (astream_events v2) |
| **工具** | `tools/` | `@tool` 装饰器注册 → `ALL_TOOLS`，类型注解 + docstring |
| **工作流** | `langgraph/` | 有状态图编排，条件路由 / 循环 / 中断恢复 + MCP |
| **RAG** | `rag/` | 检索管线 (HyDE/混合检索/CRAG/重排序)、文档摄取、查询路由、质量门禁 |
| **记忆** | `memory/` | L0-L3 四层递进记忆 + 上下文卸载至外部 Markdown |
| **缓存** | `cache/` | Redis + 内存双缓存、语义缓存去重 |
| **安全** | `security/` | PII 检测脱敏、Prompt Injection 防护 (Guardrails)、SSO/Fernet 加密 |
| **多租户** | `multi_tenant/` | JWT 签名验证 tenant_id、ASGI 中间件隔离 |
| **可观测** | `observability/` | LangFuse 全链路追踪 (init → handler → shutdown) |
| **成本** | `cost/` | Token/API 成本追踪、Redis 时间序列 Budget |
| **可靠性** | `reliability/` | 熔断器、事件溯源、SLO 监控、备份 |
| **审计** | `audit/` | 操作日志、用户行为审计 |
| **数据库** | `database/` | PostgreSQL (asyncpg) 连接管理、迁移 (Alembic) |
| **中间件** | `middleware/` | CORS、多租户隔离、Rate Limiting、Tenant 解析 |

### 检索层

RAG 系统为多策略自适应管线：

- **向量数据库**：Qdrant Cloud，BGE-M3 1024d dense + 稀疏向量 hybrid (RRF 融合)
- **查询路由**：`Query Router` 根据查询复杂度分发至三条 pipeline
  - 简单查询 → 纯稀疏向量检索（< 10ms 低延迟）
  - 中等查询 → 混合检索 + 重排序
  - 复杂查询 → HyDE + Multi-Query + 混合检索 + CRAG 评估
- **检索增强**：RRF 融合系数 k=60 · INT8 量化 · HNSW m=32 ef=200/128
- **重排序**：自适应策略，top1/top2 分差大时跳过节省延迟
- **纠正机制 (CRAG)**：基于 embedding 相似度的轻量级评估（~50ms），三路动作：correct/ambiguous/incorrect
- **文档摄取**：Pipeline 包含 `Extractor → Normalizer → Chunk → Quality Gate`
  - ParentChildSplitter: parent 1500 字符 / child 512 字符 / overlap 80
  - Contextual Retrieval 前缀增强
  - 并发控制 Semaphore(5)，~10min/1000 文档
- **负例检测**：关键词快速路径 + LLM 分类器
- **质量评估**：Recall + Faithfulness + 延迟基准

### 记忆系统

递进式记忆，解决 Agent 长上下文丢失问题：

| 层 | 存储 | 内容 | 容量 |
|---|------|------|------|
| L0 | PostgreSQL conversations | 原始对话消息 | 完整历史 |
| L1 | PostgreSQL atoms | 原子事实三元组 | 关键信息 |
| L2 | offloads/scenarios/\*.md | 场景级上下文摘要 | ≤3 个场景 |
| L3 | offloads/persona.md | 用户画像（偏好/风格/背景） | ≤2KB |

- **上下文卸载**：长工具输出外存至 `offloads/refs/*.md`，按需按片段加载，避免注意力稀释

## 核心请求流

### Chat + RAG 流

```text
用户提问 ──→ 前端 Chat UI
                │
                ▼ POST /api/chat/enhanced/stream
         FastAPI 接收请求（JWT 验证 → 租户解析 → Rate Limit）
                │
                ▼
         LangGraph 启动有状态图
                │
                ├── Agent 选择工具 / 直接回答
                │   ├── 调用工具 → 工具结果注入
                │   └── 直接回答 → 跳至生成
                │
                ├── 本 RAG 分支：Query Router 分类
                │   ├── 简单 → 纯稀疏检索
                │   ├── 中等 → 混合检索 + Rerank
                │   └── 复杂 → HyDE + Multi-Query + CRAG
                │
                ├── Qdrant 混合检索
                │   ├── 稠密向量相似度搜索 (BGE-M3)
                │   ├── 稀疏向量关键词匹配
                │   └── RRF 融合 top-k 候选项
                │
                ├── 后处理
                │   ├── Reranking 重排序
                │   ├── CRAG 质量评估 (correct/ambiguous/incorrect)
                │   ├── 负例检测（超出知识库范围则拒绝回答）
                │   └── 上下文压缩过滤低相关片段
                │
                ├── 答案生成 (QA Chain)
                │   ├── HyDE 假设文档增强
                │   ├── LLM 以检索上下文生成答案
                │   └── 引用来源标注
                │
                └── SSE 流式返回
                    ├── session → 会话初始化
                    ├── text → 逐 Token 回答文本
                    ├── tool_start/tool_end → 工具调用信息
                    ├── done → 完成信号（含引用来源）
                    └── error → 错误处理
```

### LangGraph 工作流

有向图编排，非简单线性流水线：

- 节点（Agent, Tool, RAG, Generate）通过边连接
- 条件路由基于 Agent 输出动态选择后继节点
- 支持循环（Agent 多轮工具调用）和中断恢复（人工审批节点）
- 所有边附带 LangFuse 追踪 trace

### 详细 RAG Pipeline

```
查询复杂分类 ──→                          HyDE (假设文档增强)
                           ┌────────────────────┐
Query Vector ─────────────→│   BGE-M3 稠密检索    │─→┐
                           │   top_k × 12 候选    │  │
                           └────────────────────┘  │  ┌──────────┐
                                                   ├─→│ RRF 融合  │─→ Rerank → QA
                           ┌────────────────────┐  │  │ k=60     │
Sparse Vector ────────────→│  稀疏向量关键词检索   │─→┘  └──────────┘
                           │   BGE-M3 sparse    │
                           └────────────────────┘
```

## 安全模型

多层纵深防御架构：

| 层 | 措施 | 说明 |
|---|------|------|
| **传输层** | HTTPS | 所有 API 端点强制 TLS |
| **认证** | API Key / JWT | API Key 通过 `X-API-Key` header 校验（白名单：health 端点），JWT 用于 SSO/RBAC |
| **授权** | RBAC | 三级角色：VIEWER / EDITOR / ADMIN，中间件逐路由校验 |
| **租户隔离** | JWT 签发 tenant_id | ASGI TenantMiddleware 解析 → 全模块 tenant 过滤 |
| **防注入** | Prompt Injection Guardrails | 用户输入检测，可疑内容标记/阻断 |
| **数据隐私** | PII 脱敏 | Fernet 对称加密敏感字段，审计日志脱敏存储 |
| **速率限制** | Token Bucket | 基于 Redis 的分布式限流，租户级隔离 |
| **CORS** | 显式 allow_headers | 列出所有允许 header，不暴露通配符 `*` |
| **审计日志** | structured audit | user_id + action + resource + timestamp 不可篡改记录 |

## 核心公开数据概念

### Document

上传到知识库中的源文件。

关键字段：

- filename
- source
- language
- upload status

### Chunk

从文档切分出来的检索单元。

关键字段：

- text
- parent document
- language
- source metadata

### Query

用户从搜索或对话发出的提问。

关键字段：

- query text
- session 或 user context
- selected retrieval path

### Answer

返回给用户的生成答案。

关键字段：

- response text
- cited sources
- stream events

## 技术栈

| 类别 | 组件 |
|------|------|
| **运行时** | Python 3.12 / Node.js 20+ / Docker |
| **Web 框架** | FastAPI (ASGI) / React 19 + Vite |
| **AI 框架** | LangChain + LangGraph (有状态 Agent 编排) |
| **LLM** | Qwen3.5-Flash (主) / GLM-4-Flash (备用) / Reasoning 模型 |
| **向量数据库** | Qdrant Cloud (BGE-M3 1024d, INT8, RRF) |
| **Embedding** | DashScope (主) / SiliconFlow / Zhipu (降级链) |
| **缓存** | Redis (分布式) + 应用内存 (热点) |
| **数据库** | PostgreSQL + asyncpg |
| **可观测** | LangFuse (链路追踪 + Prompt Management) |
| **样式** | Tailwind CSS 4 + Design Token (oklch) |
| **i18n** | react-i18next (en / zh) |

## 部署模型

- **源码托管**：GitHub
- **CI/CD**：GitHub Actions — pip-audit + Trivy + hadolint + mypy (非阻断) + ruff lint + pytest (1011 tests 全部通过)
- **部署平台**：Railway，新加坡区域，自动部署
- **容器**：Docker `python:3.12-slim`，非 root 运行
- **生产地址**：`https://aureon-production-659a.up.railway.app`
- **配套服务**：Railway Redis + Qdrant Cloud (独立 SaaS)
- **自动休眠**：Railway 空闲休眠，冷启动 ~15s P95

## 相关文档

- [README.md](../README.md)
- [README.zh-CN.md](../README.zh-CN.md)
- [SECURITY.md](../SECURITY.md)
