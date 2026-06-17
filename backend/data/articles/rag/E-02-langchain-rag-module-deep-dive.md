# LangChain RAG 模块深度解析

## LangChain RAG 架构

LangChain 是构建 RAG 应用最流行的框架，提供了检索、生成、Agent 等模块化组件。理解其内部架构对于构建高质量 RAG 系统至关重要。

## 核心模块

### VectorStore

LangChain 的向量库抽象层，支持 Qdrant、Pinecone、Chroma 等后端：

```python
from langchain_qdrant import QdrantVectorStore
from langchain_core.embeddings import Embeddings

class CustomEmbeddings(Embeddings):
    """自定义 Embedding 适配器"""

    async def aembed_query(self, text: str) -> list[float]:
        return await embedding_service.embed(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await embedding_service.embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(text))

vectorstore = QdrantVectorStore(
    client=qdrant_client,
    collection_name="aureon_docs",
    embedding=CustomEmbeddings(),
)
```

### Retriever

检索器是 LangChain RAG 的核心抽象：

```python
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

class HybridRetriever(BaseRetriever):
    """自定义 Hybrid 检索器"""

    embedder: Embeddings
    vectorstore: QdrantVectorStore
    sparse_search_fn: callable

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        # Dense 检索
        dense_docs = await self.vectorstore.asimilarity_search(query, k=20)

        # Sparse 检索
        sparse_docs = await self.sparse_search_fn(query, k=20)

        # RRF 融合
        return reciprocal_rank_fusion([dense_docs, sparse_docs])[:10]
```

### ChatModel

LangChain 的 LLM 抽象：

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="qwen3.5-plus",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=settings.DASHSCOPE_API_KEY,
    streaming=True,
    temperature=0.1,
)
```

## RAG Chain 构建

### 基础 RAG Chain

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# Prompt 模板
rag_prompt = ChatPromptTemplate.from_messages([
    ("system", "基于以下上下文回答问题。如果上下文中没有相关信息，请说'我不知道'。\n\n上下文：{context}"),
    ("human", "{query}"),
])

# RAG Chain
rag_chain = (
    {"context": retriever | format_docs, "query": RunnablePassthrough()}
    | rag_prompt
    | llm
    | StrOutputParser()
)

# 执行
answer = await rag_chain.ainvoke("什么是 RAG？")
```

### 流式 RAG Chain

```python
async def stream_rag(query: str):
    """流式 RAG"""
    # 检索
    docs = await retriever.ainvoke(query)
    context = format_docs(docs)

    # 流式生成
    async for chunk in (rag_prompt | llm | StrOutputParser()).astream(
        {"context": context, "query": query}
    ):
        yield chunk
```

## Agent 集成

### Tool Calling Agent

```python
from langchain.agents import create_tool_calling_agent
from langchain_core.tools import tool

@tool
async def search_knowledge_base(query: str, k: int = 5) -> str:
    """搜索知识库"""
    docs = await vectorstore.asimilarity_search(query, k=k)
    return "\n\n".join([doc.page_content for doc in docs])

agent = create_tool_calling_agent(llm, [search_knowledge_base], prompt)

# 流式执行
async for event in agent.astream_events(
    {"messages": [HumanMessage(content="什么是 RAG？")]},
    version="v2",
    config={"callbacks": [langfuse_handler]},
):
    yield event
```

## 关键事实

1. **LangChain RAG 的核心抽象**：VectorStore（向量库）、Retriever（检索器）、ChatModel（LLM）、Chain（链式调用）
2. **自定义 Retriever 继承 BaseRetriever**，实现 `_aget_relevant_documents` 方法，可以封装 Hybrid Search、RRF 融合等逻辑
3. **RAG Chain 使用 LCEL（LangChain Expression Language）**，通过 `|` 管道操作符组合检索、Prompt、LLM、输出解析
4. **流式输出使用 `.astream()` 方法**，逐 Token 推送生成内容，配合 SSE 实现实时响应
5. **Agent 通过 `create_tool_calling_agent` 创建**，工具使用 `@tool` 装饰器定义，LangFuse 追踪通过 `config={"callbacks": [handler]}` 注入
