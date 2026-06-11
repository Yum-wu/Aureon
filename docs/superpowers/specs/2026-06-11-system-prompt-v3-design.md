# Aureon 系统提示词 v3 设计规格

**日期**: 2026-06-11  
**作者**: Yum-wu / Aureon  
**状态**: Draft  

## 1. 背景与动机

### 1.1 v2 文档审计结果

v2 系统提示词 HTML 文档包含 10 个问题的修复矩阵。经对项目实际代码的全面审计（2026-06-11），发现 **10 个问题中 6 个已修复**：

| v2 ID | 问题 | 实际状态 |
|-------|------|---------|
| P0-1 | Redis volume 缺失 | **已修复** — `redis_data:/data` + 顶层 `redis_data:` 声明 |
| P0-2 | Railway OOM | **已缓解** — Dockerfile 配置 `RERANK_BACKEND=api`，`GPU_ENABLED=false` |
| P0-3 | ES 无 healthcheck | **已修复** — 完整 healthcheck + `depends_on: service_healthy` |
| P1-4 | CI 跳过测试 | **部分准确** — CI 运行但 `--ignore` 了 2 个测试文件 |
| P1-5 | WebSocket 测试删除 | **不准确** — test_websocket_chat/load/manager/integration 均存在 |
| P1-6 | Docker CI 缺失 | **已修复** — docker-build.yml 完整（validate + build） |
| P2-7 | ChromaDB 冗余 | **部分修复** — requirements.txt 已注释，但 vector_store.py 仍有 ~100 行残留 |
| P2-8 | crewai 冲突 | **准确** — 仍被注释 |
| P2-9 | SECURITY.md 缺失 | **已修复** — 78 行完整文档 |
| P3-10 | nginx 回滚 | **不准确** — nginx 完全集成 |

**结论**: v2 问题矩阵仅 1.5/10 准确，需完全重写。

### 1.2 审计方法论

通过 3 个并行分析维度执行全面审计：
1. **测试覆盖与代码质量**: 79 个测试文件分析、CI 忽略原因、ChromaDB 残留、print/except/TODO 扫描、配置一致性
2. **安全与性能**: 认证中间件、多租户隔离、SSO 权限、嵌入/重排性能、资源配置
3. **前端与 CI/CD**: 依赖版本、TypeScript 严格性、console.log 扫描、CI 完整性、可观测性

## 2. 新问题矩阵（26 项）

### P0 — 关键（4 项）

**#1 EMBEDDING_DIMENSION 环境变量静默失效**
- **根因**: `.env.example` 使用 `EMBEDDING_DIMENSION=768`，但 `config.py` 字段是 `embedding_dim: int = 768`。Pydantic-settings 按字段名映射环境变量，`EMBEDDING_DIMENSION` 不会映射到 `embedding_dim`
- **验证**: config.py L30 + .env.example 对比
- **影响**: 嵌入维度始终使用默认值，配置不可覆盖

**#2 vector_backend 默认 "chroma" 但 chromadb 已移除**
- **根因**: config.py L55 `vector_backend: str = "chroma"`，但 chromadb 已从 requirements.txt 移除
- **验证**: config.py L55 + requirements.txt L24（已注释）
- **影响**: 新开发者 clone 后不设 `VECTOR_BACKEND=qdrant` 则启动崩溃

**#3 多租户隔离可被 X-Tenant-ID header 绕过**
- **根因**: 安全中间件接受 `X-Tenant-ID` header 但未验证来源合法性
- **验证**: `backend/app/multi_tenant/` 代码审查
- **影响**: 攻击者可伪造 header 读取其他租户数据

**#4 SSO 管理端点无 ADMIN 权限检查**
- **根因**: `/api/security/sso/providers` 注释声明"需要 ADMIN 角色"但代码无 `Depends(require_role(...))`
- **验证**: `backend/app/security/` 代码审查
- **影响**: 未授权用户可管理 SSO 配置

### P1 — 高（11 项）

**#5 ChromaDB 残留代码 ~100 行**
- vector_store.py L147-226: 完整 ChromaDB singleton（`_chroma_client`, `_get_chroma()`, `_reset_chroma()`）
- vector_store.py L3: docstring 仍写 "Uses ChromaDB"
- config.py L55: 默认值仍为 "chroma"

