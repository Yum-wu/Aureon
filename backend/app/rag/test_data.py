"""RAG Evaluation Test Dataset — Q&A pairs annotated from articles.

51+ QA pairs covering all 18 articles in the knowledge base.
Each article has 2-3 questions testing different aspects:
- Factual recall (specific numbers, names, lists)
- Conceptual understanding (how/why questions)
- Applied knowledge (configuration, solutions)
"""

TEST_QA_PAIRS = [
    # ── Hermes Agent (7 pairs) ──
    {"id": "hermes-001", "question": "Hermes Agent 的分层记忆系统有几层？每层叫什么？", "answer": "4 层：L0 Conversation、L1 Atoms、L2 Scenarios、L3 Persona", "source_article": "hermes-agent-practical-guide"},
    {"id": "hermes-002", "question": "集成四层记忆后，Token 消耗和任务成功率变化如何？", "answer": "Token 消耗降低 61%，任务成功率提升 51%", "source_article": "hermes-agent-practical-guide"},
    {"id": "hermes-003", "question": "Hermes Agent 的核心优势是什么？", "answer": "模块化设计、分层可扩展性，约 900 个测试文件和 17000+ 测试用例", "source_article": "hermes-agent-practical-guide"},
    {"id": "hermes-004", "question": "文中提到了哪三个核心技能？", "answer": "Litprog Skill、Super-Hermes、Hermes Dojo", "source_article": "hermes-agent-practical-guide"},
    {"id": "hermes-005", "question": "文中提到的三个挑战是什么？解决方案分别是什么？", "answer": "1. 多层记忆数据同步冲突；2. 技能之间工具函数冲突；3. 长上下文性能下降", "source_article": "hermes-agent-practical-guide"},
    {"id": "hermes-006", "question": "上下文完整性提升的百分比是多少？", "answer": "89%", "source_article": "hermes-agent-practical-guide"},
    {"id": "hermes-007", "question": "短期记忆、中层存储和长期持久化分别负责什么？", "answer": "短期记忆保留最近对话，中层存储任务状态，长期持久化用户偏好", "source_article": "hermes-agent-practical-guide"},
    # ── SPA GitHub Pages (8 pairs) ──
    {"id": "spa-001", "question": "把 React SPA 部署到 GitHub Pages 经历了哪三阶段崩溃？", "answer": "404 → 白屏 → 路由 404", "source_article": "spa-github-pages"},
    {"id": "spa-002", "question": "GitHub Pages 部署 SPA 列出了多少个部署问题？", "answer": "7 个部署问题", "source_article": "spa-github-pages"},
    {"id": "spa-003", "question": "SPA 路由回退的解决方案是什么？", "answer": "复制 index.html 为 404.html", "source_article": "spa-github-pages"},
    {"id": "spa-004", "question": "Vite 配置中需要设置什么参数？", "answer": "设置 base 为部署子路径", "source_article": "spa-github-pages"},
    {"id": "spa-005", "question": "React Router 中需要设置什么参数？", "answer": "设置 BrowserRouter 的 basename", "source_article": "spa-github-pages"},
    {"id": "spa-006", "question": "base 和 basename 各自控制什么？", "answer": "base 控制静态资源路径，basename 控制前端路由路径", "source_article": "spa-github-pages"},
    {"id": "spa-007", "question": "SPA 部署到 GitHub Pages 的自检清单包含哪些检查项？", "answer": "Network 面板、Console 面板、Elements 面板、路由测试、CI 日志", "source_article": "spa-github-pages"},
    {"id": "spa-008", "question": "构建阶段出现的两个问题是什么？", "answer": "构建产物被 gitignore 和 Node.js 版本太低", "source_article": "spa-github-pages"},
    # ── AI Agent Memory System (3 pairs) ──
    {"id": "mem-001", "question": "AI Agent 多层记忆系统有几层？", "answer": "四层：L0 对话记录、L1 原子事实、L2 场景聚合、L3 用户画像", "source_article": "agent-memory-system"},
    {"id": "mem-002", "question": "L1 原子事实层的作用是什么？", "answer": "从对话中提取结构化的事实信息", "source_article": "agent-memory-system"},
    {"id": "mem-003", "question": "L2 场景聚合层如何工作？", "answer": "将多个原子事实聚合为场景块，保留上下文关联", "source_article": "agent-memory-system"},
    # ── RAG System Guide (3 pairs) ──
    {"id": "rag-001", "question": "RAG 系统的全链路包括哪些步骤？", "answer": "文档加载、分块、向量嵌入、检索、生成", "source_article": "rag-system-guide"},
    {"id": "rag-002", "question": "RAG 中文档分块的推荐大小是多少？", "answer": "500 字左右，overlap 50 字", "source_article": "rag-system-guide"},
    {"id": "rag-003", "question": "RAG 检索优化有哪些方法？", "answer": "混合检索（BM25 + 向量）、RRF 融合、重排序", "source_article": "rag-system-guide"},
    # ── Railway Deployment (3 pairs) ──
    {"id": "rail-001", "question": "AI Chatbot 部署到 Railway 用了什么架构？", "answer": "Docker 多阶段构建，前端 + 后端 + nginx", "source_article": "chatbot-railway-deployment"},
    {"id": "rail-002", "question": "Railway 部署中 Docker 多阶段构建的作用是什么？", "answer": "分离前端构建和后端运行，减小镜像体积", "source_article": "chatbot-railway-deployment"},
    {"id": "rail-003", "question": "Railway 健康检查配置了什么路径？", "answer": "/api/health", "source_article": "chatbot-railway-deployment"},
    # ── DeepSeek Cache Optimization (3 pairs) ──
    {"id": "ds-001", "question": "DeepSeek 缓存率从多少提升到多少？", "answer": "从 56% 提升到 76%", "source_article": "deepseek-cache-optimization"},
    {"id": "ds-002", "question": "DeepSeek 的 KV 缓存机制是什么？", "answer": "前缀相同的请求可以复用 KV 缓存，减少重复计算", "source_article": "deepseek-cache-optimization"},
    {"id": "ds-003", "question": "提升缓存率的关键策略是什么？", "answer": "保持 system prompt 前缀一致，避免频繁变更", "source_article": "deepseek-cache-optimization"},
    # ── React Performance Tips (3 pairs) ──
    {"id": "react-001", "question": "React.memo 的作用是什么？", "answer": "避免不必要的重渲染，当 props 不变时跳过渲染", "source_article": "react-performance-tips"},
    {"id": "react-002", "question": "useMemo 缓存什么？", "answer": "缓存计算结果，避免每次渲染都重新计算", "source_article": "react-performance-tips"},
    {"id": "react-003", "question": "useCallback 的使用场景是什么？", "answer": "缓存函数引用，避免子组件因父组件渲染而重渲染", "source_article": "react-performance-tips"},
    # ── LangGraph Workflow (3 pairs) ──
    {"id": "lg-001", "question": "LangGraph 的核心概念是什么？", "answer": "StateGraph 状态图，通过节点和边编排工作流", "source_article": "langgraph-workflow"},
    {"id": "lg-002", "question": "LangGraph 中条件边的作用是什么？", "answer": "根据状态值动态路由到不同节点", "source_article": "langgraph-workflow"},
    {"id": "lg-003", "question": "LangGraph 状态定义包含哪些字段？", "answer": "messages、current_step、context 等", "source_article": "langgraph-workflow"},
    # ── LangChain Agent Intro (3 pairs) ──
    {"id": "lc-001", "question": "LangChain Agent 的核心概念是什么？", "answer": "LLM + Tools + Memory 的组合，自主决策执行", "source_article": "langchain-agent-intro"},
    {"id": "lc-002", "question": "Agent 的执行流程是怎样的？", "answer": "思考 → 选择工具 → 执行 → 观察结果 → 再思考", "source_article": "langchain-agent-intro"},
    {"id": "lc-003", "question": "LangChain 中工具注册的作用是什么？", "answer": "让 Agent 知道有哪些工具可用及其参数格式", "source_article": "langchain-agent-intro"},
    # ── Zustand Todo App (3 pairs) ──
    {"id": "zust-001", "question": "为什么选择 Zustand 而不是 Redux？", "answer": "极简 API、无需 Provider、性能好", "source_article": "zustand-todo-app"},
    {"id": "zust-002", "question": "Zustand 的核心 API 有几个？", "answer": "主要是 create 函数，一个 store 即可", "source_article": "zustand-todo-app"},
    {"id": "zust-003", "question": "Zustand 如何处理状态更新？", "answer": "直接调用 setter，自动触发重渲染", "source_article": "zustand-todo-app"},
    # ── Blog Migration (3 pairs) ──
    {"id": "blog-001", "question": "博客搬家遇到的主要问题是什么？", "answer": "Git 报错、文件被覆盖、Vercel 部署失败", "source_article": "blog-migration-troubleshooting"},
    {"id": "blog-002", "question": "被覆盖的文件如何恢复？", "answer": "通过 git reflog 找到被删除的提交，恢复文件", "source_article": "blog-migration-troubleshooting"},
    {"id": "blog-003", "question": "Vercel 部署失败的排查步骤是什么？", "answer": "检查构建日志、确认环境变量、验证输出目录", "source_article": "blog-migration-troubleshooting"},
    # ── Eleven Projects (2 pairs) ──
    {"id": "11p-001", "question": "两个月做了多少个项目？", "answer": "11 个项目", "source_article": "eleven-projects-two-months"},
    {"id": "11p-002", "question": "做减法比做加法难在哪里？", "answer": "需要判断力和取舍能力，砍掉已实现的功能比添加更痛苦", "source_article": "eleven-projects-two-months"},
    # ── Git Workflow (2 pairs) ──
    {"id": "git-001", "question": "文章推荐的分支策略是什么？", "answer": "主干开发 (Trunk-Based Development)", "source_article": "git-workflow-best-practices"},
    {"id": "git-002", "question": "功能分支的流程是怎样的？", "answer": "从 main 创建分支 → 开发 → 测试 → 合并回 main", "source_article": "git-workflow-best-practices"},
    # ── Weather App API (2 pairs) ──
    {"id": "weather-001", "question": "天气应用的三层 API 调用设计是什么？", "answer": "定位 API → 天气 API → 空气质量 API", "source_article": "weather-app-api-integration"},
    {"id": "weather-002", "question": "天气应用为什么采用定位→天气→空气质量三层 API 设计？", "answer": "每个 API 职责单一，需要前一个 API 的结果作为后一个的输入", "source_article": "weather-app-api-integration"},
    # ── WeChat Mini Program (2 pairs) ──
    {"id": "wx-001", "question": "微信小程序开发遇到的第一个坑是什么？", "answer": "基础库 3.15.2 的 timeout 问题", "source_article": "wechat-miniprogram-ai-agent"},
    {"id": "wx-002", "question": "WXML 中 wx:key 的正确写法是什么？", "answer": "使用字符串而非 *this", "source_article": "wechat-miniprogram-ai-agent"},
    # ── Markdown Notes App (2 pairs) ──
    {"id": "md-001", "question": "Markdown 笔记应用的三栏布局是什么？", "answer": "文件列表、编辑器、预览", "source_article": "markdown-notes-app"},
    {"id": "md-002", "question": "防抖保存机制的作用是什么？", "answer": "避免每次输入都触发保存，减少 API 调用", "source_article": "markdown-notes-app"},
    # ── AI Writing Assistant (2 pairs) ──
    {"id": "aw-001", "question": "AI 写作助手的流式输出如何实现？", "answer": "使用 SSE (Server-Sent Events) 逐字输出", "source_article": "ai-writing-assistant"},
    {"id": "aw-002", "question": "AI 写作助手支持哪些写作模式？", "answer": "多种写作模式，支持文本优化和历史记录", "source_article": "ai-writing-assistant"},
    # ── LangChain Framework Guide (3 pairs) ──
    {"id": "lcf-001", "question": "LangChain v0.2+ 推荐的链式编排语法是什么？", "answer": "LCEL（LangChain Expression Language），使用管道操作符连接各组件", "source_article": "langchain-framework-guide"},
    {"id": "lcf-002", "question": "create_tool_calling_agent 和 create_react_agent 的主要区别是什么？", "answer": "前者依赖模型原生 function calling，后者使用 ReAct prompt 模式", "source_article": "langchain-framework-guide"},
    {"id": "lcf-003", "question": "LangGraph 相比 LangChain 的核心优势是什么？", "answer": "有状态 Agent 编排，基于有向图的状态机，支持循环和条件分支", "source_article": "langchain-framework-guide"},
    # ── LlamaIndex RAG Guide (3 pairs) ──
    {"id": "li-001", "question": "LlamaIndex 的 RAG Pipeline 分为哪三个核心阶段？", "answer": "Loading、Indexing、Querying", "source_article": "llamaindex-rag-guide"},
    {"id": "li-002", "question": "LlamaIndex Response Synthesizer 的 compact 模式是什么？", "answer": "将多个文档压缩后一次性送入 LLM，性价比最高", "source_article": "llamaindex-rag-guide"},
    {"id": "li-003", "question": "QueryFusionRetriever 的默认 BM25 和向量权重各是多少？", "answer": "BM25 0.4，向量 0.6", "source_article": "llamaindex-rag-guide"},
    # ── RAG Concepts Deep Dive (3 pairs) ──
    {"id": "ragc-001", "question": "RAG 和 Fine-tuning 各自最适合什么场景？", "answer": "RAG 适合知识密集型问答，Fine-tuning 适合调整输出风格", "source_article": "rag-concepts-deep-dive"},
    {"id": "ragc-002", "question": "RRF 的公式是什么，k 通常取多少？", "answer": "score = Σ 1/(k + rank_i)，k 通常取 60", "source_article": "rag-concepts-deep-dive"},
    {"id": "ragc-003", "question": "Parent-Child 切分策略的核心思路是什么？", "answer": "小块检索精确匹配，大块作为上下文返回 LLM", "source_article": "rag-concepts-deep-dive"},
    # ── Vector Database Guide (3 pairs) ──
    {"id": "vdb-001", "question": "HNSW 索引算法的核心结构是什么？", "answer": "多层图结构，底层所有向量，上层稀疏高速公路", "source_article": "vector-database-guide"},
    {"id": "vdb-002", "question": "ChromaDB 默认使用什么索引算法？", "answer": "HNSW，适合 100 万以下向量", "source_article": "vector-database-guide"},
    {"id": "vdb-003", "question": "已有 PostgreSQL 时推荐哪个向量数据库？", "answer": "pgvector，PostgreSQL 扩展", "source_article": "vector-database-guide"},
    # ── Embedding Models Guide (3 pairs) ──
    {"id": "emb-001", "question": "BGE 模型相比 OpenAI Embedding 的优势是什么？", "answer": "本地部署、零费用、中文优秀、支持 instruction", "source_article": "embedding-models-guide"},
    {"id": "emb-002", "question": "768 维 vs 1536 维 Embedding 的性能差异？", "answer": "768 维快一倍，精度损失有限时优先低维", "source_article": "embedding-models-guide"},
    {"id": "emb-003", "question": "BGE 查询编码为什么建议加 instruction 前缀？", "answer": "提升检索精度，区分文档编码和查询编码", "source_article": "embedding-models-guide"},
    # ── AI Agent Architecture (3 pairs) ──
    {"id": "agenta-001", "question": "AI Agent 架构中 ReAct 模式的核心循环是什么？", "answer": "Thought → Action → Observation 循环，交替推理和行动", "source_article": "ai-agent-architecture"},
    {"id": "agenta-002", "question": "Agent 数据库工具为什么默认只读？", "answer": "最小权限原则，防止 Agent 执行写操作", "source_article": "ai-agent-architecture"},
    {"id": "agenta-003", "question": "多 Agent 主从模式中编排者的职责是什么？", "answer": "将任务分配给合适的专家 Worker", "source_article": "ai-agent-architecture"},
    # ── Prompt Engineering Guide (3 pairs) ──
    {"id": "pe-001", "question": "Prompt Engineering 中 Chain-of-Thought 的三种主要变体是什么？", "answer": "Zero-shot CoT、Few-shot CoT、Tree-of-Thought", "source_article": "prompt-engineering-guide"},
    {"id": "pe-002", "question": "Self-Consistency 技术的工作原理是什么？", "answer": "多次独立推理，投票选择最一致的答案", "source_article": "prompt-engineering-guide"},
    {"id": "pe-003", "question": "RAG 场景中 Prompt 设计的关键规则有哪些？", "answer": "只基于参考回答、无信息时说明不知道、标注来源、不编造", "source_article": "prompt-engineering-guide"},
]

# For recall evaluation: expected source articles per query
RETRIEVAL_EXPECTED = {item["question"]: item["source_article"] for item in TEST_QA_PAIRS}
