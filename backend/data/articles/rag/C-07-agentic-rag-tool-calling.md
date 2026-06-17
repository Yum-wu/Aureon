# Agentic RAG：工具调用增强检索

## 从被动检索到主动检索

传统 RAG 是被动的——接收查询、检索、生成，流程固定。Agentic RAG 让 LLM Agent 主动决定何时检索、检索什么、如何使用检索结果，通过工具调用（Tool Calling）实现更灵活的检索策略。

## Agentic RAG 架构

### 核心组件

```
用户查询 → LLM Agent →
  ├── 判断是否需要检索 → 调用 search_knowledge_base 工具
  ├── 判断是否需要计算 → 调用 calculator 工具
  ├── 判断是否需要查数据库 → 调用 sql_query 工具
  ├── 判断是否需要搜索网络 → 调用 web_search 工具
  └── 综合所有信息 → 生成最终答案
```

### 工具定义

```python
from langchain_core.tools import tool

@tool
async def search_knowledge_base(query: str, k: int = 5) -> str:
    """搜索内部知识库，获取相关文档。

    Args:
        query: 搜索查询
        k: 返回文档数量

    Returns:
        相关文档内容
    """
    results = await vectorstore.asimilarity_search(query, k=k)
    return "\n\n".join([doc.page_content for doc in results])

@tool
async def search_by_keywords(keywords: list[str], k: int = 5) -> str:
    """通过关键词搜索知识库，适合精确匹配场景。

    Args:
        keywords: 关键词列表
        k: 返回文档数量

    Returns:
        匹配关键词的文档内容
    """
    query = " ".join(keywords)
    results = await sparse_search(query, k=k)
    return "\n\n".join([doc.page_content for doc in results])

@tool
async def web_search(query: str, k: int = 3) -> str:
    """搜索互联网获取最新信息。

    Args:
        query: 搜索查询
        k: 返回结果数量

    Returns:
        搜索结果摘要
    """
    results = await web_search_api.search(query, k=k)
    return "\n\n".join([r["snippet"] for r in results])

@tool
async def sql_query(database: str, query: str) -> str:
    """执行 SQL 查询获取结构化数据。

    Args:
        database: 数据库名称
        query: SQL 查询语句

    Returns:
        查询结果
    """
    result = await db_client.execute(database, query)
    return str(result)
```

### Agent 创建

```python
from langchain.agents import create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

# 注册所有工具
ALL_TOOLS = [
    search_knowledge_base,
    search_by_keywords,
    web_search,
    sql_query,
]

# 创建 Agent
prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一个智能助手，可以搜索知识库和互联网来回答问题。

使用工具时请遵循以下规则：
1. 先尝试搜索知识库，如果知识库中没有相关信息，再搜索互联网
2. 对于精确匹配场景（如产品名称、版本号），使用关键词搜索
3. 对于需要最新信息的查询，使用网络搜索
4. 对于结构化数据查询，使用 SQL 查询
5. 综合所有检索结果生成答案，标注信息来源"""),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, ALL_TOOLS, prompt)
```

## 多步检索

### 迭代检索

Agent 可以根据第一次检索的结果决定是否需要进一步检索：

```python
# 示例对话流程
# 用户：比较 RAG 和 Fine-tuning 的成本

# Agent 步骤 1：搜索 RAG 成本
# → 调用 search_knowledge_base("RAG 成本分析")

# Agent 步骤 2：搜索 Fine-tuning 成本
# → 调用 search_knowledge_base("Fine-tuning 成本分析")

# Agent 步骤 3：发现知识库中 Fine-tuning 信息不足，搜索互联网
# → 调用 web_search("Fine-tuning LLM 成本 2024")

# Agent 步骤 4：综合所有信息生成对比答案
```

### 条件检索

Agent 根据查询类型选择不同的检索策略：

```python
@tool
async def smart_search(query: str, search_type: str = "auto") -> str:
    """智能搜索：根据查询类型自动选择检索策略。

    Args:
        query: 搜索查询
        search_type: 搜索类型（auto/semantic/keyword/hybrid）

    Returns:
        搜索结果
    """
    if search_type == "auto":
        # 自动判断搜索类型
        route = await query_router.route(query)
        if route == "simple":
            return await sparse_search(query)
        elif route == "medium":
            return await hybrid_search(query)
        else:
            return await full_pipeline_search(query)
    elif search_type == "semantic":
        return await semantic_search(query)
    elif search_type == "keyword":
        return await sparse_search(query)
    else:
        return await hybrid_search(query)
```

## 工具调用优化

### 并行工具调用

```python
@tool
async def parallel_search(queries: list[str], k: int = 5) -> str:
    """并行搜索多个查询。

    Args:
        queries: 查询列表
        k: 每个查询返回文档数量

    Returns:
        合并后的搜索结果
    """
    tasks = [vectorstore.asimilarity_search(q, k=k) for q in queries]
    all_results = await asyncio.gather(*tasks)
    fused = reciprocal_rank_fusion(all_results)

    return "\n\n".join([doc.page_content for doc in fused[:k]])
```

### 检索结果缓存

```python
@tool
async def cached_search(query: str, k: int = 5, use_cache: bool = True) -> str:
    """带缓存的搜索。

    Args:
        query: 搜索查询
        k: 返回文档数量
        use_cache: 是否使用缓存

    Returns:
        搜索结果
    """
    if use_cache:
        cache_key = f"search:{query}:{k}"
        cached = await cache.get(cache_key)
        if cached:
            return cached

    results = await vectorstore.asimilarity_search(query, k=k)
    result_text = "\n\n".join([doc.page_content for doc in results])

    if use_cache:
        await cache.set(cache_key, result_text, ttl=300)

    return result_text
```

## Agentic RAG vs 传统 RAG

| 维度 | 传统 RAG | Agentic RAG |
|------|---------|-------------|
| 检索决策 | 固定流程 | Agent 自主决定 |
| 检索次数 | 固定 1 次 | 按需多次 |
| 数据源 | 单一知识库 | 多数据源 |
| 检索策略 | 统一策略 | 按查询选择 |
| 错误恢复 | 无 | Agent 可重试 |
| 延迟 | 低（1-3s） | 高（3-10s） |
| 成本 | 低 | 高（多次 LLM 调用） |
| 灵活性 | 低 | 高 |

## 关键事实

1. **Agentic RAG 通过工具调用让 LLM Agent 主动决定检索策略**，包括何时检索、检索什么、使用哪个数据源
2. **LangChain 的 @tool 装饰器 + create_tool_calling_agent** 是实现 Agentic RAG 的标准方式，工具定义通过 docstring 和类型注解描述
3. **多步检索是 Agentic RAG 的核心优势**——Agent 可以根据第一次检索结果决定是否需要进一步检索
4. **Agentic RAG 的延迟和成本高于传统 RAG**（3-10s vs 1-3s），适合复杂查询场景，简单查询仍建议使用传统 Pipeline
5. **并行工具调用和检索结果缓存**是 Agentic RAG 的关键优化手段，可以减少延迟和成本
