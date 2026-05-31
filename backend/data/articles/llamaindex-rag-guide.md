---
title: "LlamaIndex RAG 开发指南"
slug: "llamaindex-rag-guide"
language: "zh"
source: "llamaindex-rag-guide.md"
---

# LlamaIndex RAG 开发指南

## 什么是 LlamaIndex

LlamaIndex（原名 GPT Index）是一个专为 LLM 应用设计的数据框架，核心能力是将各种数据源与 LLM 连接起来，实现高效的知识检索增强生成（RAG）。

与 LangChain 偏向通用 Agent 编排不同，LlamaIndex 专注于**数据索引和检索**，在 RAG 场景下提供更精细的控制。

## 核心架构：RAG Pipeline

LlamaIndex 的 RAG 流水线分为三个核心阶段：

```
Loading → Indexing → Querying
(数据加载)   (索引构建)   (查询检索)
```

### Stage 1: Loading（数据加载）

LlamaIndex 提供 `Reader` 接口统一加载各类数据源：

```python
from llama_index.core import SimpleDirectoryReader
from llama_index.readers.file import PDFReader, CSVReader

# 从目录加载（自动识别文件类型）
documents = SimpleDirectoryReader("./data").load_data()

# 加载单个 PDF
reader = PDFReader()
documents = reader.load_data(file_path="./report.pdf")

# 加载 CSV
reader = CSVReader()
documents = reader.load_data(file_path="./data.csv")
```

每个 Document 对象包含 `text`（文本内容）和 `metadata`（元数据，如文件名、页码）。

### Stage 2: Indexing（索引构建）

Indexing 将 Document 切分为 Node 并构建可检索的索引结构：

```python
from llama_index.core import VectorStoreIndex, Settings

# 全局设置
Settings.chunk_size = 512
Settings.chunk_overlap = 50

# 构建向量索引
index = VectorStoreIndex.from_documents(documents)

# 或从已有文档增量添加
index.insert_nodes(new_nodes)
```

VectorStoreIndex 是最常用的索引类型，它将文本转换为向量并存储在内存中，支持语义搜索。

### Stage 3: Querying（查询检索）

通过 Retriever 检索相关文档，再由 Response Synthesizer 生成回答：

```python
# 基本查询
query_engine = index.as_query_engine(
    similarity_top_k=5,
    response_mode="compact"
)
response = query_engine.query("什么是 RAG？")
print(response)

# 流式查询
streaming_response = query_engine.query("RAG 的优势是什么？")
for token in streaming_response.response_gen:
    print(token, end="", flush=True)
```

## VectorStoreIndex 深入

### 索引构建方式

```python
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

# 方式 1：内存索引（适合小规模数据）
index = VectorStoreIndex.from_documents(documents)

# 方式 2：持久化到 ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_db")
chroma_collection = chroma_client.get_or_create_collection("docs")
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

storage_context = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex.from_documents(
    documents,
    storage_context=storage_context
)

# 加载已有索引
index = VectorStoreIndex.from_vector_store(
    vector_store=vector_store
)
```

### 索引类型对比

| 索引类型 | 适用场景 | 特点 |
|----------|----------|------|
| VectorStoreIndex | 通用语义搜索 | 向量相似度检索 |
| SummaryIndex | 全文摘要 | 将所有文档拼接后送 LLM |
| TreeIndex | 层级问答 | 构建文档树，逐层检索 |
| KeywordTableIndex | 关键词搜索 | 基于关键词匹配 |
| KnowledgeGraphIndex | 知识图谱 | 构建实体关系图 |

## Retriever 模式

Retriever 负责从索引中检索最相关的文档：

```python
# 默认向量检索
retriever = index.as_retriever(similarity_top_k=5)

# 关键词 + 向量混合检索
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.retrievers import QueryFusionRetriever

bm25_retriever = BM25Retriever.from_documents(documents, similarity_top_k=5)
vector_retriever = index.as_retriever(similarity_top_k=5)

# 混合检索 + RRF 融合
hybrid_retriever = QueryFusionRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    num_queries=3,
    use_async=True,
    retriever_weights=[0.4, 0.6]  # BM25: 向量
)

results = hybrid_retriever.retrieve("LangChain 和 LlamaIndex 的区别")
```

### Retriever 后处理

```python
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.postprocessor import KeywordNodePostprocessor

# 相似度过滤
retriever = index.as_retriever(
    similarity_top_k=10,
    node_postprocessors=[
        SimilarityPostprocessor(similarity_cutoff=0.7)
    ]
)
```

## Response Synthesizer

Response Synthesizer 将检索到的文档和问题组合，生成最终回答：

```python
from llama_index.core import get_response_synthesizer

# compact 模式：将多个文档压缩后一次性送 LLM（默认推荐）
response = get_response_synthesizer(response_mode="compact")

# refine 模式：逐个文档迭代优化回答（更精确但更慢）
response = get_response_synthesizer(response_mode="refine")

# tree_summarize：递归摘要，适合长文档
response = get_response_synthesizer(response_mode="tree_summarize")

# simple_summarize：简单拼接后总结
response = get_response_synthesizer(response_mode="simple_summarize")
```

响应模式选择：
- **compact**：性价比最高，适合大多数场景
- **refine**：质量最好但 token 消耗大，适合重要问答
- **tree_summarize**：适合文档内容过长需要分层摘要

## 集成常见向量数据库

### ChromaDB

```python
import chromadb
from llama_index.vector_stores.chroma import ChromaVectorStore

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("my_docs")
vector_store = ChromaVectorStore(chroma_collection=collection)
```

### Qdrant

```python
from llama_index.vector_stores.qdrant import QdrantVectorStore

vector_store = QdrantVectorStore(
    collection_name="my_docs",
    url="http://localhost:6333",
    api_key="your-api-key"  # 可选
)
```

### Milvus / Zilliz

```python
from llama_index.vector_stores.milvus import MilvusVectorStore

vector_store = MilvusVectorStore(
    collection_name="my_docs",
    uri="http://localhost:19530",
    dim=1536  # 向量维度
)
```

### pgvector

```python
from llama_index.vector_stores.postgres import PGVectorStore

vector_store = PGVectorStore.from_params(
    database="postgres",
    host="localhost",
    password="your-password",
    port=5432,
    user="postgres",
    table_name="my_docs"
)
```

## LlamaIndex vs LangChain

| 维度 | LlamaIndex | LangChain |
|------|-----------|-----------|
| 核心定位 | 数据索引与 RAG | 通用 LLM 应用编排 |
| 索引能力 | 丰富（向量/树/图/关键词） | 基础（主要靠向量存储） |
| Agent 能力 | 有但非重点 | 核心优势 |
| RAG 控制粒度 | 精细（Retriever + Synthesizer 分离） | 中等 |
| 生态集成 | 专注数据连接器和索引 | 广泛的工具和 API 集成 |
| 学习曲线 | RAG 场景较平缓 | 通用但概念多 |

## 最佳实践

1. **从小开始**：先用 VectorStoreIndex 验证效果，再按需切换高级索引
2. **chunk_size 调优**：一般 256-1024 tokens，根据文档类型和查询粒度调整
3. **混合检索**：BM25 + 向量检索的混合模式在多数场景优于单一检索
4. **持久化索引**：生产环境使用向量数据库（Chroma/Qdrant/Milvus）而非内存存储
5. **评估驱动**：使用 LlamaIndex 内置评估模块验证检索和生成质量
6. **上下文窗口**：注意模型的 context window 限制，避免检索结果超出上限
