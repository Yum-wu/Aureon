---
title: "Aureon 平台概览 - 常见问题"
slug: "aureon-faq-overview"
language: "zh"
source: "aureon-faq"
---

# Aureon 平台概览 - 常见问题

## Aureon 是什么？

Aureon 是一个**企业级 AI 知识库平台**，基于 FastAPI（后端）+ React 19（前端）构建。它是一个生产级的检索增强生成（RAG）系统，帮助企业将内部文档索引化，并通过自然语言查询获得 AI 驱动的、有来源引用的答案。

**核心价值**：将企业散落的知识统一管理，让员工和客户通过对话式 AI 快速找到准确答案。

## Aureon 能做什么？

Aureon 提供以下核心能力：

1. **智能搜索**：基于 RAG 技术的语义搜索，支持混合检索（BM25 + 向量 + RRF 融合）
2. **知识管理**：上传文档（.md、.txt、.pdf、.docx、.xlsx），自动分块、索引
3. **对话式 AI**：WebSocket 实时聊天，支持工具调用、文件附件、来源引用
4. **企业管理**：用户管理、角色权限（RBAC）、审计日志、多租户隔离
5. **成本治理**：Token 用量追踪、预算管理、成本趋势分析
6. **可观测性**：LangFuse 链路追踪、Prometheus 指标、结构化日志

## Aureon 的性能指标如何？

| 指标 | 数值 | 说明 |
|------|------|------|
| 检索准确率 | **96.5%** | Recall@3，基于 192 个 QA 对 |
| Recall@10 | **100%** | Top-10 完全召回 |
| 首 Token 延迟 | **~310ms** | 流式 RAG TTFT |
| 单次查询成本 | **~$0.001** | Qwen 定价 |
| 负例检测率 | **100%** | LLM 分类器 + 检索阈值双重防御 |
| 缓存命中率 | **78%** | 多级缓存（语义 + Redis） |
| 上下文精确度 | **92%** | 检索结果相关性 |
| 忠实度 | **97%** | 答案基于来源的准确度 |
| TTFT 提升 | **61%** | 优化后（并行检索+缓存预热+流式） |

## Aureon 支持哪些 LLM 模型？

**主力模型**：
- **Qwen 3.5 Flash**（阿里云 DashScope）— 默认模型
- **GLM-4-Flash**（智谱 AI）— 备用模型

**扩展支持**：
- GPT-4o（OpenAI）
- Claude（Anthropic）

**Embedding 模型**：
- 智谱 AI embedding-2（1024 维）
- DashScope text-embedding-v4（1024 维）
- SiliconFlow BGE-large-zh-v1.5 / BGE-M3（稀疏向量）

**Rerank 模型**：
- DashScope qwen3-rerank
- Cohere rerank-multilingual-v3.0
- 支持集成多模型重排序

## Aureon 的架构是什么？

Aureon 采用模块化的 RAG 流水线架构：

```
用户查询 → 意图分类 → 混合检索（BM25+ + RRF + 父子文档）→ MMR 重排序 → Prompt 组装 → LLM 生成 → 引用注入 → SSE 流式输出
```

**关键组件**：
- **查询分类器**：按复杂度路由（简单/中等/复杂）
- **查询重写**：多查询变体扩展召回
- **HyDE**：假设文档嵌入，提升复杂查询效果
- **CRAG**：纠正性 RAG，基于置信度阈值
- **语义缓存**：0.92 余弦相似度阈值去重
- **多级记忆**：L0-L3 四层记忆系统

## Aureon 的技术栈是什么？

**后端**：
- Python 3.12 + FastAPI
- LangChain + LangGraph
- Qdrant（向量数据库）
- Redis（缓存）
- SQLite（本地存储）

**前端**：
- React 19 + TypeScript
- Vite + Tailwind CSS 4
- React Query（数据获取）

**基础设施**：
- Docker 容器化
- Railway 一键部署
- GitHub Actions CI/CD
