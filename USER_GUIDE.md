# Aureon 用户手册

**版本**: 2026-06-23  
**在线访问**: https://aureon-production-659a.up.railway.app

---

## 目录

1. [快速开始](#1-快速开始)
2. [智能搜索](#2-智能搜索)
3. [文档管理](#3-文档管理)
4. [仪表盘](#4-仪表盘)
5. [分析页面](#5-分析页面)
6. [客服助手](#6-客服助手)
7. [管理功能](#7-管理功能)
8. [API 使用](#8-api-使用)
9. [常见问题](#9-常见问题)

---

## 1. 快速开始

### 1.1 登录

访问 https://aureon-production-659a.up.railway.app/login

**登录方式**：
- **演示账号**：点击「使用演示账号登录」按钮
- **邮箱密码**：输入邮箱和密码（需管理员配置）
- **SSO 登录**：Google 或 GitHub 账号（需配置）

### 1.2 首次引导

首次登录后，系统会自动启动引导流程：

| 步骤 | 页面 | 内容 |
|------|------|------|
| 1/5 | 搜索 | 体验智能搜索（已预填示例查询） |
| 2/5 | 文档 | 上传您的第一个文档 |
| 3/5 | 搜索 | 搜索您自己的数据 |
| 4/5 | 仪表盘 | 查看系统健康状态 |
| 5/5 | 分析 | 了解使用模式 |

**提示**：可随时点击「跳过」按钮跳过引导。

---

## 2. 智能搜索

### 2.1 基本搜索

1. 访问 `/search` 页面
2. 在搜索框输入问题
3. 按 Enter 或点击搜索按钮
4. 等待 AI 返回带来源引用的答案

**示例查询**：
- "这个平台能做什么？"
- "如何部署 Aureon？"
- "支持哪些 LLM 模型？"

### 2.2 搜索结果

搜索结果包含：
- **AI 答案**：基于知识库生成的精准回答
- **来源引用**：答案中标注了 `[1]`、`[2]` 等引用标记
- **来源列表**：右侧显示引用的文档来源和相关度评分

### 2.3 搜索技巧

- **具体问题**：越具体的问题，答案越精准
- **使用关键词**：包含关键术语可提高检索准确率
- **多语言支持**：支持中英文混合查询

---

## 3. 文档管理

### 3.1 查看文档

访问 `/documents` 页面查看所有已索引的文档。

**文档列表显示**：
- 文档名称
- 来源
- 格式（MD、PDF、DOCX、XLSX、TXT）
- 片段数
- 状态
- 操作（删除）

**分页功能**：
- 默认每页显示 20 条
- 可选择 10/20/50/100 条
- 支持翻页导航

### 3.2 上传文档

1. 点击「上传文档」按钮
2. 选择文件（支持拖拽）
3. 等待上传和索引完成

**支持格式**：
| 格式 | 说明 |
|------|------|
| .md | Markdown 格式（推荐） |
| .txt | 纯文本格式 |
| .pdf | PDF 文档 |
| .docx | Word 文档 |
| .xlsx | Excel 表格 |

**限制**：
- 单文件最大 10MB
- 文件名不能包含特殊字符

### 3.3 删除文档

1. 在文档列表中找到要删除的文档
2. 点击「删除」按钮
3. 确认删除操作

**注意**：删除操作不可撤销，文档及其所有索引片段将被永久删除。

### 3.4 搜索文档

在搜索框中输入关键词，可按文档名称或来源筛选。

---

## 4. 仪表盘

访问 `/dashboard` 页面查看系统实时状态。

### 4.1 Golden Signals

四大核心指标：

| 指标 | 说明 | 正常范围 |
|------|------|----------|
| 延迟 | 查询响应时间 | < 1000ms |
| 流量 | 每秒查询数 | 视业务而定 |
| 错误率 | 失败查询比例 | < 1% |
| 饱和度 | 系统负载 | < 80% |

### 4.2 RAG 流水线

显示检索和生成的耗时分布：
- **检索**：BM25 + 向量检索时间
- **重排序**：结果重排序时间
- **生成**：LLM 生成答案时间

### 4.3 系统健康

显示各组件状态：
- API 服务器
- 索引状态
- Redis 缓存
- Qdrant 向量库

### 4.4 查询量趋势

显示最近 7 天的查询量变化趋势图。

### 4.5 缓存命中率

显示缓存命中率趋势，帮助优化缓存策略。

---

## 5. 分析页面

访问 `/analytics` 页面查看详细使用分析。

### 5.1 Token 消耗

- **输入 Token**：查询消耗的 Token
- **输出 Token**：答案生成的 Token
- **总消耗**：累计 Token 使用量

### 5.2 时间范围

支持选择不同时间范围：
- 最近 1 小时
- 最近 6 小时
- 最近 24 小时
- 最近 7 天
- 最近 30 天

### 5.3 查询统计

- 查询总数
- 平均延迟
- 缓存命中率

### 5.4 延迟分布

显示查询延迟的分布情况，帮助识别性能瓶颈。

---

## 6. 客服助手

### 6.1 打开客服

点击页面右下角的蓝色圆形按钮，打开客服助手面板。

### 6.2 快捷回复

客服助手提供 4 个快捷回复按钮：
- "这个平台能做什么？"
- "如何部署到生产环境？"
- "支持哪些 LLM 模型？"
- "性能指标怎么样？"

### 6.3 自由提问

在输入框中输入问题，按 Enter 发送。

**支持的问题类型**：
- 平台功能咨询
- 部署配置问题
- API 使用问题
- 性能优化建议
- 故障排除

### 6.4 关闭客服

点击面板右上角的 × 按钮关闭客服面板。

---

## 7. 管理功能

**注意**：以下功能仅对管理员角色可见。

### 7.1 用户管理

访问 `/admin` → 「用户管理」标签页。

**功能**：
- 查看用户列表
- 邀请新用户
- 修改用户角色
- 禁用/启用用户
- 删除用户

**角色权限**：
| 角色 | 权限 |
|------|------|
| Viewer | 只读访问 |
| Editor | 上传、编辑、删除文档 |
| Admin | 用户管理、系统配置 |

### 7.2 审计日志

访问 `/admin` → 「审计日志」标签页。

**记录的操作**：
- 用户登录/登出
- 文档上传/删除
- 配置变更
- API 调用

**导出功能**：支持导出为 CSV 或 JSON 格式。

### 7.3 系统配置

访问 `/admin` → 「系统配置」标签页。

**可配置项**：
- LLM 模型选择
- 缓存策略
- 速率限制
- 安全设置

---

## 8. API 使用

### 8.1 认证

所有 API 请求需要在 Header 中添加认证信息：

```bash
# 使用 API Key
curl -H "X-API-Key: your-api-key" https://aureon-production-659a.up.railway.app/api/health

# 使用 JWT Token
curl -H "Authorization: Bearer your-jwt-token" https://aureon-production-659a.up.railway.app/api/health
```

### 8.2 RAG 查询 API

**流式查询**（推荐）：

```bash
curl -X POST https://aureon-production-659a.up.railway.app/api/rag/query/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "Aureon 有什么功能？"}'
```

**非流式查询**：

```bash
curl -X POST https://aureon-production-659a.up.railway.app/api/rag/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "Aureon 有什么功能？"}'
```

### 8.3 文档上传 API

```bash
curl -X POST https://aureon-production-659a.up.railway.app/api/rag/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@document.md" \
  -F "language=zh" \
  -F "title=文档标题"
```

### 8.4 健康检查 API

```bash
# 基本健康检查
curl https://aureon-production-659a.up.railway.app/api/health

# 就绪检查（包含 Redis/Qdrant 状态）
curl https://aureon-production-659a.up.railway.app/health/ready
```

### 8.5 完整 API 列表

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /api/health | 健康检查 | 无 |
| GET | /health/ready | 就绪检查 | 无 |
| POST | /api/rag/query | RAG 查询 | API Key |
| POST | /api/rag/query/stream | RAG 流式查询 | API Key |
| POST | /api/rag/upload | 上传文档 | Editor+ |
| DELETE | /api/rag/upload/{fn} | 删除文档 | Editor+ |
| GET | /api/rag/uploads | 列出文档 | Viewer+ |
| POST | /api/rag/index | 重建索引 | Editor+ |
| POST | /api/rag/cache/clear | 清除缓存 | Admin |
| GET | /api/rag/stats | RAG 统计 | API Key |
| GET | /api/rag/health | RAG 健康 | API Key |
| POST | /api/chat/stream | 聊天流式 | API Key |
| GET | /metrics | Prometheus | 无 |
| WS | /ws/chat/{id} | WebSocket 聊天 | Token |

---

## 9. 常见问题

### 9.1 搜索没有结果

**可能原因**：
1. 知识库为空 → 上传相关文档
2. 查询太具体 → 尝试更通用的查询
3. 语言不匹配 → 检查文档语言

**解决方法**：
- 上传相关文档到知识库
- 使用更通用的关键词
- 尝试同义词或相关表述

### 9.2 上传文档失败

**可能原因**：
1. 文件格式不支持 → 检查文件扩展名
2. 文件过大 → 超过 10MB 限制
3. 权限不足 → 需要 Editor 角色

**解决方法**：
- 转换为支持的格式
- 压缩或拆分文件
- 联系管理员提升权限

### 9.3 LLM 响应很慢

**可能原因**：
1. API 限流 → 检查 API Key 配额
2. 网络延迟 → 检查网络连接
3. 并发过高 → 等待或联系管理员

**解决方法**：
- 检查 API Key 配额
- 使用缓存减少重复查询
- 联系管理员优化配置

### 9.4 登录失败

**可能原因**：
1. 密码错误 → 重置密码
2. 账号被禁用 → 联系管理员
3. SSO 配置问题 → 检查 SSO 设置

**解决方法**：
- 使用演示账号登录
- 联系管理员重置密码
- 检查 SSO 配置

### 9.5 页面加载很慢

**可能原因**：
1. 网络问题 → 检查网络连接
2. 浏览器缓存 → 清除缓存
3. 服务器负载 → 等待或联系管理员

**解决方法**：
- 刷新页面（Ctrl+Shift+R）
- 清除浏览器缓存
- 联系管理员检查服务器状态

---

## 10. 快捷键

| 快捷键 | 功能 |
|--------|------|
| Enter | 发送消息/执行搜索 |
| Esc | 关闭弹窗/取消操作 |
| Ctrl+K | 打开搜索框 |
| Ctrl+/ | 打开帮助 |

---

## 11. 联系支持

- **客服助手**：页面右下角蓝色按钮
- **邮箱**：support@aureon.ai
- **文档**：https://docs.aureon.ai

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端框架 | React 19 + TypeScript + Vite |
| 样式 | Tailwind CSS 4 |
| 后端框架 | Python FastAPI |
| Agent 框架 | LangChain + LangGraph |
| 模型 | Qwen 3.5 Flash / GPT-4o / Claude |
| 向量库 | Qdrant Cloud |
| 缓存 | Redis + In-Memory |
| 安全 | API Key Auth + JWT RBAC + Fernet Encryption |
| 实时通信 | SSE + WebSocket |

---

**文档版本**: 2026-06-23  
**适用版本**: Aureon v1.0  
**最后更新**: 2026-06-23
