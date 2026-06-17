# Cohere Rerank 集成指南

## Cohere Rerank 简介

Cohere Rerank 是业界领先的 Rerank API，基于 Cross-Encoder 架构，支持多语言精排。在 RAG 系统中作为两阶段检索的精排层，显著提升检索精度。

## 集成方式

### API 调用

```python
import cohere

co = cohere.AsyncClient("YOUR_COHERE_API_KEY")

async def cohere_rerank(
    query: str,
    documents: list[str],
    top_n: int = 10,
    model: str = "rerank-v3.5",
) -> list[dict]:
    """Cohere Rerank"""
    response = await co.rerank(
        query=query,
        documents=documents,
        top_n=top_n,
        model=model,
    )

    return [
        {
            "index": result.index,
            "relevance_score": result.relevance_score,
            "document": result.document.text,
        }
        for result in response.results
    ]
```

### LangChain 集成

```python
from langchain_cohere import CohereRerank
from langchain_core.documents import Document

reranker = CohereRerank(
    cohere_api_key="YOUR_API_KEY",
    model="rerank-v3.5",
    top_n=10,
)

async def rerank_documents(
    query: str,
    docs: list[Document],
    top_n: int = 5,
) -> list[Document]:
    """使用 Cohere Rerank 精排文档"""
    # 压缩检索器模式
    from langchain.retrievers import ContextualCompressionRetriever

    compression_retriever = ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=base_retriever,
    )

    compressed_docs = await compression_retriever.ainvoke(query)
    return compressed_docs[:top_n]
```

## 性能特点

| 模型 | 延迟 | 中文支持 | 价格 |
|------|------|---------|------|
| rerank-v3.5 | ~100ms | 优秀 | $0.002/1K searches |
| rerank-v3 | ~80ms | 优秀 | $0.002/1K searches |
| rerank-multilingual | ~120ms | 良好 | $0.002/1K searches |

## 与 DashScope Rerank 对比

| 维度 | Cohere Rerank | DashScope Rerank |
|------|--------------|-----------------|
| 延迟 | ~100ms | ~150ms |
| 中文效果 | 优秀 | 优秀 |
| 价格 | $0.002/1K | ¥0.001/1K |
| API 端点 | api.cohere.com | dashscope.aliyuncs.com |
| 网络延迟 | 较高（海外） | 较低（新加坡） |

Aureon 使用 DashScope Rerank 作为主力，Cohere Rerank 作为备用。

## 关键事实

1. **Cohere Rerank 基于 Cross-Encoder 架构**，支持多语言精排，延迟约 100ms
2. **rerank-v3.5 是最新模型**，中文效果优秀，价格 $0.002/1K searches
3. **LangChain 通过 CohereRerank 和 ContextualCompressionRetriever 集成**，可以无缝替换 Rerank 层
4. **Aureon 使用 DashScope Rerank 作为主力**（延迟更低、网络更近），Cohere Rerank 作为备用
5. **Rerank 的候选数建议 20-50**，太少精度不足，太多延迟增加
