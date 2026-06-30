# AGENTS.md

> **主指令文件**: [CLAUDE.md](CLAUDE.md) — 项目约定、结构、红线、环境变量、路由清单。
> **领域上下文**: [CONTEXT.md](CONTEXT.md) — 术语表、系统边界、RAG 迭代历史、MVP 边界。

## 快速索引

| 你想知道 | 去哪 |
|---------|------|
| 项目结构 | CLAUDE.md §项目结构 |
| 开发规范 | CLAUDE.md §开发规范 |
| API 端点 | CLAUDE.md §API 端点 |
| CI/CD | CLAUDE.md §CI/CD 部署流程 |
| 术语定义 | CONTEXT.md §术语表 |
| RAG 检索策略 | CONTEXT.md §RAG 优化经验教训 |
| 系统边界/约束 | CONTEXT.md §系统边界 |
| 已删除模块（禁止复活） | CLAUDE.md §前置要求 |

## AGENTS.md 专属（CLAUDE.md 未覆盖）

- **RBAC 端点权限**：`GET /api/rag/uploads`(VIEWER), `DELETE /api/rag/upload/{fn}`(EDITOR), `POST /api/rag/cache/clear`(ADMIN)
- **Dev 模式绕过**：Railway/Render/Fly.io/Heroku/Vercel/Netlify 自动识别为生产平台，启动时硬阻断 `AUTH__ENVIRONMENT=dev`
- **用户引导**：搜索优先、价值驱动。`src/components/onboarding/` 含步骤配置和引导状态管理。
