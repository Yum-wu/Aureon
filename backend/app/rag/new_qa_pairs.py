NEW_QA_PAIRS = [
    # langchain-framework-guide
    {"id": "lc-001", "question": "LangChain v0.2+ 推荐的链式编排语法是什么？", "answer": "LCEL（LangChain Expression Language），使用管道操作符 `|` 连接各组件，支持 streaming、async、并行执行。", "source_article": "langchain-framework-guide"},
    {"id": "lc-002", "question": "LangChain 中 create_tool_calling_agent 和 create_react_agent 的主要区别是什么？", "answer": "create_tool_calling_agent 依赖模型原生的 function calling 能力，性能更好但需要模型支持；create_react_agent 使用 ReAct prompt 模式，所有模型都兼容但 token 消耗更高。", "source_article": "langchain-framework-guide"},
    {"id": "lc-003", "question": "LangGraph 相比 LangChain 的核心优势是什么？", "answer": "LangGraph 是有状态 Agent 编排框架，基于有向图的状态机，支持循环和条件分支，内置持久化和人机协作，适合复杂 Agent 工作流和多步骤推理。", "source_article": "langchain-framework-guide"},

    # llamaindex-rag-guide
    {"id": "li-001", "question": "LlamaIndex 的 RAG Pipeline 分为哪三个核心阶段？", "answer": "Loading（数据加载）、Indexing（索引构建）、Querying（查询检索）。", "source_article": "llamaindex-rag-guide"},
    {"id": "li-002", "question": "LlamaIndex 的 Response Synthesizer 中 compact 模式的工作原理是什么？", "answer": "compact 模式将多个检索到的文档压缩后一次性送入 LLM 生成回答，是性价比最高的模式，适合大多数场景。", "source_article": "llamaindex-rag-guide"},
    {"id": "li-003", "question": "LlamaIndex 中 QueryFusionRetriever 的默认权重配置示例中 BM25 和向量检索的权重各是多少？", "answer": "BM25 权重 0.4，向量检索权重 0.6。", "source_article": "llamaindex-rag-guide"},

    # rag-concepts-deep-dive
    {"id": "rag-001", "question": "RAG 和 Fine-tuning 各自最适合什么场景？", "answer": "RAG 适合需要最新知识或可溯源回答的知识密集型问答；Fine-tuning 适合需要调整模型输出风格或专业格式的场景，两者也可以结合使用。", "source_article": "rag-concepts-deep-dive"},
    {"id": "rag-002", "question": "RRF（Reciprocal Rank Fusion）的公式是什么，k 通常取多少？", "answer": "公式为 score(d) = Σ 1/(k + rank_i(d))，k 通常取 60。RRF 用于融合不同检索方法的排序结果，无需归一化分数。", "source_article": "rag-concepts-deep-dive"},
    {"id": "rag-003", "question": "RAG 系统中 Parent-Child 切分策略的核心思路是什么？", "answer": "大块用于检索（召回率高），小块用于输入 LLM（精确度高）。检索时匹配 child，返回 parent 作为上下文。", "source_article": "rag-concepts-deep-dive"},

    # vector-database-guide
    {"id": "vdb-001", "question": "HNSW 索引算法的核心结构是什么？", "answer": "HNSW 构建多层图结构，底层包含所有向量，上层是稀疏的"高速公路"。检索时从顶层开始逐层下降，快速定位目标区域，查询速度快但内存占用高。", "source_article": "vector-database-guide"},
    {"id": "vdb-002", "question": "ChromaDB 默认使用什么索引算法，适合什么规模？", "answer": "ChromaDB 默认使用 HNSW 索引，适合 100 万以下向量的场景。", "source_article": "vector-database-guide"},
    {"id": "vdb-003", "question": "在已有 PostgreSQL 基础设施的情况下，推荐使用哪个向量数据库？", "answer": "推荐使用 pgvector，它是 PostgreSQL 扩展，无需额外基础设施。", "source_article": "vector-database-guide"},

    # embedding-models-guide
    {"id": "emb-001", "question": "BGE 模型相比 OpenAI Embedding 的主要优势是什么？", "answer": "BGE 模型可以本地部署、无需 API 费用、中文效果优秀、支持 instruction 提升检索精度。", "source_article": "embedding-models-guide"},
    {"id": "emb-002", "question": "Embedding 维度选择中，768 维（BGE-small）相比 1536 维（OpenAI）的性能差异是什么？", "answer": "768 维比 1536 维快一倍，在精度损失有限时优先选低维以提升检索速度。", "source_article": "embedding-models-guide"},
    {"id": "emb-003", "question": "为什么 BGE 模型在查询编码时建议加 instruction 前缀？", "answer": "加 instruction 前缀可以提升检索精度，例如在查询前添加"为这个句子生成表示以用于检索相关文章："，帮助模型更好地区分文档编码和查询编码的语义差异。", "source_article": "embedding-models-guide"},

    # ai-agent-architecture
    {"id": "agent-001", "question": "ReAct 模式的核心循环是什么？", "answer": "Thought -> Action -> Observation -> Thought -> ... -> Answer，交替进行推理（Thought）和行动（Action）。", "source_article": "ai-agent-architecture"},
    {"id": "agent-002", "question": "Agent 工具安全原则中，为什么数据库查询工具应默认只读？", "answer": "为了遵循最小权限原则，数据库工具默认只读可以防止 Agent 执行 INSERT/UPDATE/DELETE 等写操作，写操作需要额外确认。", "source_article": "ai-agent-architecture"},
    {"id": "agent-003", "question": "在多 Agent 系统的主从模式（Orchestrator-Worker）中，编排者（Orchestrator）的职责是什么？", "answer": "编排者负责根据用户需求将任务分配给合适的专家（Worker），例如将信息搜集分配给 researcher，代码编写分配给 coder，代码审查分配给 reviewer。", "source_article": "ai-agent-architecture"},

    # prompt-engineering-guide
    {"id": "prompt-001", "question": "Chain-of-Thought 的三种主要变体是什么？", "answer": "Zero-shot CoT（简单加"Let's think step by step"）、Few-shot CoT（提供带推理过程的示例）、Tree-of-Thought（探索多个推理路径，选择最优）。", "source_article": "prompt-engineering-guide"},
    {"id": "prompt-002", "question": "Self-Consistency 技术的工作原理是什么？", "answer": "多次独立推理，选择出现最多的一致答案。具体做法是用 temperature > 0 多次采样，然后用投票（Counter）选择最常见的答案及其置信度。", "source_article": "prompt-engineering-guide"},
    {"id": "prompt-003", "question": "RAG 场景中 Prompt 设计的关键规则有哪些？", "answer": "只基于参考资料回答；没有相关信息时明确说明不知道；引用信息时标注来源；不要编造资料中没有的信息；回答要简洁准确。", "source_article": "prompt-engineering-guide"},
]

NEW_RETRIEVAL_EXPECTED = {item["question"]: item["source_article"] for item in NEW_QA_PAIRS}
