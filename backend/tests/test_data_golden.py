"""Golden test datasets for RAG evaluation.

Three tiers:
- GOLDEN_97QA: Full 97 QA pairs (weekly / release runs)
- CORE_REGRESSION_30QA: Core 30 QA pairs (every PR)
- DIFFICULT_CASES_15QA: Hard cases (version upgrades)

Each entry has: question, answer, source_article, category, difficulty
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.test_data import TEST_QA_PAIRS


# ── Layer 1: Full 97 QA (auto-converted from test_data.py) ──

GOLDEN_97QA = [
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

# ── Layer 2: Core Regression Set (30 QA) ──
# Selected to cover every category, mixed difficulty, both positive and negative

CORE_REGRESSION_30QA = [
    # Factual - easy
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
    # Factual - medium
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
    # Reasoning
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
        "source_article": "langgraph-workflow-guide",
        "category": "reasoning",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # Embedding
    {
        "question": "BGE 模型和 OpenAI Embedding 各有什么特点？",
        "answer": "BGE 可本地部署零费用、中文效果好；OpenAI Embedding 需 API 调用有成本、英文效果好",
        "source_article": "embedding-models-guide",
        "category": "embedding",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Embedding 维度选择需要考虑哪些因素？",
        "answer": "需要权衡精度、速度和存储。768 维速度快一倍，1536 维精度更高但成本翻倍",
        "source_article": "embedding-models-guide",
        "category": "embedding",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # Framework
    {
        "question": "LangChain Agent 的核心执行循环是什么？",
        "answer": "思考 → 选择工具 → 执行工具 → 观察结果 → 再思考",
        "source_article": "langchain-agent-guide",
        "category": "framework",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "LlamaIndex 的 RAG Pipeline 三阶段中，每个阶段的核心任务是什么？",
        "answer": "Loading（加载文档）→ Indexing（构建向量索引）→ Querying（检索并合成回答）",
        "source_article": "llamaindex-rag-guide",
        "category": "framework",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # Deployment
    {
        "question": "Docker 多阶段构建在 Railway 部署中解决了什么问题？",
        "answer": "将前端构建和后端运行分离，减小镜像体积",
        "source_article": "chatbot-railway-deployment",
        "category": "deployment",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Railway 的健康检查机制是如何工作的？",
        "answer": "定期请求健康检查路径，超时未响应则标记容器失败并重启",
        "source_article": "chatbot-railway-deployment",
        "category": "deployment",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # Caching
    {
        "question": "提升 DeepSeek 缓存命中率的关键策略是什么？",
        "answer": "保持 system prompt 前缀一致，让后续对话复用相同 KV 计算",
        "source_article": "deepseek-cache-optimization",
        "category": "caching",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # DevOps
    {
        "question": "Git Flow、GitHub Flow、Trunk-Based 三种分支策略各自的优缺点？",
        "answer": "Git Flow 流程重但适合发布周期长；GitHub Flow 简单直接；Trunk-Based 迭代最快需要强 CI/CD",
        "source_article": "git-workflow",
        "category": "devops",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # Frontend
    {
        "question": "React.memo、useMemo 和 useCallback 三者的优化目标区别？",
        "answer": "React.memo 避免组件重渲染，useMemo 缓存计算结果，useCallback 缓存函数引用",
        "source_article": "react-performance-tips",
        "category": "frontend",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Zustand 相比 Redux 的核心设计差异是什么？",
        "answer": "无需 Provider、API 极简、细粒度订阅，减少样板代码",
        "source_article": "zustand-todo-app",
        "category": "frontend",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # Cross-article (multi-hop)
    {
        "question": "LangChain 和 LlamaIndex 构建 RAG 系统时技术路线有什么不同？",
        "answer": "LangChain 通过 LCEL 链式编排，LlamaIndex 提供 Pipeline 三阶段架构",
        "source_article": "langchain-agent-guide",
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
    # Negative (out of scope) - 8 pairs
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
        "question": "LangChain 的最新版本号是多少？",
        "answer": "知识库中没有关于 LangChain 版本号的信息",
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
        "question": "Docker 的最新版本号是什么？",
        "answer": "知识库中没有关于 Docker 版本号的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "Vercel 的免费额度是多少？",
        "answer": "知识库中没有关于 Vercel 免费额度的信息",
        "source_article": "",
        "category": "negative",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
]


# ── Layer 3: Difficult Cases (15 QA) ──
# For version upgrades and stress testing

DIFFICULT_CASES_15QA = [
    # Multi-hop (3): requires combining info from 2+ documents
    {
        "question": "对比 Hermes Agent 和 LangChain Agent 的记忆系统设计差异，哪个更适合长期对话场景？",
        "answer": "Hermes 用 L0-L3 四层记忆架构，从对话到用户画像逐层抽象；LangChain Agent 无内置记忆系统，依赖外部存储。Hermes 更适合长期对话因为有人格层（L3）持久化用户偏好。",
        "source_article": "hermes-agent-practical-guide",
        "category": "multi_hop",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    {
        "question": "如果要为 Aureon 选择向量数据库，结合其 Embedding 模型（1024维）和部署环境（Railway），推荐什么方案？为什么？",
        "answer": "推荐 ChromaDB（轻量嵌入式）+ Railway volume 持久化。1024 维向量在 ChromaDB 中存储约 4KB/chunk，476 chunks 约 2MB，远低于 500MB volume 限制。如果需要更高并发可考虑 Qdrant Cloud。",
        "source_article": "embedding-models-guide",
        "category": "multi_hop",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    {
        "question": "分析 Aureon 的 RAG 系统从查询到回答的完整技术栈，每个环节用了什么技术？",
        "answer": "查询嵌入(DashScope text-embedding-v3) → 混合检索(BM25 jieba分词 + ChromaDB向量搜索) → RRF融合 → LLM生成(DeepSeek v4-flash) → Redis缓存。",
        "source_article": "rag-concepts-deep-dive",
        "category": "multi_hop",
        "difficulty": "hard",
        "requires_multi_hop": True,
        "is_negative": False,
    },
    # Counterfactual (3): knowledge base doesn't have the answer
    {
        "question": "Aureon 使用了什么微服务架构？各个服务之间如何通信？",
        "answer": "知识库中没有关于 Aureon 微服务架构的信息。Aureon 是一个单体应用，不是微服务架构。",
        "source_article": "",
        "category": "counterfactual",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "DeepSeek V4 和 GPT-4o 在 RAG 场景下的性能对比数据是什么？",
        "answer": "知识库中没有关于 DeepSeek V4 和 GPT-4o 在 RAG 场景下的对比数据。",
        "source_article": "",
        "category": "counterfactual",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    {
        "question": "Hermes Agent 的分层记忆系统在生产环境中的 QPS 是多少？",
        "answer": "知识库中没有关于 Hermes Agent 分层记忆系统 QPS 的性能数据。",
        "source_article": "",
        "category": "counterfactual",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    # Ambiguous (3): semantically similar but different answers
    {
        "question": "如何优化 AI 应用的性能？",
        "answer": "优化 AI 应用性能可以从多个层面入手：1) 检索层：使用混合检索（BM25+向量）提高召回率，缓存嵌入结果减少 API 调用；2) 生成层：选择更快的 LLM 模型，优化 prompt 减少 token 消耗；3) 基础设施：使用 Redis 缓存查询结果，CDN 加速静态资源。",
        "source_article": "rag-concepts-deep-dive",
        "category": "ambiguous",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "什么是最好的向量搜索方案？",
        "answer": "没有绝对最好的方案，取决于场景。小规模（<100万向量）推荐 ChromaDB（零配置、Python原生）；中规模推荐 Qdrant 或 Weaviate（支持分布式）；大规模推荐 Milvus 或 Pinecone（云原生、高并发）。选择时需考虑数据规模、团队技术栈、运维能力。",
        "source_article": "embedding-models-guide",
        "category": "ambiguous",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "React 和 Vue 哪个更适合做 AI 应用的前端？",
        "answer": "两者都适合。React 生态更成熟，AI 相关组件库更多（如 Vercel AI SDK）；Vue 上手更快，适合小团队。Aureon 选择 React 是因为 Vite + React 的开发体验好、构建速度快。关键不在框架选择，而在状态管理和 API 集成方案。",
        "source_article": "react-performance-tips",
        "category": "ambiguous",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    # Edge cases (3): empty/long/special queries
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
        "question": "请详细解释 RAG 系统的每一个技术细节，包括但不限于：向量数据库的选型对比（ChromaDB vs Milvus vs Pinecone vs Weaviate vs Qdrant）、嵌入模型的选择（BGE vs OpenAI vs Cohere vs Jina）、分块策略的优化（固定大小 vs 语义分块 vs 递归分块 vs 父子分块）、检索方法的对比（纯向量 vs BM25 vs 混合检索 vs RRF vs Reranker）、LLM 的选择和 Prompt 工程、评估指标体系（RAGAS vs BEIR vs MTEB）、生产环境的监控和告警、成本优化策略、以及如何处理多语言场景下的检索和生成问题。",
        "answer": "这个问题涉及太多方面，无法在一次回答中覆盖所有细节。知识库中有几篇相关文章可以提供部分信息：1) RAG 核心概念深度解析介绍基本原理和分块策略；2) Embedding 模型选型指南对比 BGE 和 OpenAI；3) LlamaIndex RAG 开发指南介绍 Pipeline 架构。建议针对具体方面单独提问。",
        "source_article": "rag-concepts-deep-dive",
        "category": "edge_case",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "!!!@@@###$$$%%%^^^&&&***(((  ???",
        "answer": "无法理解这个问题。请用自然语言描述你的问题，知识库可以帮你回答关于 RAG、AI Agent、前端开发、DevOps 等方面的问题。",
        "source_article": "",
        "category": "edge_case",
        "difficulty": "easy",
        "requires_multi_hop": False,
        "is_negative": True,
    },
    # Long-tail (3): rare but important
    {
        "question": "Hermes Agent 在技能执行过程中如何处理工具调用的安全性？",
        "answer": "通过最小权限原则，工具默认只读，写操作需要额外确认，防止 Agent 执行危险操作",
        "source_article": "hermes-agent-practical-guide",
        "category": "long_tail",
        "difficulty": "medium",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "HNSW 索引的多层图结构是如何加速近似最近邻搜索的？",
        "answer": "上层是稀疏的'高速公路'快速定位大致区域，下层是密集的全量向量精确搜索。检索时从顶层逐层下降，每层缩小搜索范围。",
        "source_article": "embedding-models-guide",
        "category": "long_tail",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
    {
        "question": "Chain-of-Thought 的三种变体各自的核心思路是什么？",
        "answer": "Zero-shot CoT 用'让我们逐步思考'触发推理；Few-shot CoT 提供带推理过程的示例；Tree-of-Thought 探索多条推理路径选择最优。",
        "source_article": "langchain-agent-guide",
        "category": "long_tail",
        "difficulty": "hard",
        "requires_multi_hop": False,
        "is_negative": False,
    },
]


# ── Dataset metadata ──

DATASETS = {
    "golden_97qa": {
        "data": GOLDEN_97QA,
        "version": "2026-06-04",
        "description": "Full 97 QA pairs from RAG test suite",
        "total": len(GOLDEN_97QA),
    },
    "core_regression_30qa": {
        "data": CORE_REGRESSION_30QA,
        "version": "2026-06-04",
        "description": "Core 30 QA pairs for CI quality gate",
        "total": len(CORE_REGRESSION_30QA),
    },
    "difficult_cases_15qa": {
        "data": DIFFICULT_CASES_15QA,
        "version": "2026-06-04",
        "description": "15 difficult cases for stress testing",
        "total": len(DIFFICULT_CASES_15QA),
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
