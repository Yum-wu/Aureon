# CLAUDE.md

本文件为 Claude Code 在此仓库中工作时的指南。

## 仓库概览

本仓库是 **Aureon** — 企业级 AI 知识库平台的单一项目仓库。

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

## 构建与开发命令

### 前端
```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 运行测试
npm test

# 代码检查
npm run lint
```

### 后端
```bash
# 进入后端目录
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（复制 .env.example 填入 API Key）
cp .env.example .env

# 启动开发服务器
uvicorn app.main:app --reload --port 8000

# 运行测试
pytest
```

### Docker（推荐）
```bash
# 一键启动前后端
docker-compose up --build

# 后台运行
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## API 端点

- `POST /api/chat/enhanced/stream` — Chat + RAG 自动集成，LangGraph 流式工作流
- `POST /api/chat/stream` — 基础 Chat Agent
- `POST /api/rag/query` — RAG 查询
- `POST /api/rag/query/stream` — 流式 RAG 查询（SSE）
- `GET /api/rag/analytics/usage` — 使用量分析
- `GET /api/rag/analytics/latency` — 延迟分析
- `GET /api/rag/analytics/tokens` — Token 使用分析
- `GET /api/rag/analytics/cache` — 缓存性能分析
- `POST /api/rag/index` — 重新索引文章

## 项目结构

```
Aureon/
├── src/                    # 前端源码
│   ├── components/         # React 组件
│   ├── hooks/              # 自定义 Hooks
│   ├── services/           # API 服务
│   └── utils/              # 工具函数
├── backend/                # 后端源码
│   ├── app/                # FastAPI 应用
│   ├── tests/              # 测试文件
│   └── requirements.txt    # Python 依赖
├── crew/                   # CrewAI 文章生成服务
├── dist/                   # 构建输出
├── docs/                   # 文档
├── screenshots/            # 截图
└── docker-compose.yml      # Docker 配置
```

## 代码规范

- **TypeScript** 用于前端
- **Python** 用于后端
- 所有组件使用 Tailwind CSS 样式
- 状态管理使用 React hooks（无外部状态库）
- 后端遵循 FastAPI 最佳实践

## 环境要求

- Node.js 18+
- npm 9+
- Python 3.10+
- pip 21+

## 插件技能（claude-code-setup v2）

已安装 16 个插件到 `~/.claude/plugins/`，分三类使用：

### 自动触发（Hooks，无需手动调用）
- `security-essentials` — 文件保护、命令校验、变更限速
- `tailwind-expert` — 自动校验 Tailwind 配置/构建前检查
- `testing-toolkit` — 提交时自动触发测试
- `project-management` — 任务状态持久化
- `shadcn-style-expert` — CSS 风格守护

### 手动调用（Slash Commands）
```
前端          /frontend-expert  /component-architecture  /state-management
             /react-optimization  /performance-audit  /css-architecture

Tailwind     /tailwind-expert  /setup-tailwind  /validate-tailwind-config
             /fix-custom-utilities  /check-tailwind-utilities  /fix-styling
             /tailwind-v4-migration

Python       /python-developer

测试         /testing-best-practices

代码质量     /code-quality  /fix-issue  /fix-zh  /review-zh  /explain-zh  /test-zh

项目管理     /project-management  /create-tasks  /update-tasks  /from-prd
             /generate-docs  /security-best-practices
```

### Agent（对话中自动识别场景调用）
- `Frontend Expert` / `Tailwind CSS Expert`
- `Testing Toolkit` / `Project Management`

## 语言与沟通

- 所有对话和思考应使用中文（或中英双语）。
- 代码注释使用英文。

## 部署

- **GitHub Pages**：推送到 `main` 分支后 GitHub Actions 自动构建并部署前端
- **Railway**：支持一键部署后端（见 `railway.json`）
- **Docker**：支持容器化部署（见 `Dockerfile` 和 `docker-compose.yml`）

## 许可证

MIT License
