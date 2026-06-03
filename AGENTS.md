# AI 聊天助手 — Agent 开发指令

## 项目概述

**Python FastAPI + React 19 Agent 架构**：
- 后端：FastAPI + LangChain Agent（Tool Calling + 四层记忆）
- 前端：React 19 + TypeScript + Vite + Tailwind CSS 4

## 项目结构

```
Aureon/
├── backend/app/
│   ├── agent/        # LLM 工厂、Agent 工厂、流式执行器
│   ├── tools/        # @tool 装饰器，__init__.py 统一注册 ALL_TOOLS
│   ├── memory/       # L0-L3 四层记忆 + 上下文卸载
│   ├── rag/          # ChromaDB + Zhipu Embedding + MMR
│   │   ├── vector_store.py  # 向量库 + BM25 检索
│   │   ├── qa_chain.py      # RAG pipeline（检索→生成→来源）
│   │   ├── evaluator.py     # Recall + Faithfulness + 延迟
│   │   └── models.py        # Pydantic 请求/响应
│   ├── features/     # Feature Flag（灰度发布）
│   ├── observability/ # Query Trace、统计
│   ├── security/     # PII、SSO、Rate Limiting
│   ├── evaluation/   # 评估指标、基准测试
│   ├── cost/         # 成本追踪、Budget
│   ├── reliability/  # 备份、事件、SLO、熔断器
│   ├── knowledge/    # 文档版本、导出
│   ├── ai_platform/  # LLM Router、置信度、会话记忆
│   ├── integration/  # 企业连接器、IM Bot
│   ├── langgraph/    # 工作流引擎 + MCP
│   ├── api/          # 模型 + Analytics
│   ├── config.py     # pydantic_settings
│   └── main.py       # FastAPI 入口
├── backend/tests/     # 390 tests
├── src/               # React 前端
│   ├── components/ hooks/ pages/ services/ i18n/ types/
│   └── (49 tests)
├── crew/              # CrewAI 文章生成
└── docker-compose.yml
```

## 开发规范

### 后端
- 工具：`@tool` + 类型注解 + docstring → `ALL_TOOLS` 注册
- Agent：`create_agent(model, tools, prompt)` → `CompiledStateGraph`
- 输入：`{"messages": [HumanMessage(content=...)]}`
- 流式：`graph.astream_events(..., version="v2")`
- 测试：`tests/` + pytest + pytest-asyncio
- API Key 仅存 `.env`

### 前端
- TypeScript + Tailwind CSS
- SSE 事件：session/text/tool_start/tool_end/done/error
- API Key 从后端读取

### 代码质量
- 类型注解完整：`def foo(x: int) -> str:`
- 异步优先：`async def` + `asyncio`
- 异常处理：禁裸 `except`，至少 `logger.exception()`
- 路径安全：`.resolve()` + 前缀检查
- 日志：`logging.getLogger(__name__)`，禁 `print`
- SSE 输出：`json.dumps(..., ensure_ascii=False)`

## 记忆系统

| 层 | 存储 | 职责 |
|---|------|------|
| L0 | SQLite conversations | 原始对话 |
| L1 | SQLite atoms | 原子事实三元组 |
| L2 | offloads/scenarios/*.md | 场景总结 |
| L3 | offloads/persona.md | 用户画像 (≤2KB) |
| 卸载 | offloads/refs/*.md | 长工具输出外存 |

## 构建

```bash
cd backend && uvicorn app.main:app --reload --port 8000
cd Aureon && npm install && npm run dev
cd Aureon/backend && python -m pytest tests/ -v
cd Aureon && npm test
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/chat/stream | Agent SSE |
| POST | /api/chat/enhanced/stream | Chat + RAG |
| POST | /api/rag/query[/stream] | RAG 查询 |
| POST | /api/rag/upload | 上传并索引 |
| POST | /api/rag/index | 重建索引 |
| POST | /api/rag/evaluate | RAG 评估 |
| POST | /api/rag/experiment | Prompt 实验 |
| GET | /api/rag/{stats,uploads,documents,health,benchmark} | RAG 管理 |
| GET | /api/rag/analytics/{usage,latency,tokens,cache} | 分析 |
| POST | /api/langgraph/run | LangGraph |
| POST | /api/crew/generate[/stream] | CrewAI |
| GET | /api/health | 健康检查 |

语言规则：所有回复必须使用中文

## CI/CD 部署流程

**触发条件**：推送代码到 main 分支

**流程**：
1. **推送** → GitHub Actions 触发 CI/CD
2. **CI 通过** → 自动部署到 Railway
3. **部署完成** → 生产环境生效

**关键点**：
- 只推送 main 分支才会触发部署
- 必须等 CI 通过后才继续下一步
- 部署后需验证生产端点确认生效

**推送前检查**：
`ash
# 前端测试
npm test -- --run

# 后端测试
cd backend && python -m pytest tests/ -v
`