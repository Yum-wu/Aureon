# Aureon 架构说明

本文档是 Aureon 的公开技术说明，介绍运行时架构、主要子系统和核心请求流，不暴露内部规划记录。

## 概览

Aureon 是一个全栈企业级 AI 知识库平台：

- 前端：React 19、TypeScript、Vite、Tailwind CSS 4
- 后端：FastAPI、LangGraph、LangChain
- 检索：Qdrant 稀疏 + 稠密混合检索
- 缓存：Redis
- 部署：Docker + GitHub Actions + Railway

## 高层架构

```text
浏览器 UI
  -> FastAPI API
  -> LangGraph 工作流
  -> 检索流水线
     -> 稀疏检索
     -> 稠密检索
     -> 重排序
  -> LLM 生成答案
  -> SSE 流式返回前端
```

## 主要子系统

### 前端

- 落地页与 demo 入口
- 搜索界面
- 文档管理
- 分析页面
- 管理与配置页面
- 中英文双语界面

### 后端

- Chat 与 RAG API
- SSE 流式响应
- 文档上传与索引
- 认证与 RBAC
- 审计日志与安全控制
- 成本与可靠性接口

### 检索层

- Qdrant 作为向量后端
- 稀疏 + 稠密混合检索
- 按查询复杂度做路由
- 生成前进行重排序
- 返回带引用来源的答案

## 请求流程

1. 用户在 UI 提交问题。
2. FastAPI 接收请求。
3. LangGraph 协调检索与生成流程。
4. 查询路由器选择检索策略。
5. Qdrant 返回候选 chunk。
6. 重排序筛选并重排候选结果。
7. LLM 基于检索上下文生成答案。
8. 后端将答案和引用通过流式方式返回前端。

## 安全模型

- 受保护接口支持 API key
- 基于 JWT 的身份认证
- RBAC 角色校验
- 多租户隔离
- 审计日志
- PII 脱敏
- Prompt Injection 防护

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

## 部署模型

- 源码托管在 GitHub
- CI 运行在 GitHub Actions
- 应用部署到 Railway
- Demo 由公网生产地址提供

## 相关文档

- [README.md](../README.md)
- [README.zh-CN.md](../README.zh-CN.md)
- [SECURITY.md](../SECURITY.md)