**#6 CI 忽略 test_rag_quality.py**
- 原因: 依赖 DeepEval + 真实 LLM API Key，CI 无 key 必跳过
- L91: `pytest.warns` 用法有 bug

**#7 CI 忽略 test_rag_router_extended.py**
- 原因: 需完整 FastAPI app 初始化，CI 环境不兼容

**#8 TypeScript strict mode 未启用**
- tsconfig.app.json 缺少 `"strict": true`，`strictNullChecks`/`noImplicitAny` 未启用

**#9 CI 无 npm audit**
- 高危漏洞依赖可无阻断合并

**#10 CI 无测试覆盖率门槛**
- vitest.config.ts 未配置 `coverage.thresholds`

**#11 缺少 /health/ready 和 /health/live**
- 仅有 `/api/health`，无 readiness/liveness 分离

**#12 console.log/print() 在生产代码中**
- 后端: qa_chain.py L1162/L1357, main.py L32, reranking_ab_test.py L398
- 前端: websocket.ts L72/L89/L216, useWebSocket.ts L115

**#13 前端缺少 404 路由**
- App.tsx 无通配符路由，未知 URL 显示空白页

**#14 SKIP_LOCAL_EMBED 绕过 Settings 系统**
- 13 处 `os.getenv("SKIP_LOCAL_EMBED")` 分散在 vector_store.py/ensemble_reranker.py/qa_chain.py/semantic_cache.py

**#15 LLM 模型版本号不一致**
- config.py: `qwen3.6-flash`，.env.example: `qwen3.5-flash`

### P2 — 中（7 项）

**#16 crewai 版本冲突** — 仍被注释，与 langchain>=1.0 不兼容  
**#17 api.ts 重复代码** — streamChat/streamEnhancedChat 几乎相同  
**#18 CI 无后端 lint** — 无 ruff/flake8  
**#19 WebSocket 类型安全** — 15 处 `eslint-disable no-explicit-any`  
**#20 ErrorBoundary UI 硬编码中文** — 未使用 i18n  
**#21 RAG Quality CI fork PR** — 缺少 secrets 不可用时的跳过逻辑  
**#22 WEBSOCKET_MAX_CONNECTIONS 不一致** — config.py: 300 vs .env.example: 200  

### P3 — 低（4 项）

**#23 @tailwindcss/typography alpha** — 预发布版本  
**#24 TODO 注释未跟踪** — 5 处（qa_chain.py, rag_stats.py, analytics.py）  
**#25 Docker 镜像无安全扫描** — docker-build.yml 无 Trivy/Snyk  
**#26 前端无错误监控** — ErrorBoundary 注释 "Future: send to Sentry"  

## 3. Phase 任务设计

### Phase 0: 安全修复（P0 #3 #4）
最高优先级，安全修复必须在所有其他修复之前完成。

### Phase 1: 配置与基础设施（P0 #1 #2 + P1 #5 #14 #15）
修复配置静默失效、默认值、ChromaDB 残留、Settings 统一。

### Phase 2: CI/CD 质量门禁（P1 #6-11 #18）
恢复 CI 测试覆盖、添加 audit/lint/coverage、健康端点。

### Phase 3: 代码质量与技术债务（P1 #12-13 + P2 + P3）
生产代码清理、前端修复、依赖升级、监控集成。

## 4. 系统提示词设计变更

| 组件 | v2 | v3 |
|------|-----|-----|
| `<role>` | DevOps + Python 后端 | DevOps + 安全 + 全栈 |
| `<rules>` do | 6 条 | 9 条（+安全优先、配置同步、测试覆盖） |
| `<rules>` don't | 6 条 | 7 条（+不要假设环境变量名） |
| `<data>` | 旧 10 问题 + OOM 链 | 新 26 问题 + 安全漏洞 |
| `<output>` | 基础 JSON | +security_impact 字段 |
| `<key_reminder>` | 2 条 | 3 条（+安全优先） |

## 5. 反模式更新

新增 2 个反模式：
- **配置漂移**: `.env.example` 与 `config.py` 字段名不同步
- **权限注释幻觉**: 注释声明权限检查但代码未实施

## 6. 输出格式

保持 HTML 报告格式，与 v2 相同视觉风格。新文件: `docs/superpowers/aureon-fix-prompt-v3.html`
