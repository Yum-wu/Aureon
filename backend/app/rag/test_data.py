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
        "source_article": "hermes-agent-practical-guide",
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
        "question": "构建阶段常见的两个陷阱是什么？",
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
        "source_article": "hello-world",
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
