---
title: "Aureon API 使用指南 - 常见问题"
slug: "aureon-faq-api"
language: "zh"
source: "aureon-faq"
---

# Aureon API 使用指南 - 常见问题

## 有哪些 API 端点？

Aureon 提供以下核心 API：

### 聊天 API
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/stream` | Agent SSE 流式聊天 |
| POST | `/api/chat/enhanced/stream` | Chat + RAG 增强流式 |
| WS | `/ws/chat/{client_id}` | WebSocket 实时聊天 |

### RAG API
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/rag/query` | RAG 查询（非流式） |
| POST | `/api/rag/query/stream` | RAG 查询（SSE 流式） |
| POST | `/api/rag/upload` | 上传并索引文档 |
| POST | `/api/rag/index` | 重建索引 |
| GET | `/api/rag/uploads` | 列出已上传文件 |
| DELETE | `/api/rag/upload/{filename}` | 删除文档 |
| GET | `/api/rag/health` | RAG 系统健康检查 |
| GET | `/api/rag/stats` | RAG 统计信息 |

### 管理 API
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 系统健康检查 |
| GET | `/health/ready` | 就绪探针 |
| GET | `/metrics` | Prometheus 指标 |

### 安全 API
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/security/sso/login` | SSO 登录 |
| POST | `/api/security/pii/detect` | PII 检测 |
| POST | `/api/security/pii/mask` | PII 脱敏 |

## 如何使用 RAG 查询 API？

### 流式查询（推荐）

```bash
curl -X POST https://your-domain/api/rag/query/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "Aureon 有什么功能？"}'
```

响应为 SSE 格式：
```
data: {"type": "text", "content": "Aureon 是"}
data: {"type": "text", "content": "一个企业级"}
data: {"type": "sources", "sources": [...]}
data: {"type": "done"}
```

### 非流式查询

```bash
curl -X POST https://your-domain/api/rag/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "Aureon 有什么功能？"}'
```

响应：
```json
{
  "answer": "Aureon 是一个企业级 AI 知识库平台...",
  "sources": [
    {"title": "平台概览", "snippet": "...", "score": 0.95}
  ],
  "latency_ms": 310
}
```

## 如何上传文档？

```bash
curl -X POST https://your-domain/api/rag/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@document.md" \
  -F "language=zh" \
  -F "title=文档标题"
```

**支持格式**：.md、.txt、.pdf、.docx、.xlsx
**大小限制**：10MB
**权限**：需要 Editor 或更高角色

## 如何删除文档？

```bash
curl -X DELETE https://your-domain/api/rag/upload/document-name.md \
  -H "X-API-Key: your-api-key"
```

## 如何重建索引？

```bash
curl -X POST https://your-domain/api/rag/index \
  -H "X-API-Key: your-api-key"
```

**注意**：重建索引会清除缓存，耗时取决于文档数量。

## 认证方式有哪些？

### 方式一：API Key

在请求头中添加：
```
X-API-Key: your-api-key
```

### 方式二：JWT Token

```bash
# 先登录获取 token
curl -X POST https://your-domain/api/security/sso/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# 使用 token
curl -H "Authorization: Bearer <token>" https://your-domain/api/rag/query
```

## 角色权限如何划分？

| 角色 | 权限 |
|------|------|
| **Super Admin** | 所有权限 |
| **Admin** | 用户管理、工作空间、审计、功能开关、SSO、成本 |
| **Editor** | 文档上传、编辑、删除 |
| **Viewer** | 只读访问 |

## 如何获取系统指标？

```bash
# Prometheus 格式
curl https://your-domain/metrics

# JSON 格式健康检查
curl https://your-domain/api/health
```

## API 限流规则

- 默认限流：60 请求/分钟
- LangGraph 执行：5 请求/分钟
- 可通过环境变量配置

## 错误码说明

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证（缺少或无效的 API Key/JWT） |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 429 | 请求过于频繁（限流） |
| 500 | 服务器内部错误 |
