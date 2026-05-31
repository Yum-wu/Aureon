---
title: "RAG 核心概念深度解析"
slug: "rag-concepts-deep-dive"
language: "zh"
source: "rag-concepts-deep-dive.md"
---

# RAG 核心概念深度解析

## 什么是 RAG

RAG（Retrieval-Augmented Generation，检索增强生成）是一种将外部知识检索与大语言模型生成相结合的技术架构。核心思路：先从知识库中检索相关文档，再将检索结果作为上下文输入 LLM 生成回答。

基本公式：`问题 → 检索 → 上下文 + 问题 → LLM → 回答`

## 为什么需要 RAG

### RAG vs Fine-tuning

| 维度 | RAG | Fine-tuning |
|------|-----|-------------|
| 知识更新 | 实时更新，改文档即可 | 需要重新训练 |
| 成本 | 低（无需训练） | 高（GPU + 数据标注） |
| 可解释性 | 高（可追溯来源） | 低（知识内化） |
| 适用场景 | 知识密集型问答 | 风格/格式调整 |
| 幻觉控制 | 好（有引用支撑） | 一般 |
| 数据量要求 | 少量即可 | 通常需要大量数据 |

核心判断：如果需要的是**最新知识**或**可溯源的回答**，选 RAG；如果需要调整模型的**输出风格**或**专业格式**，选 Fine-tuning。两者也可以结合使用。

## 完整 RAG Pipeline

```
数据处理阶段：
  文档收集 → 文档清洗 → 文档切分（Chunking）→ 向量化（Embedding）→ 存入向量数据库

查询阶段：
  用户问题 → 问题向量化 → 检索（Retrieval）→ [重排序 Reranking] → Prompt 组装 → LLM 生成 → 返回回答
```

### 1. 文档切分（Chunking）

将长文档切分为适合检索的小片段，是影响 RAG 质量的关键环节。

**固定长度切分（Fixed-size Chunking）**：

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,      # 每个块 500 字符
    chunk_overlap=100,   # 相邻块重叠 100 字符
    separators=["\n\n", "\n", "。", "，", " "]  # 优先切分点
)
chunks = splitter.split_documents(documents)
```

优点：实现简单，处理速度快。缺点：可能切断语义边界。

**语义切分（Semantic Chunking）**：

```python
# 基于 embedding 相似度判断语义边界
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings

splitter = SemanticChunker(
    OpenAIEmbeddings(),
    breakpoint_threshold_type="percentile",
    breakpoint_threshold_amount=85  # 相似度低于 85 分位数时切分
)
chunks = splitter.split_documents(documents)
```

优点：保持语义完整性。缺点：需要 embedding 调用，速度较慢。

**Parent-Child 切分**：

```python
# 大块用于检索（召回率高），小块用于输入 LLM（精确度高）
parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000)
child_splitter = RecursiveCharacterTextSplitter(chunk_size=500)

parent_chunks = parent_splitter.split_documents(documents)
child_chunks = child_splitter.split_documents(documents)

# 检索时匹配 child，返回 parent 作为上下文
```

### 2. 向量化（Embedding）

将文本转换为高维向量，使语义相似的文本在向量空间中距离相近：

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# 单条文本向量化
vector = embeddings.embed_query("什么是 RAG？")

# 批量向量化
vectors = embeddings.embed_documents(["文档1", "文档2", "文档3"])
```

### 3. 检索方法

**向量检索（Vector Search）**：

```python
# 基于余弦相似度的语义检索
results = vectorstore.similarity_search("RAG 的优势", k=5)

# 带分数的检索
results = vectorstore.similarity_search_with_score("RAG 的优势", k=5)
```

**BM25 检索（关键词检索）**：

```python
from langchain.retrievers import BM25Retriever

bm25_retriever = BM25Retriever.from_documents(documents, k=5)
results = bm25_retriever.invoke("RAG 优势")
```

BM25 基于 TF-IDF 的词频统计，擅长精确关键词匹配，不理解语义但速度快。

**混合检索 + RRF 融合**：

```python
from langchain.retrievers import EnsembleRetriever

ensemble_retriever = EnsembleRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    weights=[0.3, 0.7]  # BM25 权重 0.3，向量权重 0.7
)
results = ensemble_retriever.invoke("RAG 的优势是什么")
```

RRF（Reciprocal Rank Fusion）公式：`score(d) = Σ 1/(k + rank_i(d))`，k 通常取 60。RRF 融合不同检索方法的排序结果，无需归一化分数。

### 4. 重排序（Reranking）

检索后对候选文档重新排序，提高相关性：

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

# 使用 Cohere Rerank
reranker = CohereRerank(model="rerank-multilingual-v3.0", top_n=5)

compression_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=ensemble_retriever
)
results = compression_retriever.invoke("RAG 的优势")
```

### 5. 生成（Generation）

将检索结果组装为 Prompt，输入 LLM 生成回答：

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_template("""
请根据以下参考资料回答用户问题。

要求：
1. 只基于提供的参考资料回答
2. 如果资料中没有相关信息，明确说明不知道
3. 引用信息时标注来源

参考资料：
{context}

用户问题：{question}
""")
```

## 评估指标

### 检索质量指标

**Recall@k**：前 k 个检索结果中包含的相关文档比例

```
Recall@5 = 命中的相关文档数 / 总相关文档数
```

**MRR（Mean Reciprocal Rank）**：第一个相关结果排名的倒数的均值

```
MRR = (1/Q) × Σ(1/rank_i)
```

如果第一个相关结果排第 1 位，RR=1.0；排第 3 位，RR=0.333。

**NDCG（Normalized Discounted Cumulative Gain）**：考虑相关文档在排序中位置的归一化得分

```
DCG@k = Σ(2^rel_i - 1) / log2(i + 1)
NDCG@k = DCG@k / IDCG@k
```

相关文档排在前面时 NDCG 更高。

### 生成质量指标

**Faithfulness（忠实度）**：生成的回答是否忠实于检索到的上下文

```python
# 使用 RAGAS 框架评估
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

eval_results = evaluate(
    dataset=eval_dataset,
    metrics=[faithfulness, answer_relevancy, context_precision]
)
print(eval_results)
```

**Answer Relevancy（答案相关性）**：回答是否切题

**Context Precision（上下文精确度）**：检索到的上下文中有多少是相关的

**Context Recall（上下文召回率）**：回答所需的信息是否都被检索到了

## 常见优化策略

1. **Query Rewriting**：改写用户问题，提升检索命中率
2. **HyDE**：让 LLM 先生成假设性回答，用该回答做检索
3. **多级检索**：粗筛（向量检索）→ 精排（Reranker）
4. **元数据过滤**：利用文档元数据（日期、类别）预过滤候选集
5. **自适应检索**：根据问题复杂度动态决定是否需要检索
