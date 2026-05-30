# CLAUDE.md

Aureon 项目开发指南。

## 项目信息

| 属性 | 值 |
|------|-----|
| 项目名 | Aureon |
| 类型 | 全栈 AI 应用 |
| 前端 | React 19 + Vite + TypeScript + Tailwind CSS |
| 后端 | Python FastAPI + LangChain + LangGraph |
| 端口 | 前端 5173 / 后端 8000 |
| 数据库 | SQLite（记忆）+ Chroma（向量库）|
| AI API | 智谱 AI / OpenAI |

## 构建命令

### 前端
```bash
npm install && npm run dev
npm run build
npm test
npm run lint
```

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
pytest
```

### Docker
```bash
docker-compose up --build
docker-compose up -d
docker-compose logs -f
docker-compose down
```

## API 端点

- `POST /api/chat/enhanced/stream` — Chat + RAG，LangGraph 流式
- `POST /api/chat/stream` — Chat Agent
- `POST /api/rag/query` / `query/stream` — RAG 查询（同步/流式）
- `GET /api/rag/analytics/{usage|latency|tokens|cache}` — 分析
- `POST /api/rag/index` — 重建索引

## 项目结构

```
Aureon/
├── src/components/  hooks/  services/  utils/
├── backend/app/{agent,tools,memory,rag,features,observability,security,evaluation,cost,reliability,knowledge,ai_platform,integration,langgraph,api}/
├── backend/tests/   (390 tests)
├── crew/            CrewAI 文章生成
├── dist/            构建输出
├── docs/            文档
└── docker-compose.yml
```

## 代码规范

- 前端 TypeScript + Tailwind CSS + React hooks
- 后端 Python + FastAPI + async
- 代码注释英文

## 环境要求

Node.js 18+ / npm 9+ / Python 3.10+ / pip 21+

## 插件（16 个）

自动：`security-essentials` `tailwind-expert` `testing-toolkit` `project-management` `shadcn-style-expert`

手动：
```
前端     /frontend-expert /component-architecture /state-management /react-optimization /performance-audit
Tailwind /tailwind-expert /setup-tailwind /validate-tailwind-config /fix-custom-utilities
Python   /python-developer
测试     /testing-best-practices
质量     /code-quality /fix-issue /fix-zh /review-zh
管理     /project-management /create-tasks /from-prd /generate-docs
```

Agent 自动识别：`Frontend Expert` `Tailwind CSS Expert` `Testing Toolkit` `Project Management`

## 部署

- GitHub Pages：`main` 分支 GitHub Actions 自动构建部署前端
- Railway：一键部署后端（`railway.json`）
- Docker：容器化部署（`Dockerfile` + `docker-compose.yml`）

MIT License
