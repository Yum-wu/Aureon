"""Golden test datasets for RAG evaluation.

Three tiers aligned with enterprise benchmark framework:
- GOLDEN_192QA: Full 192 QA pairs (weekly / release runs)
- CORE_REGRESSION_40QA: Core 40 QA pairs (every PR) — covers all categories
- DIFFICULT_CASES_20QA: Hard cases (version upgrades, stress testing)

Each entry has: question, answer, source_article, category, difficulty

Updated for Plan A enterprise benchmark upgrade (2026-06-06):
- Expanded from 97 → 192 QA pairs across 25 source articles
- All QA grounded in real article content (no simulated QA)
- Categories: factual(24), reasoning(92), synthesis(42), cross_article(14), negative(20)
- Difficulty: easy(34), medium(105), hard(53)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.test_data import TEST_QA_PAIRS


# ── Layer 1: Full 192 QA (auto-converted from test_data.py) ──

GOLDEN_192QA = [
    {
        "question": qa["question"],
        "answer": qa["answer"],
        "source_article": qa.get("source_article", ""),
        "category": qa.get("type", "unknown"),
        "difficulty": qa.get("difficulty", "medium"),
        "requires_multi_hop": qa.get("type") == "cross_article",
        "is_negative": qa.get("type") == "negative",
    }
    for qa in TEST_QA_PAIRS
]

# ── Layer 2: Core Regression Set (40 QA) ──
# Selected to cover every category, mixed difficulty, diverse article sources
# Designed for CI quality gate — fast feedback on every PR

CORE_REGRESSION_40QA = [
    # ═══ Factual (6) ═══
    {
        "question": "Hermes Agent 的分层记忆系统有几层？每层叫什么？",
        "answer": "4 层：L0 Conversation、L1 Atoms、L2 Scenarios、L3 Persona",
        "source_article": "hermes-agent-practical-guide",
        "category": "factual",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "React SPA 部署到 GitHub Pages 时，路由系统会遇到什么典型问题？如何解决？",
        "answer": "刷新页面会出现 404，因为 GitHub Pages 找不到对应的 HTML 文件。解决方案是复制 index.html 为 404.html",
        "source_article": "spa-github-pages",
        "category": "factual",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "从原始文档到最终生成回答，RAG 系统经历了哪些处理阶段？",
        "answer": "文档加载 → 分块 → 向量嵌入 → 检索 → 生成",
        "source_article": "rag-concepts-deep-dive",
        "category": "factual",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "DeepSeek 的 KV 缓存机制是如何工作的？",
        "answer": "前缀相同的请求可以复用 KV 缓存，跳过 prefill 阶段",
        "source_article": "deepseek-cache-optimization",
        "category": "factual",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "LangChain Agent 的核心执行循环是什么？",
        "answer": "思考 → 选择工具 → 执行工具 → 观察结果 → 再思考",
        "source_article": "langchain-agent-intro",
        "category": "factual",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "LlamaIndex 的 RAG Pipeline 三阶段中，每个阶段的核心任务是什么？",
        "answer": "Loading（加载文档）→ Indexing（构建向量索引）→ Querying（检索并合成回答）",
        "source_article": "llamaindex-rag-guide",
        "category": "factual",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },

    # ═══ Reasoning (10) ═══
    {
        "question": "混合检索为什么比纯向量检索效果好？",
        "answer": "BM25 擅长精确关键词匹配，向量搜索擅长语义理解，混合检索通过 RRF 融合两者优势",
        "source_article": "rag-concepts-deep-dive",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "为什么 useCallback 需要和 React.memo 配合使用才有意义？",
        "answer": "useCallback 缓存函数引用，但子组件没有 React.memo 时仍会重渲染",
        "source_article": "react-performance-tips",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "LangGraph 相比 LangChain LCEL 在什么场景下更有优势？",
        "answer": "需要循环、条件分支、状态持久化时，LangGraph 的状态图比线性链更有优势",
        "source_article": "langgraph-workflow",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "天气应用的三层 API 调用设计中，每个 API 的输入和输出分别是什么？",
        "answer": "定位 API（输入：GPS 坐标→输出：城市编码）→ 天气 API（输入：城市编码→输出：天气数据）→ 空气质量 API（输入：城市编码→输出：AQI 数据）",
        "source_article": "weather-app-api-integration",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "文章对比了哪几种分支策略？各自的优缺点是什么？",
        "answer": "对比了 Git Flow（适合发布周期长的项目，但流程重）、GitHub Flow（简单直接，适合持续部署）、Trunk-Based（最快迭代速度，需要强大的 CI/CD）",
        "source_article": "git-workflow-best-practices",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Docker 多阶段构建在 Railway 部署中解决了什么问题？",
        "answer": "将前端构建和后端运行分离，减小镜像体积",
        "source_article": "chatbot-railway-deployment",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "BGE 模型和 OpenAI Embedding 各有什么特点？",
        "answer": "BGE 可本地部署零费用、中文效果好；OpenAI Embedding 需 API 调用有成本、英文效果好",
        "source_article": "embedding-models-guide",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Zustand 相比 Redux 的核心设计差异是什么？",
        "answer": "无需 Provider、API 极简、细粒度订阅，减少样板代码",
        "source_article": "zustand-todo-app",
        "category": "reasoning",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "微信小程序开发中遇到的基础库兼容性问题是什么？如何解决？",
        "answer": "基础库 3.15.2 存在 timeout 问题导致 API 调用超时。解决方案是升级基础库版本或使用兼容性写法",
        "source_article": "wechat-miniprogram-ai-agent",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "提升 DeepSeek 缓存命中率的关键策略是什么？",
        "answer": "保持 system prompt 前缀一致，让后续对话复用相同 KV 计算",
        "source_article": "deepseek-cache-optimization",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },

    # ═══ Synthesis (8) ═══
    {
        "question": "Hermes Agent 的模块化设计解决了哪些实际工程问题？",
        "answer": "模块化设计解决了技能间工具函数冲突、长上下文性能下降、多层记忆数据同步冲突等问题",
        "source_article": "hermes-agent-practical-guide",
        "category": "synthesis",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "AI Agent 架构中 ReAct 模式的核心循环步骤是什么？",
        "answer": "Thought（推理）→ Action（调用工具）→ Observation（观察结果）→ 循环直到得出 Answer",
        "source_article": "ai-agent-architecture",
        "category": "synthesis",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "向量数据库的 HNSW 索引如何加速近似最近邻搜索？",
        "answer": "上层是稀疏的高速公路快速定位大致区域，下层是密集的全量向量精确搜索。检索时从顶层逐层下降，每层缩小搜索范围",
        "source_article": "vector-database-guide",
        "category": "synthesis",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Prompt Engineering 中 Chain-of-Thought 的三种变体各自的核心思路是什么？",
        "answer": "Zero-shot CoT 用让我们逐步思考触发推理；Few-shot CoT 提供带推理过程的示例；Tree-of-Thought 探索多条推理路径选择最优",
        "source_article": "prompt-engineering-guide",
        "category": "synthesis",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Aureon 的 RAG 系统从查询到回答的完整技术栈，每个环节用了什么技术？",
        "answer": "查询嵌入(DashScope text-embedding-v3) → 混合检索(BM25 jieba分词 + ChromaDB向量搜索) → RRF融合 → LLM生成(DeepSeek v4-flash) → Redis缓存",
        "source_article": "rag-concepts-deep-dive",
        "category": "synthesis",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "十一项目两个月实践中，哪些项目对整体架构思维提升最大？",
        "answer": "AI 聊天机器人项目（全栈技术栈整合）和 RAG 知识库项目（检索增强生成的实际应用）对架构思维提升最大",
        "source_article": "eleven-projects-two-months",
        "category": "synthesis",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Markdown 笔记应用中，本地持久化存储方案有哪些优缺点？",
        "answer": "LocalStorage 简单但容量有限（5-10MB），IndexedDB 容量大但 API 复杂，文件系统 API 最灵活但兼容性差",
        "source_article": "markdown-notes-app",
        "category": "synthesis",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "AI 写作助手的多模型路由策略是如何设计的？",
        "answer": "根据任务类型路由：创意写作用 GPT-4，技术文档用 Claude，日常对话用 GPT-3.5。通过置信度评分动态选择最优模型",
        "source_article": "ai-writing-assistant",
        "category": "synthesis",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },

    # ═══ Cross-article (4) ═══
    {
        "question": "LangChain 和 LlamaIndex 构建 RAG 系统时技术路线有什么不同？",
        "answer": "LangChain 通过 LCEL 链式编排，LlamaIndex 提供 Pipeline 三阶段架构",
        "source_article": "langchain-agent-intro",
        "category": "cross_article",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    {
        "question": "对比 Hermes Agent 和 LangChain Agent 的记忆系统设计差异，哪个更适合长期对话场景？",
        "answer": "Hermes 用 L0-L3 四层记忆架构，从对话到用户画像逐层抽象；LangChain Agent 无内置记忆系统，依赖外部存储。Hermes 更适合长期对话因为有人格层（L3）持久化用户偏好",
        "source_article": "hermes-agent-practical-guide",
        "category": "cross_article",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    {
        "question": "向量数据库选型和 Embedding 模型选择之间有什么关联？",
        "answer": "低维模型配轻量数据库，高维模型需要更强的数据库",
        "source_article": "embedding-models-guide",
        "category": "cross_article",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    {
        "question": "Agent 的 ReAct 模式和 Prompt Engineering 的 Chain-of-Thought 在推理机制上有什么异同？",
        "answer": "相同点：都涉及逐步推理过程。不同点：CoT 是纯推理不涉及外部工具调用，而 ReAct 交替进行推理和行动（Tool Calling），能根据工具返回的 Observation 动态调整策略",
        "source_article": "prompt-engineering-guide",
        "category": "cross_article",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },

    # ═══ Negative (6) ═══
    {
        "question": "Aureon 的 SaaS 定价方案是什么？",
        "answer": "知识库中没有关于 Aureon 定价的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "这个项目的团队有多少人？",
        "answer": "知识库中没有关于团队规模的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "DeepSeek V4 模型的具体训练数据量是多少？",
        "answer": "知识库中没有关于 DeepSeek 模型训练数据量的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "作者毕业于哪所大学？",
        "answer": "知识库中没有关于作者教育背景的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "OpenAI GPT-5 什么时候发布？",
        "answer": "知识库中没有关于 GPT-5 发布时间的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "Aureon 使用了什么微服务架构？各个服务之间如何通信？",
        "answer": "知识库中没有关于 Aureon 微服务架构的信息。Aureon 是一个单体应用，不是微服务架构",
        "source_article": "",
        "category": "negative",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": True,
    },

    # ═══ Edge cases (6) ═══
    {
        "question": "",
        "answer": "请提供具体的问题，知识库可以帮你回答关于 RAG、AI Agent、前端开发、DevOps 等方面的问题。",
        "source_article": "",
        "category": "edge_case",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "!!!@@@###$$$%%%^^^&&&***(((  ???",
        "answer": "无法理解这个问题。请用自然语言描述你的问题",
        "source_article": "",
        "category": "edge_case",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "请详细解释 RAG 系统的每一个技术细节，包括但不限于：向量数据库的选型对比、嵌入模型的选择、分块策略的优化、检索方法的对比、LLM 的选择和 Prompt 工程、评估指标体系、生产环境的监控和告警、成本优化策略、以及如何处理多语言场景下的检索和生成问题。",
        "answer": "这个问题涉及太多方面，无法在一次回答中覆盖所有细节。建议针对具体方面单独提问。",
        "source_article": "rag-concepts-deep-dive",
        "category": "edge_case",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Hermes Agent 在技能执行过程中如何处理工具调用的安全性？",
        "answer": "通过最小权限原则，工具默认只读，写操作需要额外确认，防止 Agent 执行危险操作",
        "source_article": "hermes-agent-practical-guide",
        "category": "edge_case",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "如何优化 AI 应用的性能？",
        "answer": "优化 AI 应用性能可以从多个层面入手：检索层使用混合检索提高召回率，生成层选择更快的 LLM 模型，基础设施层使用 Redis 缓存查询结果",
        "source_article": "rag-concepts-deep-dive",
        "category": "edge_case",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "React 和 Vue 哪个更适合做 AI 应用的前端？",
        "answer": "两者都适合。React 生态更成熟，AI 相关组件库更多；Vue 上手更快，适合小团队。关键不在框架选择，而在状态管理和 API 集成方案",
        "source_article": "react-performance-tips",
        "category": "edge_case",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
]


# ── Layer 3: Difficult Cases (20 QA) ──
# For version upgrades and stress testing — all hard difficulty

DIFFICULT_CASES_20QA = [
    # ═══ Multi-hop deep (5): requires combining info from 2+ articles ═══
    {
        "question": "对比 Hermes Agent 和 LangChain Agent 的记忆系统设计差异，哪个更适合长期对话场景？",
        "answer": "Hermes 用 L0-L3 四层记忆架构，从对话到用户画像逐层抽象；LangChain Agent 无内置记忆系统，依赖外部存储。Hermes 更适合长期对话因为有人格层（L3）持久化用户偏好。",
        "source_article": "hermes-agent-practical-guide",
        "category": "cross_article",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    {
        "question": "如果要为 Aureon 选择向量数据库，结合其 Embedding 模型（1024维）和部署环境（Railway），推荐什么方案？为什么？",
        "answer": "推荐 ChromaDB（轻量嵌入式）+ Railway volume 持久化。1024 维向量在 ChromaDB 中存储约 4KB/chunk，476 chunks 约 2MB，远低于 500MB volume 限制。如果需要更高并发可考虑 Qdrant Cloud。",
        "source_article": "embedding-models-guide",
        "category": "cross_article",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    {
        "question": "分析 RAG 系统中幻觉产生的三个主要原因以及对应的缓解策略。",
        "answer": "1. 检索不到相关文档导致 LLM 编造（缓解：Negative Detection + 降低 temperature）2. 检索到相关文档但 LLM 忽略上下文自行发挥（缓解：Faithfulness 约束 Prompt + 引用标注）3. 检索到不相关文档干扰生成（缓解：Context Precision 优化 + 相似度过滤）",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "question": "向量数据库的 HNSW 索引和 Embedding 模型的维度选择如何共同影响 RAG 系统的检索性能？",
        "answer": "高维 Embedding（如 1536d）使 HNSW 图中每个节点的向量更大占用更多内存，查询时距离计算也更慢。低维（如 512d）降低内存和计算成本但可能损失精度。最优配置需要根据文档规模和延迟要求在维度和索引参数之间权衡",
        "source_article": "vector-database-guide",
        "difficulty": "hard",
        "type": "cross_article",
    },
    {
        "question": "Memory 系统（对话历史管理）和 RAG 系统（知识检索）在架构设计上有什么共同的优化思路？",
        "answer": "两者都使用分层策略：Memory 用 L0-L3 分层抽象，RAG 用分块+索引分层检索。两者都用缓存（Memory 缓存最近对话，RAG 缓存嵌入结果）。两者都面临容量和性能的权衡（Memory 需要压缩策略，RAG 需要 chunk 大小调优）",
        "source_article": "agent-memory-system",
        "difficulty": "hard",
        "type": "cross_article",
    },

    # ═══ Counterfactual (4): knowledge base doesn't have the answer ═══
    {
        "question": "Aureon 使用了什么微服务架构？各个服务之间如何通信？",
        "answer": "知识库中没有关于 Aureon 微服务架构的信息。Aureon 是一个单体应用，不是微服务架构。",
        "source_article": "",
        "category": "negative",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "DeepSeek V4 和 GPT-4o 在 RAG 场景下的性能对比数据是什么？",
        "answer": "知识库中没有关于 DeepSeek V4 和 GPT-4o 在 RAG 场景下的对比数据。",
        "source_article": "",
        "category": "negative",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "Hermes Agent 的分层记忆系统在生产环境中的 QPS 是多少？",
        "answer": "知识库中没有关于 Hermes Agent 分层记忆系统 QPS 的性能数据。",
        "source_article": "",
        "category": "negative",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "LangChain 的最新版本号是多少？",
        "answer": "知识库中没有关于 LangChain 版本号的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },

    # ═══ Synthesis hard (5): requires multi-section comprehension ═══
    {
        "question": "如果要为一个 1000+ 文档的企业知识库选择完整的 RAG 技术栈，你会推荐什么组合？为什么？",
        "answer": "推荐 bge-large-zh 或 bge-m3 Embedding（多语言高精度）+ ChromaDB 或 Qdrant（取决于是否需要分布式）+ Parent-Child 分块（1500字父+500字子）+ Hybrid 检索（BM25+向量+RRF）+ CrossEncoder Reranker（fp16 加速）+ DeepSeek 生成",
        "source_article": "rag-concepts-deep-dive",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "question": "从生产环境角度，Agent 系统需要哪些可观测性和安全保障？请结合具体技术方案说明。",
        "answer": "可观测性：记录 Thought/Action/Observation 日志（structlog）、Prometheus 指标、LangSmith 追踪。安全保障：工具沙箱执行（避免 eval/exec）、输入验证（Pydantic）、速率限制、权限控制（数据库只读）、Prompt Injection 检测（OWASP regex 模式）",
        "source_article": "ai-agent-architecture",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "question": "Embedding 维度选择需要考虑哪些因素？768 维和 1536 维在实际应用中有什么区别？",
        "answer": "需要权衡精度、速度和存储。768 维速度快一倍，1536 维精度更高但成本翻倍",
        "source_article": "embedding-models-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "question": "Chain-of-Thought 的三种变体各自的核心思路是什么？在什么场景下使用哪种？",
        "answer": "Zero-shot CoT 用让我们逐步思考触发推理（通用场景）；Few-shot CoT 提供带推理过程的示例（特定领域）；Tree-of-Thought 探索多条推理路径选择最优（复杂决策场景）",
        "source_article": "prompt-engineering-guide",
        "difficulty": "hard",
        "type": "synthesis",
    },
    {
        "question": "博客迁移过程中遇到的典型问题有哪些？如何系统性地解决？",
        "answer": "典型问题：URL 结构变化导致 404、图片路径失效、Frontmatter 格式不兼容、内部链接断裂。系统性解决方案：建立 URL 映射表、批量修复图片路径、编写格式转换脚本、使用链接检查工具扫描",
        "source_article": "blog-migration-troubleshooting",
        "difficulty": "hard",
        "type": "synthesis",
    },

    # ═══ Ambiguous (3): semantically similar but different answers ═══
    {
        "question": "什么是最好的向量搜索方案？",
        "answer": "没有绝对最好的方案，取决于场景。小规模推荐 ChromaDB，中规模推荐 Qdrant 或 Weaviate，大规模推荐 Milvus 或 Pinecone",
        "source_article": "embedding-models-guide",
        "category": "ambiguous",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "React 和 Vue 哪个更适合做 AI 应用的前端？",
        "answer": "两者都适合。React 生态更成熟，AI 相关组件库更多；Vue 上手更快，适合小团队。关键不在框架选择，而在状态管理和 API 集成方案。",
        "source_article": "react-performance-tips",
        "category": "ambiguous",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "如何优化 AI 应用的性能？",
        "answer": "优化 AI 应用性能可以从多个层面入手：1) 检索层：使用混合检索提高召回率；2) 生成层：选择更快的 LLM 模型；3) 基础设施：使用 Redis 缓存查询结果",
        "source_article": "rag-concepts-deep-dive",
        "category": "ambiguous",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },

    # ═══ Edge cases (3): empty/long/special queries ═══
    {
        "question": "",
        "answer": "请提供具体的问题",
        "source_article": "",
        "category": "edge_case",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "!!!@@@###$$$%%%^^^&&&***(((  ???",
        "answer": "无法理解这个问题",
        "source_article": "",
        "category": "edge_case",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "请详细解释 RAG 系统的每一个技术细节，包括但不限于：向量数据库的选型对比（ChromaDB vs Milvus vs Pinecone vs Weaviate vs Qdrant）、嵌入模型的选择（BGE vs OpenAI vs Cohere vs Jina）、分块策略的优化（固定大小 vs 语义分块 vs 递归分块 vs 父子分块）、检索方法的对比（纯向量 vs BM25 vs 混合检索 vs RRF vs Reranker）、LLM 的选择和 Prompt 工程、评估指标体系（RAGAS vs BEIR vs MTEB）、生产环境的监控和告警、成本优化策略、以及如何处理多语言场景下的检索和生成问题。",
        "answer": "这个问题涉及太多方面，建议针对具体方面单独提问。",
        "source_article": "rag-concepts-deep-dive",
        "category": "edge_case",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
]


# ── Dataset metadata ──

DATASETS = {
    "golden_192qa": {
        "data": GOLDEN_192QA,
        "version": "2026-06-06",
        "description": "Full 192 QA pairs from RAG test suite (25 source articles)",
        "total": len(GOLDEN_192QA),
    },
    "core_regression_40qa": {
        "data": CORE_REGRESSION_40QA,
        "version": "2026-06-06",
        "description": "Core 40 QA pairs for CI quality gate — all categories covered",
        "total": len(CORE_REGRESSION_40QA),
    },
    "difficult_cases_20qa": {
        "data": DIFFICULT_CASES_20QA,
        "version": "2026-06-06",
        "description": "20 difficult cases for version upgrades and stress testing",
        "total": len(DIFFICULT_CASES_20QA),
    },
}


def load_dataset(name: str) -> list:
    """Load a dataset by name."""
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset: {name}. Available: {list(DATASETS.keys())}")
    return DATASETS[name]["data"]


def get_dataset_info(name: str) -> dict:
    """Get dataset metadata."""
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset: {name}")
    info = DATASETS[name].copy()
    info.pop("data")
    return info
