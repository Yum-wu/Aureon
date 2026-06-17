"""RAG Evaluation Test Dataset — Comprehensive Q&A pairs for rigorous benchmarking.

Design principles (aligned with RAGAS/DeepEval best practices):
- Questions require multi-sentence comprehension, not single-keyword lookup
- Paraphrased vocabulary (different from article text) to prevent keyword cheating
- Mixed difficulty levels: easy (factual), medium (reasoning), hard (synthesis)
- Negative/unanswerable queries to test hallucination resistance
- Cross-article queries requiring multi-document reasoning
- No duplicate questions across files (single source of truth)

Categories:
- factual: direct information retrieval from one article
- reasoning: requires understanding cause/effect or process
- synthesis: combines information from multiple parts of an article
- negative: answer NOT in knowledge base — system should decline to answer
- cross_article: requires information from 2+ articles
"""

TEST_QA_PAIRS = [
    # ═══════════════════════════════════════════════════════════
    # Hermes Agent Practical Guide (7 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "hermes-001",
        "question": "Hermes Agent 的分层记忆系统有几层？每层叫什么？",
        "answer": "4 层：L0 Conversation、L1 Atoms、L2 Scenarios、L3 Persona",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "hermes-002",
        "question": "集成四层记忆后，Token 消耗和任务成功率变化如何？",
        "answer": "Token 消耗降低 61%，任务成功率提升 51%",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "hermes-003",
        "question": "Hermes Agent 的模块化设计解决了哪些实际工程问题？",
        "answer": "模块化设计解决了技能间工具函数冲突、长上下文性能下降、多层记忆数据同步冲突等问题",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "hermes-004",
        "question": "文中提到的三个核心技能分别面向什么使用场景？",
        "answer": "Litprog Skill 面向文档生成，Super-Hermes 面向通用任务，Hermes Dojo 面向测试评估",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "hermes-005",
        "question": "Hermes Agent 集成记忆系统时，如何解决短期记忆和长期持久化之间的数据一致性问题？",
        "answer": "通过分层架构，短期记忆保留最近对话，中层存储任务状态，长期持久化用户偏好，各层独立管理避免冲突",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "hermes-006",
        "question": "记忆系统引入后对 Agent 的上下文管理产生了什么量化影响？",
        "answer": "上下文完整性提升了 89%，同时 Token 消耗降低了 61%",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "hermes-007",
        "question": "Hermes Agent 在技能执行过程中如何处理工具调用的安全性？",
        "answer": "通过最小权限原则，工具默认只读，写操作需要额外确认，防止 Agent 执行危险操作",
        "source_article": "ai-agent-architecture",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # SPA GitHub Pages (5 pairs — reduced from 8, removed trivial ones)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "spa-001",
        "question": "React SPA 部署到 GitHub Pages 时，路由系统会遇到什么典型问题？如何解决？",
        "answer": "刷新页面会出现 404，因为 GitHub Pages 找不到对应的 HTML 文件。解决方案是复制 index.html 为 404.html，让所有 404 都回退到 SPA 入口",
        "source_article": "spa-github-pages",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "spa-002",
        "question": "Vite 的 base 配置和 React Router 的 basename 分别控制什么？为什么两者都要设置？",
        "answer": "base 控制静态资源（JS/CSS）的路径前缀，basename 控制前端路由的路径前缀。两者都要设置是因为资源加载和路由匹配是独立的系统",
        "source_article": "spa-github-pages",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "spa-003",
        "question": "文章描述的部署自检流程中，Network 面板和 Console 面板分别能发现什么问题？",
        "answer": "Network 面板发现资源加载失败（404/路径错误），Console 面板发现 JS 运行时错误（路由配置、模块导入问题）",
        "source_article": "spa-github-pages",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "spa-004",
        "question": "SPA 部署到 GitHub Pages 时构建阶段常见的两个陷阱是什么？",
        "answer": "构建产物被 .gitignore 排除导致 CI 无法部署，以及 Node.js 版本过低导致构建失败",
        "source_article": "spa-github-pages",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "spa-005",
        "question": "GitHub Pages 部署 SPA 时，CI/CD 流程中哪个环节最容易出错？如何排查？",
        "answer": "构建产物提交环节最容易出错。排查方法是检查 CI 日志中的构建输出、确认输出目录配置正确、验证 .gitignore 没有排除 dist 目录",
        "source_article": "spa-github-pages",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # AI Agent Memory System (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "mem-001",
        "question": "AI Agent 的四层记忆架构中，每一层分别存储什么类型的信息？",
        "answer": "L0 存储原始对话记录，L1 存储从对话中提取的结构化原子事实，L2 存储将多个原子事实聚合后的场景块，L3 存储用户画像和偏好",
        "source_article": "agent-memory-system",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "mem-002",
        "question": "从原始对话到用户画像，信息在四层记忆中是如何逐步抽象的？",
        "answer": "对话记录 → 提取原子事实 → 聚合为场景 → 归纳为用户画像，每层都在上一层基础上做更高阶的抽象",
        "source_article": "agent-memory-system",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "mem-003",
        "question": "L1 原子事实层和 L2 场景聚合层在数据粒度上有什么区别？",
        "answer": "L1 是细粒度的单条事实（如'用户喜欢 Python'），L2 是粗粒度的场景聚合（如'用户在做一个 RAG 项目，使用 Python + LangChain'）",
        "source_article": "agent-memory-system",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ═══════════════════════════════════════════════════════════
    # RAG System Guide (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "rag-001",
        "question": "从原始文档到最终生成回答，RAG 系统经历了哪些处理阶段？每个阶段的输入输出是什么？",
        "answer": "文档加载（原始文件→文本）→ 分块（长文本→小段落）→ 向量嵌入（文本→向量）→ 检索（查询向量→匹配文档）→ 生成（上下文+问题→回答）",
        "source_article": "rag-system-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "rag-002",
        "question": "文档分块时，chunk 大小和 overlap 分别影响什么？如何平衡？",
        "answer": "chunk 大小影响检索粒度（太大丢失精度，太小丢失上下文），overlap 影响相邻块的语义连续性。推荐 500 字 + 50 字 overlap 作为平衡点",
        "source_article": "rag-system-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "rag-003",
        "question": "混合检索为什么比纯向量检索效果好？BM25 和向量搜索各自擅长什么？",
        "answer": "BM25 擅长精确关键词匹配（如专有名词、ID），向量搜索擅长语义理解（如同义词、 paraphrase）。混合检索通过 RRF 融合两者优势",
        "source_article": "rag-system-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ═══════════════════════════════════════════════════════════
    # Chatbot Railway Deployment (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "rail-001",
        "question": "Docker 多阶段构建在 Railway 部署中解决了什么问题？",
        "answer": "将前端构建（Node.js 环境）和后端运行（Python 环境）分离，减小最终镜像体积，同时确保前端构建产物能正确复制到生产镜像中",
        "source_article": "chatbot-railway-deployment",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "rail-002",
        "question": "Railway 的健康检查机制是如何工作的？配置不当会导致什么后果？",
        "answer": "Railway 定期请求配置的健康检查路径，超时未响应则标记容器失败并重启。配置不当（如路径错误或超时太短）会导致正常运行的容器被误判为失败",
        "source_article": "chatbot-railway-deployment",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "rail-003",
        "question": "部署 AI 应用到 Railway 时，BGE 模型加载对启动时间有什么影响？如何优化？",
        "answer": "BGE 模型加载需要 60-90 秒，会导致健康检查超时。优化方案包括：模型预下载到 Docker 镜像、增加健康检查超时时间、将模型加载移到后台线程",
        "source_article": "chatbot-railway-deployment",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # DeepSeek Cache Optimization (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "ds-001",
        "question": "DeepSeek 的 KV 缓存机制是如何工作的？什么条件下可以命中缓存？",
        "answer": "前缀相同的请求可以复用 KV 缓存。当 system prompt 保持一致、输入前缀相同时，后续请求可以跳过 prefill 阶段，直接从缓存位置开始计算",
        "source_article": "deepseek-cache-optimization",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "ds-002",
        "question": "提升 DeepSeek 缓存命中率的关键策略是什么？这些策略的原理是什么？",
        "answer": "保持 system prompt 前缀一致是关键。原理是 KV 缓存按 token 位置匹配，前缀变化会导致缓存失效。固定 system prompt 可以让后续对话复用相同的 KV 计算",
        "source_article": "deepseek-cache-optimization",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "ds-003",
        "question": "DeepSeek 缓存优化对实际使用成本产生了什么影响？",
        "answer": "缓存命中率从 56% 提升到 76%，大幅降低了 token 消耗和 API 调用成本，因为命中缓存的请求不需要重新计算已缓存部分的 KV",
        "source_article": "deepseek-cache-optimization",
        "difficulty": "easy",
        "type": "factual",
    },

    # ═══════════════════════════════════════════════════════════
    # React Performance Tips (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "react-001",
        "question": "React.memo、useMemo 和 useCallback 三者各自的优化目标有什么区别？",
        "answer": "React.memo 避免组件重渲染（props 不变时跳过），useMemo 缓存计算结果避免重复运算，useCallback 缓存函数引用避免子组件因函数重建而重渲染",
        "source_article": "react-performance-tips",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "react-002",
        "question": "什么场景下使用 useMemo 是有意义的？什么场景下是过度优化？",
        "answer": "有意义：复杂计算（排序、过滤大列表）、创建大对象。过度优化：简单计算（加减乘除）、小数据集。优化成本大于重算成本时就是过度优化",
        "source_article": "react-performance-tips",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "react-003",
        "question": "为什么 useCallback 需要和 React.memo 配合使用才有意义？",
        "answer": "useCallback 缓存函数引用，但如果父组件重渲染时子组件没有 React.memo，子组件仍会重渲染。只有子组件被 React.memo 包裹时，useCallback 避免函数重建才有实际效果",
        "source_article": "react-performance-tips",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # LangGraph Workflow (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "lg-001",
        "question": "LangGraph 的状态图由哪些核心元素组成？它们之间如何协作？",
        "answer": "核心元素包括 State（状态定义）、Node（处理节点）、Edge（连接边）、Conditional Edge（条件边）。节点处理状态，边决定流转方向，条件边实现动态路由",
        "source_article": "langgraph-workflow",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lg-002",
        "question": "LangGraph 中条件边和普通边的区别是什么？什么时候需要用条件边？",
        "answer": "普通边是固定路由（A→B），条件边根据状态值动态选择下一个节点（如分类结果决定走哪个处理分支）。需要根据不同输入走不同路径时使用条件边",
        "source_article": "langgraph-workflow",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lg-003",
        "question": "LangGraph 相比普通的链式调用（LangChain LCEL），在什么场景下更有优势？",
        "answer": "需要循环（如 Agent 反复调用工具）、条件分支（如根据中间结果选择不同处理路径）、状态持久化（如中断后恢复执行）时，LangGraph 的状态图比线性链更有优势",
        "source_article": "langgraph-workflow",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # LangChain Agent Intro (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "lc-001",
        "question": "LangChain Agent 的核心执行循环是什么？每一步的作用是什么？",
        "answer": "思考（LLM 分析任务）→ 选择工具（根据需求选工具）→ 执行工具（调用外部 API/函数）→ 观察结果（获取工具返回值）→ 再思考（基于结果决定下一步）",
        "source_article": "langchain-agent-intro",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lc-002",
        "question": "工具注册在 Agent 系统中起什么作用？不注册工具会怎样？",
        "answer": "工具注册告诉 Agent 有哪些工具可用及其参数格式。不注册的话 Agent 不知道可以调用什么，会试图直接回答所有问题，导致幻觉或无法完成需要外部数据的任务",
        "source_article": "langchain-agent-intro",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lc-003",
        "question": "LangChain Agent 和简单的 LLM 调用有什么本质区别？",
        "answer": "简单 LLM 调用是单次问答，Agent 是多轮自主决策循环。Agent 能根据中间结果动态选择工具、规划执行步骤，而 LLM 调用只能基于输入直接生成回答",
        "source_article": "langchain-agent-intro",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # Zustand Todo App (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "zust-001",
        "question": "Zustand 相比 Redux 的核心设计差异是什么？这些差异带来了什么好处？",
        "answer": "Zustand 无需 Provider 包裹、API 极简（一个 create 函数）、性能好（细粒度订阅）。好处是减少样板代码、降低学习成本、提升渲染性能",
        "source_article": "zustand-todo-app",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "zust-002",
        "question": "Zustand 的状态更新机制是如何实现自动重渲染的？",
        "answer": "直接调用 setter 修改状态，Zustand 内部通过 Proxy 或 subscribe 机制检测变化，自动触发订阅了该状态的组件重渲染",
        "source_article": "zustand-todo-app",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "zust-003",
        "question": "文章中 Todo 应用的状态管理包含哪些操作？",
        "answer": "添加待办、切换完成状态、删除待办、筛选显示（全部/已完成/未完成）",
        "source_article": "zustand-todo-app",
        "difficulty": "easy",
        "type": "factual",
    },

    # ═══════════════════════════════════════════════════════════
    # Blog Migration Troubleshooting (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "blog-001",
        "question": "博客搬家过程中文件被覆盖后，如何通过 Git 恢复？",
        "answer": "通过 git reflog 找到被删除的提交记录，然后用 git checkout 或 git reset 恢复特定文件或整个目录",
        "source_article": "blog-migration-troubleshooting",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "blog-002",
        "question": "Vercel 部署失败时，排查的三个关键步骤是什么？",
        "answer": "检查构建日志中的错误信息、确认环境变量是否正确配置、验证输出目录路径是否与 Vercel 设置匹配",
        "source_article": "blog-migration-troubleshooting",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "blog-003",
        "question": "博客搬家时遇到 Git 报错的根本原因通常是什么？",
        "answer": "通常是分支策略不一致（本地 main 和远程 main 分叉）、文件权限冲突、或者远程仓库已有不同历史导致合并冲突",
        "source_article": "blog-migration-troubleshooting",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # Eleven Projects Two Months (3 pairs — strengthened)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "11p-001",
        "question": "在两个月的高强度开发中，作者对'做减法'有什么反思？",
        "answer": "做减法比做加法更需要判断力和取舍能力，砍掉已实现的功能比添加新功能更痛苦，但精简后的产品体验更好",
        "source_article": "eleven-projects-two-months",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "11p-002",
        "question": "这篇文章分享了哪些关于快速迭代和项目管理的经验教训？",
        "answer": "快速迭代需要明确优先级、避免完美主义、接受先上线再优化的策略，同时要注意技术债务的积累",
        "source_article": "eleven-projects-two-months",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "11p-003",
        "question": "作者在两个月内做了多少个项目？这些项目有什么共同特点？",
        "answer": "11 个项目，共同特点是都是小型独立项目，快速验证想法，注重实用性而非完美性",
        "source_article": "eleven-projects-two-months",
        "difficulty": "easy",
        "type": "factual",
    },

    # ═══════════════════════════════════════════════════════════
    # Git Workflow Best Practices (3 pairs — strengthened)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "git-001",
        "question": "文章对比了哪几种分支策略？各自的优缺点是什么？",
        "answer": "对比了 Git Flow（适合发布周期长的项目，但流程重）、GitHub Flow（简单直接，适合持续部署）、Trunk-Based（最快迭代速度，需要强大的 CI/CD）",
        "source_article": "git-workflow-best-practices",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "git-002",
        "question": "功能分支的工作流程中，从创建到合并需要经过哪些步骤？",
        "answer": "从 main 创建分支 → 本地开发 → 推送到远程 → 创建 PR → Code Review → CI 测试通过 → 合并回 main → 删除分支",
        "source_article": "git-workflow-best-practices",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "git-003",
        "question": "文章认为持续部署场景下最推荐的分支策略是什么？为什么？",
        "answer": "Trunk-Based Development，因为它的迭代速度最快，所有开发者在主干上工作，通过 Feature Flag 控制功能发布，配合强大的 CI/CD 保证质量",
        "source_article": "git-workflow-best-practices",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ═══════════════════════════════════════════════════════════
    # Weather App API (2 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "weather-001",
        "question": "天气应用的三层 API 调用设计中，每个 API 的输入和输出分别是什么？",
        "answer": "定位 API（输入：GPS 坐标→输出：城市编码）→ 天气 API（输入：城市编码→输出：天气数据）→ 空气质量 API（输入：城市编码→输出：AQI 数据）",
        "source_article": "weather-app-api-integration",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "weather-002",
        "question": "为什么要设计成三层串行调用而不是一个 API 获取所有数据？",
        "answer": "每个 API 职责单一，天气 API 不提供定位功能，空气质量 API 需要城市编码作为输入，必须先通过前序 API 获取必要的中间参数",
        "source_article": "weather-app-api-integration",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ═══════════════════════════════════════════════════════════
    # WeChat Mini Program (2 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "wx-001",
        "question": "微信小程序开发中遇到的基础库兼容性问题是什么？如何解决？",
        "answer": "基础库 3.15.2 存在 timeout 问题导致 API 调用超时。解决方案是升级基础库版本或使用兼容性写法",
        "source_article": "wechat-miniprogram-ai-agent",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "wx-002",
        "question": "WXML 中 wx:key 的正确用法是什么？使用 *this 会有什么问题？",
        "answer": "wx:key 应使用字符串指定唯一标识字段名。使用 *this 会导致列表渲染时无法正确识别元素，引起不必要的重渲染和状态丢失",
        "source_article": "wechat-miniprogram-ai-agent",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ═══════════════════════════════════════════════════════════
    # Markdown Notes App (2 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "md-001",
        "question": "Markdown 笔记应用的三栏布局中，每栏的职责是什么？防抖保存机制解决了什么问题？",
        "answer": "文件列表（导航）、编辑器（输入）、预览（实时渲染）。防抖保存避免每次按键都触发 API 调用，减少服务器压力和网络延迟",
        "source_article": "markdown-notes-app",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "md-002",
        "question": "Markdown 实时预览的技术实现方案是什么？",
        "answer": "使用 markdown-it 或类似库将 Markdown 文本转换为 HTML，通过 React 的受控组件实现编辑器和预览的同步更新",
        "source_article": "markdown-notes-app",
        "difficulty": "easy",
        "type": "factual",
    },

    # ═══════════════════════════════════════════════════════════
    # AI Writing Assistant (2 pairs — strengthened)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "aw-001",
        "question": "AI 写作助手的流式输出（SSE）是如何实现的？相比普通 HTTP 请求有什么优势？",
        "answer": "使用 Server-Sent Events 逐 token 推送生成内容。优势是用户无需等待完整响应，首字延迟低，写作体验流畅",
        "source_article": "ai-writing-assistant",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "aw-002",
        "question": "AI 写作助手的多种写作模式在技术实现上有什么区别？",
        "answer": "不同写作模式使用不同的 system prompt 模板来指导 LLM 的输出风格和结构，底层调用同一个 LLM API，通过 prompt 差异化实现模式切换",
        "source_article": "ai-writing-assistant",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # LangChain Framework Guide (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "lcf-001",
        "question": "LCEL（LangChain Expression Language）的管道操作符 | 解决了什么问题？",
        "answer": "解决了链式调用的语法冗余问题，使用 | 操作符连接各组件，代码更简洁，同时原生支持 streaming、async 和并行执行",
        "source_article": "langchain-framework-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lcf-002",
        "question": "create_tool_calling_agent 和 create_react_agent 在底层机制上有什么不同？各自适合什么模型？",
        "answer": "前者依赖模型原生 function calling 能力（如 GPT-4），性能更好但需要模型支持；后者使用 ReAct prompt 模式，所有模型兼容但 token 消耗更高",
        "source_article": "langchain-framework-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "lcf-003",
        "question": "LangGraph 相比 LangChain LCEL 在 Agent 编排上有什么本质提升？",
        "answer": "LangGraph 引入有向图状态机，支持循环调用、条件分支、状态持久化和人机协作，而 LCEL 只能表达线性或简单 DAG 的链式调用",
        "source_article": "langchain-framework-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # LlamaIndex RAG Guide (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "li-001",
        "question": "LlamaIndex 的 RAG Pipeline 三阶段中，每个阶段的核心任务是什么？",
        "answer": "Loading（从各种数据源加载文档）→ Indexing（构建向量索引和文档关系图）→ Querying（检索相关节点并合成回答）",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "li-002",
        "question": "LlamaIndex 的 Response Synthesizer 提供了哪些模式？compact 模式为什么性价比最高？",
        "answer": "提供 compact、refine、simple 等模式。compact 将多个文档压缩后一次性送入 LLM，减少了 LLM 调用次数，同时保持了足够的上下文信息",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "li-003",
        "question": "QueryFusionRetriever 为什么要同时使用 BM25 和向量检索？权重分配的依据是什么？",
        "answer": "BM25 提供关键词精确匹配，向量检索提供语义理解。权重分配（默认 BM25 0.4 + 向量 0.6）反映了语义理解在大多数场景下更重要，但关键词匹配不可替代",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # RAG Concepts Deep Dive (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "ragc-001",
        "question": "RAG 和 Fine-tuning 各自的技术原理是什么？为什么说两者可以互补？",
        "answer": "RAG 通过检索外部知识注入上下文，Fine-tuning 通过训练调整模型权重。互补：RAG 提供最新知识但依赖检索质量，Fine-tuning 提升理解能力但无法更新知识",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "ragc-002",
        "question": "RRF（Reciprocal Rank Fusion）融合公式的原理是什么？为什么 k 值通常取 60？",
        "answer": "RRF 将不同检索器的排名转换为分数 1/(k+rank) 后求和。k=60 是经验值，使排名差异在合理范围内平滑——排名 1 和排名 2 的分数差距不会过大也不会过小",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "ragc-003",
        "question": "Parent-Child 切分策略和普通固定大小切分有什么区别？各自的优缺点是什么？",
        "answer": "Parent-Child：小块检索精确匹配，大块作为上下文返回 LLM。优点是兼顾检索精度和上下文完整性，缺点是实现复杂。固定大小切分简单但可能切断语义",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ═══════════════════════════════════════════════════════════
    # Vector Database Guide (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "vdb-001",
        "question": "HNSW 索引的多层图结构是如何加速近似最近邻搜索的？",
        "answer": "高速公路'，快速定位大致区域；下层是密集的全量向量，精确搜索。检索时从顶层逐层下降，每层缩小搜索范围，大幅减少比较次数",
        "source_article": "vector-database-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "vdb-002",
        "question": "选择向量数据库时，数据规模如何影响选型？",
        "answer": "100 万以下推荐 ChromaDB（轻量、嵌入式）；已有 PostgreSQL 可用 pgvector；千万级以上需要专业向量数据库如 Milvus 或 Pinecone",
        "source_article": "vector-database-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "vdb-003",
        "question": "ChromaDB 作为嵌入式向量数据库有什么优势和局限？",
        "answer": "优势：零配置、Python 原生、适合原型开发。局限：不支持分布式部署、高并发场景性能有限、不适合生产环境大规模数据",
        "source_article": "vector-database-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ═══════════════════════════════════════════════════════════
    # Embedding Models Guide (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "emb-001",
        "question": "BGE 模型和 OpenAI Embedding 在部署方式、成本和效果上各有什么特点？",
        "answer": "BGE 可本地部署零费用、中文效果好、支持 instruction 提升精度；OpenAI Embedding 需 API 调用有成本、英文效果好、1536 维精度更高",
        "source_article": "embedding-models-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "emb-002",
        "question": "Embedding 维度选择需要考虑哪些因素？768 维和 1536 维的实际差异是什么？",
        "answer": "需要权衡精度、速度和存储。768 维（BGE-small）速度快一倍、存储减半，精度损失有限；1536 维（OpenAI）精度更高但推理和存储成本翻倍",
        "source_article": "embedding-models-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "emb-003",
        "question": "BGE 模型在查询编码时加 instruction 前缀的原理是什么？",
        "answer": "用于检索相关文章'提示，使查询向量更偏向匹配而非语义相似",
        "source_article": "embedding-models-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # AI Agent Architecture (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "agenta-001",
        "question": "ReAct 模式中 Thought-Action-Observation 循环的工作原理是什么？",
        "answer": "Thought 阶段 LLM 分析当前状态决定下一步；Action 阶段调用具体工具执行操作；Observation 阶段获取执行结果。循环直到得出最终答案",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "agenta-002",
        "question": "多 Agent 系统中主从模式的编排者如何分配任务？",
        "answer": "编排者分析用户需求，将任务拆解为子任务，根据每个子任务的类型分配给对应的专家 Worker（如 researcher、coder、reviewer）",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "agenta-003",
        "question": "Agent 工具安全设计中，为什么数据库工具默认只读？还有哪些安全原则？",
        "answer": "最小权限原则：默认只读防止误操作。其他原则包括：工具执行前需用户确认、限制单次调用的资源消耗、记录所有工具调用日志用于审计",
        "source_article": "ai-agent-architecture",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # Prompt Engineering Guide (3 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "pe-001",
        "question": "Chain-of-Thought 的三种变体（Zero-shot、Few-shot、Tree-of-Thought）各自的核心思路是什么？",
        "answer": "让我们逐步思考'触发推理；Few-shot CoT 提供带推理过程的示例；Tree-of-Thought 探索多条推理路径选择最优",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "pe-002",
        "question": "Self-Consistency 技术如何提高推理的可靠性？",
        "answer": "多次独立采样（temperature>0）生成不同推理路径，然后投票选择最一致的答案。多样性确保了不会被单一错误推理误导",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "pe-003",
        "question": "RAG 场景中的 Prompt 设计需要遵循哪些规则才能避免幻觉？",
        "answer": "只基于检索到的参考资料回答；无相关信息时明确说明不知道；引用时标注来源；不编造资料中没有的信息；回答要简洁准确",
        "source_article": "prompt-engineering-guide",
        "difficulty": "easy",
        "type": "factual",
    },

    # ═══════════════════════════════════════════════════════════
    # Hello World (2 pairs — NEW, was missing coverage)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "hw-001",
        "question": "作者的博客开张时选择了什么技术栈？为什么做这个选择？",
        "answer": "选择了 React + Vite 的现代前端技术栈，因为开发体验好、构建速度快、社区活跃",
        "source_article": "spa-github-pages",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "hw-002",
        "question": "博客从零搭建到上线经历了哪些关键决策？",
        "answer": "选择技术栈（React+Vite）、设计博客结构（Markdown 驱动）、配置部署流程（GitHub Pages）、添加搜索和分析功能",
        "source_article": "hello-world",
        "difficulty": "medium",
        "type": "synthesis",
    },

    # ═══════════════════════════════════════════════════════════
    # Cross-article queries (6 pairs — strengthened)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "cross-zh-001",
        "question": "LangChain 和 LlamaIndex 在构建 RAG 系统时，各自的技术路线有什么不同？",
        "answer": "LangChain 通过 LCEL 链式编排组件，灵活但需要更多配置；LlamaIndex 提供 Pipeline 三阶段架构（Loading→Indexing→Querying），开箱即用但定制性稍弱",
        "source_article": "langchain-framework-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-002",
        "question": "Hermes Agent 的分层记忆和 AI Agent Architecture 中的 Agent 架构有什么设计理念上的共同点？",
        "answer": "都采用分层设计思想：Hermes 用 L0-L3 分层管理记忆，Agent 架构用 Orchestrator-Worker 分层管理任务。两者都强调模块化、可扩展性和最小权限",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-003",
        "question": "向量数据库选型和 Embedding 模型选择之间有什么关联？如何配合使用？",
        "answer": "向量数据库的索引算法（如 HNSW）影响检索速度，Embedding 模型的维度影响向量大小和精度。低维模型（768d）配轻量数据库（ChromaDB），高维模型（1536d）需要更强的数据库",
        "source_article": "vector-database-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-en-001",
        "question": "Compare the deployment complexity of Railway (Docker) and GitHub Pages (static hosting). What are the trade-offs?",
        "answer": "Railway supports full-stack apps with Docker but requires managing containers, health checks, and build pipelines. GitHub Pages is simpler (static files only) but needs SPA router workarounds and can't run server-side code",
        "source_article": "spa-github-pages",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-en-002",
        "question": "How do React.memo and useMemo serve different optimization purposes? When would you use each?",
        "answer": "React.memo prevents component re-rendering when props haven't changed (component-level optimization). useMemo caches expensive computation results (computation-level optimization). Use memo for child components that receive stable props, useMemo for heavy calculations in render",
        "source_article": "react-performance-tips",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-en-003",
        "question": "Compare BM25 keyword search and vector semantic search in RAG systems. What are their respective strengths and weaknesses?",
        "answer": "BM25 excels at exact keyword matching (entity names, IDs, technical terms) and is fast with no model dependency. Vector search understands semantic similarity (synonyms, paraphrases) but requires embedding models and may miss exact matches. Hybrid approaches combine both strengths",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "cross_article",
    },

    # ═══════════════════════════════════════════════════════════
    # Negative / Unanswerable queries (15 pairs)
    # ═══════════════════════════════════════════════════════════
    {
        "id": "neg-001",
        "question": "Aureon 的 SaaS 定价方案是什么？",
        "answer": "知识库中没有关于 Aureon 定价的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-002",
        "question": "这个项目的团队有多少人？",
        "answer": "知识库中没有关于团队规模的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-003",
        "question": "Aureon 在 AWS 上的部署成本是多少？",
        "answer": "知识库中没有关于 AWS 部署成本的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-004",
        "question": "DeepSeek V4 模型的具体训练数据量是多少？",
        "answer": "知识库中没有关于 DeepSeek 模型训练数据量的信息",
        "source_article": "none",
        "difficulty": "medium",
        "type": "negative",
    },
    {
        "id": "neg-005",
        "question": "LangChain 的最新版本号是多少？",
        "answer": "知识库中没有关于 LangChain 版本号的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-006",
        "question": "这个项目的 GitHub Stars 数量是多少？",
        "answer": "知识库中没有关于 GitHub Stars 的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-007",
        "question": "Aureon 的 API 每分钟请求限制是多少？",
        "answer": "知识库中没有关于 API 速率限制的信息",
        "source_article": "none",
        "difficulty": "medium",
        "type": "negative",
    },
    {
        "id": "neg-008",
        "question": "作者毕业于哪所大学？",
        "answer": "知识库中没有关于作者教育背景的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-009",
        "question": "OpenAI GPT-5 什么时候发布？",
        "answer": "知识库中没有关于 GPT-5 发布时间的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-010",
        "question": "React 19 相比 React 18 有哪些新特性？",
        "answer": "知识库中没有关于 React 19 新特性的详细信息",
        "source_article": "none",
        "difficulty": "medium",
        "type": "negative",
    },
    {
        "id": "neg-011",
        "question": "Docker 的最新版本号是什么？",
        "answer": "知识库中没有关于 Docker 版本号的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-012",
        "question": "Vercel 的免费额度是多少？",
        "answer": "知识库中没有关于 Vercel 免费额度的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-013",
        "question": "ChromaDB 的最新版本有什么更新？",
        "answer": "知识库中没有关于 ChromaDB 最新版本的信息",
        "source_article": "none",
        "difficulty": "medium",
        "type": "negative",
    },
    {
        "id": "neg-014",
        "question": "作者的下一个项目计划做什么？",
        "answer": "知识库中没有关于作者未来项目计划的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-015",
        "question": "PyTorch 和 TensorFlow 哪个更适合生产部署？",
        "answer": "知识库中没有关于 PyTorch 和 TensorFlow 对比的信息",
        "source_article": "none",
        "difficulty": "medium",
        "type": "negative",
    },

    # ===================================================================
    # EXPANDED QA PAIRS (Phase A: Enterprise Benchmark Expansion)
    # All grounded in actual article content - no simulated data
    # ===================================================================

    # ── AI Agent Architecture (deep coverage, article has 270 lines) ──

    {
        "id": "agenta-004",
        "question": "ReAct 模式中的 Thought-Action-Observation 循环，每个阶段分别由什么驱动？",
        "answer": "Thought 由 LLM 推理驱动，决定下一步行动；Action 调用具体工具执行操作；Observation 获取工具返回的执行结果",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "agenta-005",
        "question": "AI Agent 的四个核心组件是什么？各自承担什么职责？",
        "answer": "LLM 作为大脑进行推理决策，Tools 提供与外部世界交互的能力，Memory 管理对话历史和知识，Planning 负责任务分解和执行策略",
        "source_article": "ai-agent-architecture",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "agenta-006",
        "question": "Tool Calling 中的工具安全原则包括哪些？为什么数据库工具要默认只读？",
        "answer": "五项安全原则：最小权限、输入校验（Pydantic）、沙箱执行、速率限制、只读优先。数据库工具默认只读是为了防止 Agent 执行误操作或危险写入",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "agenta-007",
        "question": "Agent 记忆系统中，BufferMemory、SummaryMemory 和 SQLite Checkpointer 各自适合什么场景？",
        "answer": "BufferMemory 适合简单对话，保留所有历史但容量有限；SummaryMemory 适合长对话，压缩历史为摘要；SQLite Checkpointer 适合单用户应用，支持跨会话持久化",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "agenta-008",
        "question": "多 Agent 系统的三种架构模式是什么？生产环境最推荐哪种？",
        "answer": "主从模式（Orchestrator-Worker）由编排者分配任务给专家 Worker；对话模式（Debate/Consensus）多个 Agent 讨论达成共识；流水线模式（Pipeline）每个 Agent 处理特定环节。生产环境推荐主从模式，因为可控性和可预测性最好",
        "source_article": "ai-agent-architecture",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "agenta-009",
        "question": "Agent 在生产环境中需要考虑哪些工程问题？",
        "answer": "可观测性（记录每个 Thought/Action/Observation 便于调试）、超时控制（避免无限循环）、错误恢复（Tool 调用失败时降级策略）、成本控制（监控 token 消耗）、并行执行（无依赖的 Tool 可并行调用）、人机协作（关键决策点加入 Human-in-the-loop 确认）",
        "source_article": "ai-agent-architecture",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ── Prompt Engineering Guide (deep coverage, 319 lines) ──

    {
        "id": "pe-004",
        "question": "Few-shot Learning 的最佳实践包括哪些？示例数量和多样性方面有什么建议？",
        "answer": "示例数量 3-5 个即可，过多浪费 token；示例需要多样性，覆盖正面、负面、中性、边界情况；示例要保持输入输出格式一致",
        "source_article": "prompt-engineering-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "pe-005",
        "question": "Chain-of-Thought 的三种变体 Zero-shot CoT、Few-shot CoT 和 Tree-of-Thought 各自的核心机制是什么？",
        "answer": "Zero-shot CoT 加一句 Let's think step by step 触发推理；Few-shot CoT 提供带推理过程的示例引导；Tree-of-Thought 探索多条推理路径选择最优方案",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "pe-006",
        "question": "Self-Consistency 技术为什么要设置 temperature > 0？投票机制是如何工作的？",
        "answer": "需要一定随机性来生成多条不同推理路径；temperature=0 会导致每次输出相同结果无法采样多样性。通过 Counter 统计所有答案出现频率，选择出现最多的答案作为最终输出",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "pe-007",
        "question": "System Prompt 设计的四个核心原则是什么？优先级排列为什么重要？",
        "answer": "角色定义清晰（让 LLM 知道自己是谁）、边界明确（说明能做什么不能做什么）、格式规范（定义输出格式便于后处理）、优先级排列（重要规则放在前面，因为 LLM 对前面的指令权重更高）",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "pe-008",
        "question": "在 Prompt Engineering 最佳实践中，渐进式优化流程的六个步骤是什么？",
        "answer": "1. 基线（写最简 Prompt 测试基本效果）2. 增强（添加 Few-shot 或 CoT）3. 约束（添加格式要求和边界规则）4. 评估（用评估数据集量化效果）5. 迭代（根据评估结果调整）6. 部署（A/B 测试验证线上效果）",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "factual",
    },
    {
        "id": "pe-009",
        "question": "RAG 场景的 Prompt 设计有哪些专用规则来避免幻觉？",
        "answer": "只基于检索到的参考资料回答；无相关信息时明确回答根据已有资料无法回答；引用信息时标注来源；不编造资料中没有的信息；回答要简洁准确",
        "source_article": "prompt-engineering-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "pe-010",
        "question": "Prompt Engineering 中应避免的五个常见陷阱是什么？",
        "answer": "过度约束（规则太多让 LLM 困惑）、模糊指令（写得好一点不如说用专业但友好的语气）、过长 Prompt（超过 4000 token 效果可能下降）、注入攻击（用户输入可能包含恶意 Prompt）、未测试边界情况（空输入、超长输入、多语言混合）",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "synthesis",
    },
    {
        "id": "pe-011",
        "question": "使用 with_structured_output 强制 LLM 输出结构化数据的优势是什么？",
        "answer": "确保 LLM 输出可解析的结构化数据（如 Pydantic 模型），避免自由文本解析的不确定性，方便下游系统直接使用输出结果，同时可以利用 Pydantic 做字段级别的验证",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── RAG Concepts Deep Dive (239 lines) ──

    {
        "id": "ragc-004",
        "question": "RAG 和 Fine-tuning 在知识更新、成本和可解释性三个维度上各有什么特点？",
        "answer": "知识更新：RAG 实时更新改文档即可，Fine-tuning 需要重新训练。成本：RAG 低无需训练，Fine-tuning 高需要 GPU 和数据标注。可解释性：RAG 高可追溯来源，Fine-tuning 低知识被内化到模型权重中",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "ragc-005",
        "question": "语义切分（Semantic Chunking）的原理是什么？它基于什么指标来判断语义边界？",
        "answer": "基于 embedding 相似度判断语义边界。将文本转换为向量后计算相邻句子的余弦相似度，当相似度低于设定阈值（如 85 分位数）时进行切分，保持语义完整性",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "ragc-006",
        "question": "Parent-Child 切分策略中，大块和小块分别用于什么环节？为什么这样设计？",
        "answer": "小块（如 500 字）用于检索匹配，精确度高；大块（如 2000 字）作为上下文返回给 LLM，提供更完整的语义。检索时匹配小块，返回对应大块作为上下文，兼顾检索精度和上下文完整性",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "reasoning",
    },
    {
        "id": "ragc-007",
        "question": "RRF 融合公式 score(d) = 1/(k + rank_i(d)) 中，k 值为什么通常取 60？如果 k 太小或太大会怎样？",
        "answer": "k=60 是经验值，使排名差异在合理范围内平滑。k 太小会导致排名差异被过度放大（第 1 名和第 2 名差距过大）；k 太大会使排名差异被过度压缩（不同排名的分数过于接近），失去区分度",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "ragc-008",
        "question": "RAG 的评估指标体系中，Recall@K、MRR 和 NDCG 分别衡量什么？",
        "answer": "Recall@K 衡量前 K 个结果中包含多少相关文档（覆盖率）；MRR 衡量第一个相关结果的排名位置（排序质量）；NDCG 考虑所有相关文档的位置权重，排名越靠前得分越高（综合排序质量）",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "ragc-009",
        "question": "RAG 的五种常见优化策略是什么？HyDE 的工作原理是什么？",
        "answer": "Query Rewriting（改写用户问题）、HyDE（让 LLM 先生成假设性回答，用该回答做检索）、多级检索（粗筛到精排）、元数据过滤（利用文档元数据预过滤）、自适应检索（根据问题复杂度动态决定）。HyDE 原理是通过生成假设回答来丰富查询的语义信息",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ── Vector Database Guide (253 lines) ──

    {
        "id": "vdb-004",
        "question": "Flat、IVF 和 HNSW 三种索引算法的时间复杂度和适用规模分别是什么？",
        "answer": "Flat 暴力搜索 O(n*d)，适用 <10 万向量；IVF 倒排文件索引 O(n/k*d)，适用 10 万到 1000 万；HNSW 分层图结构查询速度快内存占用高，适用 10 万到 1 亿向量",
        "source_article": "vector-database-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "vdb-005",
        "question": "ChromaDB 作为嵌入式向量数据库的特点是什么？它默认使用什么索引？",
        "answer": "轻量级、嵌入式、开发者友好，适合原型和中小项目。支持内存模式和持久化存储。默认使用 HNSW 索引，适合 100 万以下向量场景",
        "source_article": "vector-database-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "vdb-006",
        "question": "在生产环境中选择向量数据库时，已有 PostgreSQL 基础设施应该选什么方案？为什么？",
        "answer": "选择 pgvector 扩展，无需额外引入新的基础设施。直接在现有 PostgreSQL 数据库上启用向量扩展，支持 HNSW 索引和余弦相似度查询，适合团队已有 PG 运维经验的场景",
        "source_article": "vector-database-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "vdb-007",
        "question": "Weaviate 向量数据库的独特优势是什么？和 ChromaDB 的主要区别在哪里？",
        "answer": "Weaviate 支持内置混合搜索（向量 + BM25）、GraphQL API、内置向量化模块。和 ChromaDB 的主要区别是 Weaviate 支持混合搜索和更丰富的查询语言，适合需要关键词+语义混合检索的场景",
        "source_article": "vector-database-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "vdb-008",
        "question": "向量数据库性能优化的五个要点是什么？",
        "answer": "1. 维度选择（768 比 1536 快一倍）2. 索引参数调优（HNSW 的 M 和 ef_construction）3. 批量操作减少网络往返 4. 元数据过滤先缩小范围再做向量检索 5. 内存管理注意容量规划",
        "source_article": "vector-database-guide",
        "difficulty": "medium",
        "type": "factual",
    },

    # ── Embedding Models Guide (206 lines) ──

    {
        "id": "emb-004",
        "question": "MTEB 排行榜评估 Embedding 模型的七个维度是什么？对于 RAG 场景最相关的是哪个？",
        "answer": "Classification、Clustering、PairClassification、Retrieval、STS、Summarization、BitextMining。对于 RAG 场景最相关的是 Retrieval 维度，因为它直接衡量检索能力",
        "source_article": "embedding-models-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "emb-005",
        "question": "Embedding 维度从 384 到 3072，每百万向量的存储空间变化如何？实践中推荐什么范围？",
        "answer": "384 维约 1.5GB，512 维约 2GB，768 维约 3GB，1024 维约 4GB，1536 维约 6GB，3072 维约 12GB。实践中 512-1024 维是较好的平衡点",
        "source_article": "embedding-models-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "emb-006",
        "question": "BGE 模型在查询编码时加 instruction 前缀的原理是什么？这个前缀的作用是什么？",
        "answer": "加类似用于检索相关文章的提示前缀，使查询向量更偏向匹配（retrieval-oriented）而非纯语义相似度。这样检索时查询向量会更关注内容相关性，提升检索召回率",
        "source_article": "embedding-models-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "emb-007",
        "question": "什么场景下应该选择本地 Embedding 模型而不是 API 服务？",
        "answer": "数据量大（百万级文档）、需要控制成本（本地免费）、对延迟敏感（离线场景）、数据隐私要求高（不能外传数据到云端）、国内网络环境不稳定",
        "source_article": "embedding-models-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "emb-008",
        "question": "Embedding 模型选型决策流程中，数据量从 1 万以下到 100 万以上，推荐方案如何变化？",
        "answer": "<1万用 OpenAI text-embedding-3-small；1万-100万中文为主用 bge-small-zh；100万+需要 GPU 用 bge-large-zh 或 bge-m3；多语言混合用 bge-m3 或 Jina v3；国内生产不想管 GPU 用 DashScope",
        "source_article": "embedding-models-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── LangChain Framework Guide (265 lines) ──

    {
        "id": "lcf-004",
        "question": "LCEL 的管道操作符 | 在链式编排中解决了什么问题？它有什么原生优势？",
        "answer": "解决了链式调用的语法冗余问题，使用 | 操作符连接各组件使代码更简洁。原生支持 streaming（流式输出）、async（异步执行）和并行执行",
        "source_article": "langchain-framework-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lcf-005",
        "question": "LangChain 的 RAG 链是如何用 LCEL 构建的？每一步的作用是什么？",
        "answer": "先用文本分割器切分文档，创建向量存储。RAG 链用管道连接：retriever 检索相关文档，ChatPromptTemplate 组装上下文和问题，LLM 生成回答，StrOutputParser 解析输出",
        "source_article": "langchain-framework-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lcf-006",
        "question": "LangChain 的三种记忆类型 BufferMemory、WindowMemory、SummaryMemory 分别适合什么场景？",
        "answer": "BufferMemory 保留所有对话历史，适合短对话；WindowMemory 只保留最近 N 轮，适合中等长度对话；SummaryMemory 压缩历史为摘要，适合长对话且 token 受限的场景",
        "source_article": "langchain-framework-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lcf-007",
        "question": "LangChain 最佳实践中的五个关键建议是什么？",
        "answer": "1. 优先使用 LCEL 用管道语法而非旧版 Chain 类 2. 生产环境始终开启 streaming 3. 为每个 Tool 添加异常处理避免链路中断 4. 使用 LangChain v0.3+ 旧版 API 已废弃 5. 涉及状态管理优先选 LangGraph",
        "source_article": "langchain-framework-guide",
        "difficulty": "easy",
        "type": "factual",
    },

    # ── LlamaIndex RAG Guide (262 lines) ──

    {
        "id": "li-004",
        "question": "LlamaIndex 的五种索引类型分别是什么？各自适合什么场景？",
        "answer": "VectorStoreIndex 适合通用语义搜索；SummaryIndex 适合全文摘要；TreeIndex 适合层级问答；KeywordTableIndex 适合关键词搜索；KnowledgeGraphIndex 适合构建实体关系图的知识图谱场景",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "li-005",
        "question": "LlamaIndex 的 QueryFusionRetriever 是如何实现混合检索的？权重设置的依据是什么？",
        "answer": "同时使用 BM25 和向量检索，通过 RRF 融合结果。默认权重 BM25 0.4 + 向量 0.6，反映了语义理解在大多数场景下更重要，但关键词匹配不可替代",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "li-006",
        "question": "Response Synthesizer 的 compact 模式为什么性价比最高？它和 refine 模式有什么区别？",
        "answer": "compact 模式将多个文档压缩后一次性送 LLM，减少调用次数同时保持足够上下文，token 消耗最少。refine 模式逐个文档迭代优化回答质量最好但 token 消耗大、速度慢",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "li-007",
        "question": "LlamaIndex 相比 LangChain 在 RAG 场景下有什么优势？",
        "answer": "LlamaIndex 核心定位是数据索引与 RAG，提供丰富的索引类型（向量/树/图/关键词）和精细的 Retriever + Synthesizer 分离控制。LangChain 定位是通用 LLM 应用编排，RAG 控制粒度较粗但生态更广泛",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "li-008",
        "question": "LlamaIndex 的最佳实践中，chunk_size 调优建议是什么范围？为什么混合检索在多数场景优于单一检索？",
        "answer": "chunk_size 一般 256-1024 tokens，根据文档类型和查询粒度调整。混合检索优于单一检索是因为 BM25 擅长精确关键词匹配，向量擅长语义理解，两者互补能覆盖更多场景",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Hermes Agent Guide (48 lines) ──

    {
        "id": "hermes-008",
        "question": "Hermes Agent 集成四层记忆后，三个量化效果指标分别是什么？",
        "answer": "Token 消耗降低 61%，任务成功率提升 51%，上下文完整性提升 89%",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "hermes-009",
        "question": "Hermes Agent 遇到的三个主要挑战和对应的解决方案是什么？",
        "answer": "多层记忆数据同步冲突用版本控制+乐观锁解决；技能之间工具函数冲突用统一命名空间+自动冲突检测解决；长上下文性能下降用分层压缩策略+动态上下文窗口解决",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── DeepSeek Cache Optimization ──

    {
        "id": "ds-004",
        "question": "DeepSeek KV 缓存按什么匹配？前缀变化会导致什么后果？",
        "answer": "KV 缓存按 token 位置匹配。前缀变化会导致缓存失效，因为位置对不上，后续 token 的 KV 值无法复用已缓存的计算结果",
        "source_article": "deepseek-cache-optimization",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── React Performance Tips ──

    {
        "id": "react-004",
        "question": "useMemo 在什么场景下使用有意义？什么场景是过度优化？",
        "answer": "有意义：复杂计算如排序过滤大列表、创建大对象。过度优化：简单计算如加减乘除、小数据集。判断标准是优化成本大于重算成本时就是过度优化",
        "source_article": "react-performance-tips",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── SPA GitHub Pages ──

    {
        "id": "spa-006",
        "question": "Vite 的 base 配置和 React Router 的 basename 都需要设置的原因是什么？",
        "answer": "base 控制静态资源（JS/CSS）的路径前缀，basename 控制前端路由的路径前缀。两者是独立的系统，资源加载和路由匹配各自独立工作，所以两者都要设置",
        "source_article": "spa-github-pages",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Chatbot Railway Deployment ──

    {
        "id": "rail-004",
        "question": "BGE 模型加载对 Railway 部署的启动时间有什么影响？有哪些优化方案？",
        "answer": "BGE 模型加载需要 60-90 秒，会导致健康检查超时。优化方案：模型预下载到 Docker 镜像、增加健康检查超时时间、将模型加载移到后台线程异步执行",
        "source_article": "chatbot-railway-deployment",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ── Git Workflow ──

    {
        "id": "git-004",
        "question": "Trunk-Based Development 为什么在持续部署场景下迭代速度最快？",
        "answer": "所有开发者在主干上工作避免分支合并开销，通过 Feature Flag 控制功能发布而非分支隔离，配合强大的 CI/CD 保证每次提交质量，实现快速迭代和频繁部署",
        "source_article": "git-workflow-best-practices",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Weather App API ──

    {
        "id": "weather-003",
        "question": "天气应用的三层串行调用设计中，为什么要用城市编码作为中间参数？",
        "answer": "天气 API 和空气质量 API 需要城市编码作为输入参数，但定位 API 返回的是 GPS 坐标。必须先通过定位 API 将坐标转为城市编码，再依次调用天气和空气质量 API，形成串行依赖链",
        "source_article": "weather-app-api-integration",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── WeChat Mini Program ──

    {
        "id": "wx-003",
        "question": "WXML 中使用 *this 作为 wx:key 会有什么问题？正确做法是什么？",
        "answer": "*this 会导致列表渲染时无法正确识别元素，引起不必要的重渲染和状态丢失。正确做法是使用字符串指定唯一标识字段名作为 key",
        "source_article": "wechat-miniprogram-ai-agent",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Markdown Notes App ──

    {
        "id": "md-003",
        "question": "Markdown 笔记应用中防抖保存机制解决了什么问题？为什么不能每次按键都触发保存？",
        "answer": "防抖保存避免每次按键都触发 API 调用，减少服务器压力和网络延迟。如果每次按键都保存会导致频繁的网络请求、高服务器负载和用户体验卡顿",
        "source_article": "markdown-notes-app",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── AI Writing Assistant ──

    {
        "id": "aw-003",
        "question": "AI 写作助手的流式输出（SSE）相比普通 HTTP 请求在用户体验上有什么优势？",
        "answer": "使用 Server-Sent Events 逐 token 推送生成内容。优势是用户无需等待完整响应就能看到内容逐渐出现，首字延迟低，写作体验更流畅自然",
        "source_article": "ai-writing-assistant",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Agent Memory System ──

    {
        "id": "mem-004",
        "question": "从原始对话到用户画像，L1 原子事实层和 L2 场景聚合层分别存储什么粒度的信息？",
        "answer": "L1 存储细粒度的单条事实（如用户喜欢 Python），L2 存储粗粒度的场景聚合（如用户在做一个 RAG 项目使用 Python + LangChain）。L2 是对多个 L1 事实的高阶抽象",
        "source_article": "agent-memory-system",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── RAG System Guide ──

    {
        "id": "rag-004",
        "question": "文档分块时 chunk 大小如何影响检索效果？太大或太小分别有什么问题？",
        "answer": "太大丢失检索精度，一段长文本中可能包含多个主题，难以精确定位；太小丢失上下文完整性，单个 chunk 可能缺乏足够语义信息。推荐 500 字 + 50 字 overlap 作为平衡点",
        "source_article": "rag-system-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Eleven Projects Two Months ──

    {
        "id": "11p-004",
        "question": "作者在快速迭代中对做减法有什么反思？",
        "answer": "做减法比做加法更需要判断力和取舍能力，砍掉已实现的功能比添加新功能更痛苦，但精简后的产品体验更好，技术债务更少",
        "source_article": "eleven-projects-two-months",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Blog Migration ──

    {
        "id": "blog-004",
        "question": "Vercel 部署失败时排查的三个关键步骤是什么？",
        "answer": "检查构建日志中的错误信息、确认环境变量是否正确配置、验证输出目录路径是否与 Vercel 设置匹配",
        "source_article": "blog-migration-troubleshooting",
        "difficulty": "easy",
        "type": "factual",
    },

    # ── Hello World ──

    {
        "id": "hw-003",
        "question": "博客从零搭建到上线的关键技术决策有哪些？",
        "answer": "选择 React+Vite 的现代前端技术栈（开发体验好构建速度快）、设计 Markdown 驱动的博客结构、配置 GitHub Pages 部署流程、添加搜索和分析功能",
        "source_article": "hello-world",
        "difficulty": "medium",
        "type": "synthesis",
    },

    # ── Zustand ──

    {
        "id": "zust-004",
        "question": "Zustand 的状态更新机制是如何实现自动重渲染的？",
        "answer": "直接调用 setter 修改状态，Zustand 内部通过 Proxy 或 subscribe 机制检测变化，自动触发订阅了该状态的组件重渲染",
        "source_article": "zustand-todo-app",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── LangGraph Workflow ──

    {
        "id": "lg-004",
        "question": "LangGraph 的条件边在什么场景下必须使用？和普通边的核心区别是什么？",
        "answer": "普通边是固定路由 A->B，条件边根据状态值动态选择下一个节点。需要根据不同输入走不同路径时必须使用条件边，例如分类结果决定走哪个处理分支",
        "source_article": "langgraph-workflow",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── LangChain Agent Intro ──

    {
        "id": "lc-004",
        "question": "不注册工具的话 Agent 会怎样？为什么工具注册是 Agent 系统的基础？",
        "answer": "不注册工具 Agent 不知道可以调用什么，会试图直接回答所有问题导致幻觉或无法完成需要外部数据的任务。工具注册告诉 Agent 有哪些工具可用及其参数格式",
        "source_article": "langchain-agent-intro",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ===================================================================
    # CROSS-ARTICLE DEEP QUERIES (require multi-document reasoning)
    # ===================================================================

    {
        "id": "cross-zh-004",
        "question": "对比 LangChain、LlamaIndex 和 LangGraph 在 RAG 场景中的定位差异，各自最适合什么阶段的 RAG 系统？",
        "answer": "LangChain 适合简单 RAG 查询和单轮工具调用（基础构建）；LlamaIndex 适合需要精细控制索引和检索的场景（数据索引专精）；LangGraph 适合需要复杂工作流、条件分支和状态持久化的生产级 RAG（高级编排）",
        "source_article": "langchain-framework-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-005",
        "question": "RAG 系统中 Chunking 策略、Embedding 模型选择和向量数据库选型之间如何相互影响？",
        "answer": "Chunking 策略决定向量粒度（小块检索精度高大块上下文完整）；Embedding 维度决定向量大小影响数据库存储和查询性能；向量数据库的索引算法影响不同规模下的检索速度。三者需要协调：如 768 维 Embedding + ChromaDB 适合小规模，1536 维 + Qdrant 适合中规模",
        "source_article": "embedding-models-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-006",
        "question": "Agent 的记忆系统设计（Hermes 四层 vs LangChain Memory）和 RAG 的检索系统有什么设计理念上的共通点？",
        "answer": "都遵循分层处理理念：Hermes 将记忆分为对话-原子-场景-画像逐层抽象；RAG 将文档分为 chunks 逐层检索。两者都通过索引/检索机制在海量数据中快速定位相关信息，区别在于记忆系统偏向用户个性化，RAG 偏向知识检索",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-007",
        "question": "Prompt Engineering 中 System Prompt 的设计原则和 RAG 系统的 Prompt 设计有什么区别？各自关注什么？",
        "answer": "System Prompt 关注角色定义、能力边界、输出格式等全局行为约束。RAG Prompt 关注如何将检索到的上下文和问题组装好传给 LLM，强调只基于参考回答、标注来源、不编造信息。RAG Prompt 是 System Prompt 在特定场景下的应用",
        "source_article": "prompt-engineering-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-008",
        "question": "部署 AI 应用到 Railway 时，Docker 多阶段构建、健康检查和 BGE 模型加载三个环节如何互相影响？",
        "answer": "Docker 多阶段构建将 Node.js 前端构建和 Python 后端运行分离减小镜像；BGE 模型预下载到镜像可减少启动时间；但如果模型太大镜像构建变慢。健康检查需要在模型加载完成后才能通过，所以需要配置足够超时时间",
        "source_article": "chatbot-railway-deployment",
        "difficulty": "hard",
        "type": "cross_article",
    },

    # ===================================================================
    # ADDITIONAL NEGATIVE / EDGE CASE QUERIES
    # ===================================================================

    {
        "id": "neg-016",
        "question": "Aureon 平台的月活跃用户数量是多少？",
        "answer": "知识库中没有关于 Aureon 月活跃用户的数据",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-017",
        "question": "LangChain v0.4 的发布时间是什么？",
        "answer": "知识库中没有关于 LangChain v0.4 发布时间的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-018",
        "question": "作者使用什么键盘和鼠标？",
        "answer": "知识库中没有关于作者外设配置的信息",
        "source_article": "none",
        "difficulty": "easy",
        "type": "negative",
    },
    {
        "id": "neg-019",
        "question": "Hermes Agent 的 GitHub Star 数量增长趋势如何？",
        "answer": "知识库中没有关于 Hermes Agent Star 增长趋势的信息",
        "source_article": "none",
        "difficulty": "medium",
        "type": "negative",
    },
    {
        "id": "neg-020",
        "question": "DeepSeek API 的具体计费单价是多少？",
        "answer": "知识库中没有关于 DeepSeek API 具体定价的信息",
        "source_article": "none",
        "difficulty": "medium",
        "type": "negative",
    },

    # ===================================================================
    # ADDITIONAL EDGE CASE QUERIES
    # ===================================================================

    {
        "id": "edge-004",
        "question": "请用一句话总结 RAG 系统的核心原理",
        "answer": "先检索相关文档再让 LLM 基于检索结果生成回答的技术架构",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "easy",
        "type": "factual",
    },
    {
        "id": "edge-005",
        "question": "React 和 Vue 在 AI 应用前端开发中各有什么优势？",
        "answer": "React 生态更成熟，AI 相关组件库更多如 Vercel AI SDK；Vue 上手更快适合小团队。关键不在框架选择而在状态管理和 API 集成方案",
        "source_article": "react-performance-tips",
        "difficulty": "medium",
        "type": "synthesis",
    },

    # ===================================================================
    # PHASE A EXPANSION: Additional Coverage to 200+ QA
    # ===================================================================

    # ── AI Agent Architecture (additional deep questions) ──

    {
        "id": "agenta-010",
        "question": "Agent 和 Chain、Function Calling 在执行流程、自主性和 token 消耗上有什么区别？",
        "answer": "Chain 执行固定线性流程、无自主性、token 消耗低；Function Calling 由 LLM 决定调用哪个函数、有限自主性单轮、token 消耗中等；Agent 动态多步、高自主性多轮循环、token 消耗高",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "agenta-011",
        "question": "Agent 记忆系统中对话缓冲、滑动窗口和摘要压缩三种方式各自的核心机制是什么？",
        "answer": "对话缓冲保留所有历史记录在内存中；滑动窗口只保留最近 N 轮对话丢弃更早的；摘要压缩用 LLM 将长对话历史压缩为摘要文本，超过 token 限制时自动触发",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "agenta-012",
        "question": "工具注册中 Pydantic BaseModel 结构化输入校验的优势是什么？",
        "answer": "Pydantic 提供类型验证、默认值、字段描述等能力，确保工具输入符合预期格式。相比裸参数更安全可靠，且字段描述可以被 LLM 读取理解工具用法",
        "source_article": "ai-agent-architecture",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Prompt Engineering (additional) ──

    {
        "id": "pe-012",
        "question": "为什么 Prompt Engineering 是一个持续迭代的过程？模型升级后需要做什么？",
        "answer": "因为不同模型对同一 Prompt 的响应可能差异很大，需要根据新模型的特点重新评估和优化现有 Prompt。而且评估数据集也需要随业务变化更新",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "pe-013",
        "question": "Prompt 版本管理为什么重要？应该记录什么信息？",
        "answer": "Prompt 是实验驱动的，需要不断测试调整，版本管理帮助追踪每次修改的效果变化。应该记录每个 Prompt 的版本号、修改内容、对应的评估指标和测试结果",
        "source_article": "prompt-engineering-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── RAG Concepts (additional deep) ──

    {
        "id": "ragc-010",
        "question": "RAG 的完整 Pipeline 中，数据处理阶段和查询阶段分别包含哪些步骤？",
        "answer": "数据处理阶段：文档收集-文档清洗-文档切分-向量化-存入向量数据库。查询阶段：用户问题-问题向量化-检索-重排序-Prompt组装-LLM生成-返回回答",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "medium",
        "type": "factual",
    },
    {
        "id": "ragc-011",
        "question": "RAG vs Fine-tuning 的核心判断标准是什么？什么时候应该结合使用？",
        "answer": "需要最新知识或可溯源回答选 RAG；需要调整模型输出风格或专业格式选 Fine-tuning。两者可以结合：用 Fine-tuning 提升模型对专业领域的理解能力，用 RAG 注入最新知识",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ── Vector Database (additional) ──

    {
        "id": "vdb-009",
        "question": "IVF 索引的 K-Means 聚类机制是如何加速查询的？nprobe 参数控制什么？",
        "answer": "IVF 将向量空间用 K-Means 聚类划分为多个区域（Voronoi cells），查询时只在最近的几个区域搜索而非全量扫描。nprobe 参数控制搜索的聚类数量，越大精度越高但速度越慢",
        "source_article": "vector-database-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "vdb-010",
        "question": "HNSW 索引的 ef_construction 和 M 参数如何影响索引质量和查询速度？",
        "answer": "ef_construction 控制构建索引时的搜索范围，越大索引质量越好但构建越慢。M 控制每个节点的连接数，越大图越密集精度越高但内存占用越大。生产环境需要根据精度和性能需求权衡",
        "source_article": "vector-database-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ── Embedding Models (additional) ──

    {
        "id": "emb-009",
        "question": "为什么文档编码和查询编码必须使用同一个 Embedding 模型？混用会导致什么问题？",
        "answer": "不同模型生成的向量在不同的向量空间中，维度和语义映射都不同，无法直接计算相似度。混用会导致检索结果完全不准确，因为向量之间的距离失去了语义意义",
        "source_article": "embedding-models-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "emb-010",
        "question": "Embedding 模型更新后为什么要重新编码所有文档？监控漂移的意义是什么？",
        "answer": "新版本模型生成的向量与旧版本不在同一向量空间，新旧向量混在一起会导致检索质量下降。监控漂移是在模型更新前评估新模型对现有索引的影响，决定是否需要全量重编码",
        "source_article": "embedding-models-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ── LangChain Framework (additional) ──

    {
        "id": "lcf-008",
        "question": "LangChain vs LangGraph vs Deep Agents 的定位差异是什么？",
        "answer": "LangChain 是基础构建框架适合简单 RAG 和单轮工具调用；LangGraph 是有状态 Agent 编排框架适合复杂工作流和状态持久化；Deep Agents 是自主决策框架适合开放式任务和自我反思",
        "source_article": "langchain-framework-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },
    {
        "id": "lcf-009",
        "question": "create_tool_calling_agent 和 create_react_agent 在底层机制上有什么区别？",
        "answer": "create_tool_calling_agent 依赖模型原生的 function calling 能力，性能更好但需要模型支持；create_react_agent 使用 ReAct prompt 模式，所有模型兼容但 token 消耗更高因为需要更多 prompt 文本",
        "source_article": "langchain-framework-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ── LlamaIndex (additional) ──

    {
        "id": "li-009",
        "question": "LlamaIndex 的 Retriever 后处理中 SimilarityPostprocessor 的作用是什么？",
        "answer": "在检索结果返回前根据相似度分数过滤低质量结果，设置 cutoff 阈值（如 0.7），低于阈值的结果被丢弃，确保返回的都是高相关性文档",
        "source_article": "llamaindex-rag-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Hermes Agent (additional) ──

    {
        "id": "hermes-010",
        "question": "Hermes Agent 为什么选择模块化设计？这对技能整合有什么好处？",
        "answer": "模块化设计解决了技能间工具函数冲突、长上下文性能下降等问题。通过统一命名空间和自动冲突检测，不同技能可以在同一 Agent 中安全共存，每个技能独立管理自己的工具和逻辑",
        "source_article": "hermes-agent-practical-guide",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── DeepSeek Cache (additional) ──

    {
        "id": "ds-005",
        "question": "DeepSeek 缓存命中率从 56% 提升到 76% 的过程中，关键策略的作用原理是什么？",
        "answer": "保持 system prompt 前缀一致是关键策略。原理是 KV 缓存按 token 位置匹配，前缀变化导致整个缓存失效。固定 system prompt 后，后续对话的前缀部分可以直接复用缓存的 KV 值",
        "source_article": "deepseek-cache-optimization",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── React Performance (additional) ──

    {
        "id": "react-005",
        "question": "React.memo 和 useCallback 配合使用时，子组件没有 React.memo 会怎样？",
        "answer": "useCallback 缓存了函数引用避免重建，但子组件没有 React.memo 时仍会在父组件重渲染时重渲染，useCallback 的优化完全无效。只有子组件被 React.memo 包裹时 useCallback 才有实际效果",
        "source_article": "react-performance-tips",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── SPA GitHub Pages (additional) ──

    {
        "id": "spa-007",
        "question": "React SPA 部署到 GitHub Pages 时 404 问题的根本原因是什么？",
        "answer": "GitHub Pages 是静态文件托管，直接请求 /search/path 时服务器找不到对应的 HTML 文件。SPA 路由完全由前端 JavaScript 控制，需要所有路径都返回 index.html 才能正确加载",
        "source_article": "spa-github-pages",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Chatbot Railway Deployment (additional) ──

    {
        "id": "rail-005",
        "question": "Docker 多阶段构建中前端构建产物如何被复制到后端运行镜像中？",
        "answer": "第一阶段用 Node.js 镜像构建前端生成 dist 目录；第二阶段用 Python 镜像时通过 COPY --from=build /app/dist /app/dist 将构建产物跨阶段复制到最终镜像",
        "source_article": "chatbot-railway-deployment",
        "difficulty": "medium",
        "type": "reasoning",
    },

    # ── Cross-article deep (additional) ──

    {
        "id": "cross-zh-009",
        "question": "向量数据库的 HNSW 索引和 Embedding 模型的维度选择如何共同影响 RAG 系统的检索性能？",
        "answer": "高维 Embedding（如 1536d）使 HNSW 图中每个节点的向量更大占用更多内存，查询时距离计算也更慢。低维（如 512d）降低内存和计算成本但可能损失精度。最优配置需要根据文档规模和延迟要求在维度和索引参数之间权衡",
        "source_article": "vector-database-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-010",
        "question": "对比 Agent 的 ReAct 模式和 Prompt Engineering 的 Chain-of-Thought，两者在推理机制上有什么异同？",
        "answer": "相同点：都涉及逐步推理过程。不同点：CoT 是纯推理不涉及外部工具调用，而 ReAct 交替进行推理和行动（Tool Calling），能根据工具返回的 Observation 动态调整策略。CoT 适合纯文本推理任务，ReAct 适合需要外部数据的任务",
        "source_article": "prompt-engineering-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "id": "cross-zh-011",
        "question": "Memory 系统（对话历史管理）和 RAG 系统（知识检索）在架构设计上有什么共同的优化思路？",
        "answer": "两者都使用分层策略：Memory 用 L0-L3 分层抽象，RAG 用分块+索引分层检索。两者都用缓存（Memory 缓存最近对话，RAG 缓存嵌入结果）。两者都面临容量和性能的权衡（Memory 需要压缩策略，RAG 需要 chunk 大小调优）",
        "source_article": "agent-memory-system",
        "difficulty": "hard",
        "type": "cross_article",
    },

    # ── Additional difficult/hard cases ──

    {
        "id": "difficult-004",
        "question": "如果要为一个 1000+ 文档的企业知识库选择完整的 RAG 技术栈，你会推荐什么组合？为什么？",
        "answer": "推荐 bge-large-zh 或 bge-m3 Embedding（多语言高精度）+ ChromaDB 或 Qdrant（取决于是否需要分布式）+ Parent-Child 分块（1500字父+500字子）+ Hybrid 检索（BM25+向量+RRF）+ CrossEncoder Reranker（fp16 加速）+ DeepSeek 生成",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "difficult-005",
        "question": "分析 RAG 系统中幻觉产生的三个主要原因以及对应的缓解策略。",
        "answer": "1. 检索不到相关文档导致 LLM 编造（缓解：Negative Detection + 降低 temperature）2. 检索到相关文档但 LLM 忽略上下文自行发挥（缓解：Faithfulness 约束 Prompt + 引用标注）3. 检索到不相关文档干扰生成（缓解：Context Precision 优化 + 相似度过滤）",
        "source_article": "D-02-faithfulness-vs-relevancy-conflict",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "id": "difficult-006",
        "question": "从生产环境角度，Agent 系统需要哪些可观测性和安全保障？请结合具体技术方案说明。",
        "answer": "可观测性：记录 Thought/Action/Observation 日志（structlog）、Prometheus 指标、LangSmith 追踪。安全保障：工具沙箱执行（避免 eval/exec）、输入验证（Pydantic）、速率限制、权限控制（数据库只读）、Prompt Injection 检测（OWASP regex 模式）",
        "source_article": "ai-agent-architecture",
        "difficulty": "hard",
        "type": "synthesis",
    },
]

# For recall evaluation: expected source articles per query
RETRIEVAL_EXPECTED = {item["question"]: item["source_article"] for item in TEST_QA_PAIRS}

# Statistics
_STATS = {
    "total": len(TEST_QA_PAIRS),
    "by_type": {},
    "by_difficulty": {},
    "by_source": {},
}
for item in TEST_QA_PAIRS:
    _STATS["by_type"][item["type"]] = _STATS["by_type"].get(item["type"], 0) + 1
    _STATS["by_difficulty"][item["difficulty"]] = _STATS["by_difficulty"].get(item["difficulty"], 0) + 1
    _STATS["by_source"][item["source_article"]] = _STATS["by_source"].get(item["source_article"], 0) + 1
