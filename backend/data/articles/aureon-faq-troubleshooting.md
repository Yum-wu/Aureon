---
title: "Aureon 故障排除 - 常见问题"
slug: "aureon-faq-troubleshooting"
language: "zh"
source: "aureon-faq"
---

# Aureon 故障排除 - 常见问题

## 搜索没有结果怎么办？

**可能原因及解决方案**：

1. **文档未索引**
   - 检查：访问 `/api/rag/health` 查看索引状态
   - 解决：上传文档后等待索引完成，或手动触发重建索引

2. **查询过于具体**
   - 检查：尝试更通用的查询
   - 解决：使用同义词或更宽泛的描述

3. **语言不匹配**
   - 检查：文档语言与查询语言是否一致
   - 解决：上传对应语言的文档

4. **向量数据库连接失败**
   - 检查：访问 `/health/ready` 查看 Qdrant 状态
   - 解决：检查 Qdrant 配置和网络连接

## LLM 响应很慢怎么办？

**排查步骤**：

1. **检查 API Key**
   - 确认 API Key 有效且有足够配额
   - 查看 `/metrics` 端点的错误率

2. **检查网络延迟**
   - 确认服务器到 LLM API 的网络连通性
   - 考虑使用就近的 API 端点

3. **检查并发限制**
   - 默认并发：Qwen 30、Embedding 50、RAG 40
   - 高并发时可能排队等待

4. **启用缓存**
   - 语义缓存可显著降低重复查询延迟
   - 检查缓存命中率

## WebSocket 连接失败怎么办？

**可能原因**：

1. **反向代理配置错误**
   - nginx 需要配置 WebSocket 支持：
   ```nginx
   location /ws/ {
       proxy_pass http://backend;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

2. **连接数超限**
   - 默认最大 300 个 WebSocket 连接
   - 检查是否有连接泄漏

3. **心跳超时**
   - 默认 30 秒心跳间隔
   - 客户端需要定期发送 pong

## 文档上传失败怎么办？

**常见错误**：

1. **文件格式不支持**
   - 仅支持：.md、.txt、.pdf、.docx、.xlsx
   - 检查文件扩展名是否正确

2. **文件过大**
   - 限制：10MB
   - 解决：拆分大文件

3. **权限不足**
   - 需要 Editor 或更高角色
   - 检查用户角色配置

4. **路径安全检查失败**
   - 文件名不能包含 `..` 或以 `.`
   - 仅允许字母、数字、中文、连字符、下划线、点、空格

## 仪表盘数据不更新怎么办？

**排查步骤**：

1. **检查 WebSocket 连接**
   - 仪表盘通过 WebSocket 接收实时数据
   - 检查浏览器控制台是否有连接错误

2. **检查 Redis 连接**
   - 仪表盘数据存储在 Redis
   - 访问 `/health/ready` 查看 Redis 状态

3. **刷新页面**
   - 有时浏览器缓存导致数据不更新
   - 强制刷新（Ctrl+Shift+R）

## 认证失败怎么办？

**常见问题**：

1. **API Key 无效**
   - 检查环境变量 `API_AUTH_KEY` 是否正确设置
   - 确认请求头格式：`X-API-Key: your-key`

2. **JWT Token 过期**
   - Token 默认有效期 24 小时
   - 重新登录获取新 Token

3. **角色权限不足**
   - 检查用户角色是否满足接口要求
   - Viewer 角色无法上传文档

4. **生产环境阻止开发模式**
   - Railway 部署时，开发模式登录被阻止
   - 必须使用正式的 SSO 认证

## 如何查看系统日志？

### Railway 部署
```bash
railway logs --latest
railway logs --follow
```

### Docker 部署
```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

### 本地开发
后端日志直接输出到终端，使用 structlog 结构化格式。

## 如何监控系统性能？

1. **Prometheus 指标**
   - 访问 `/metrics` 端点
   - 集成 Grafana 可视化

2. **LangFuse 链路追踪**
   - 配置 `LANGFUSE_ENABLED=true`
   - 查看每步延迟、Token 使用、检索质量

3. **内置仪表盘**
   - 访问 `/dashboard` 页面
   - 实时查看 Golden Signals

## 数据备份如何操作？

1. **Qdrant 数据**
   - 使用 Qdrant 自带的快照功能
   - 或导出集合数据

2. **Redis 数据**
   - Redis RDB 快照
   - 或 AOF 持久化

3. **SQLite 数据**
   - 直接复制数据库文件
   - 包含对话记录和用户数据

## 如何升级到新版本？

1. **备份数据**
2. **拉取最新代码**
3. **运行数据库迁移**（如有）
4. **重启服务**
5. **验证功能正常**

**注意**：查看 CHANGELOG 了解是否有破坏性变更。
