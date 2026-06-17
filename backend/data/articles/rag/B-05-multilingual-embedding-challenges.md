# 多语言 Embedding 挑战与解决方案

## 多语言检索的核心挑战

全球化场景下，RAG 系统需要支持跨语言检索——用户用中文查询，检索英文文档，或反之。多语言 Embedding 面临以下核心挑战：

1. **语言不对称**：不同语言的语义空间不对齐，"hello"和"你好"在向量空间中可能距离很远
2. **词序差异**：中文"检索增强生成"vs 英文"Retrieval-Augmented Generation"，词序和结构完全不同
3. **分词差异**：中文需要分词，英文按空格分词，日文有三种书写系统
4. **文化差异**：同一概念在不同语言文化中表述方式不同
5. **低资源语言**：训练数据少的语言效果显著差于高资源语言

## 多语言 Embedding 模型

### 模型对比

| 模型 | 支持语言 | 跨语言检索 | 中文效果 |
|------|---------|-----------|---------|
| bge-m3 | 100+ | 优秀 | 优秀 |
| text-embedding-3 | 100+ | 良好 | 良好 |
| LaBSE | 109 | 优秀 | 中等 |
| multilingual-e5 | 100+ | 优秀 | 良好 |
| bge-large-zh | 1（中文） | 不支持 | 最优 |

### 跨语言检索原理

多语言 Embedding 模型通过以下方式实现跨语言对齐：

1. **多语言预训练**：在多语言语料上预训练，学习跨语言的共享表示
2. **翻译对训练**：使用平行语料（翻译对）训练，将翻译对拉近
3. **知识蒸馏**：从单语言教师模型向多语言学生模型蒸馏

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/LaBSE")

# 跨语言检索
queries = ["什么是机器学习？"]  # 中文查询
docs = [
    "Machine learning is a subset of artificial intelligence.",  # 英文文档
    "机器学习是人工智能的分支。",  # 中文文档
    "Deep learning uses neural networks with multiple layers.",  # 英文文档
]

query_embeddings = model.encode(queries)
doc_embeddings = model.encode(docs)

from sklearn.metrics.pairwise import cosine_similarity
similarities = cosine_similarity(query_embeddings, doc_embeddings)
# 中文查询 → 中文文档相似度最高
# 中文查询 → 英文文档相似度也较高（跨语言对齐）
```

## BGE-M3 的多语言能力

### 架构特点

BGE-M3 基于 XLM-RoBERTa，在多语言数据上训练，支持 100+ 语言：

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

# 多语言编码
texts = [
    "什么是 RAG？",                          # 中文
    "What is RAG?",                          # 英文
    "RAGとは何ですか？",                      # 日文
    "Qu'est-ce que RAG ?",                   # 法文
]

embeddings = model.encode(texts)

# 跨语言相似度
from numpy import dot
from numpy.linalg import norm

for i in range(1, len(texts)):
    sim = dot(embeddings[0], embeddings[i]) / (norm(embeddings[0]) * norm(embeddings[i]))
    print(f"中文 vs {texts[i][:20]}: {sim:.3f}")
# 中文 vs What is RAG?: 0.92
# 中文 vs RAGとは何ですか？: 0.89
# 中文 vs Qu'est-ce que RAG: 0.87
```

### 多语言 Hybrid Search

```python
async def multilingual_hybrid_search(
    query: str,
    model,
    vectorstore,
    k: int = 10,
) -> list:
    """多语言 Hybrid Search"""
    output = model.encode(
        [query],
        return_dense=True,
        return_sparse=True,
    )

    dense_vec = output["dense_vecs"][0]
    sparse_vec = output["lexical_weights"][0]

    # Qdrant Hybrid Search
    results = client.query_points(
        collection_name="multilingual_docs",
        prefetch=[
            Query(vector_name="dense", vector=dense_vec.tolist(), limit=k*2),
            Query(vector_name="sparse", vector=sparse_vec, limit=k*2),
        ],
        query=FusionQuery(fusion="rrf"),
        limit=k,
    )

    return results
```

## 跨语言检索优化

### 查询翻译 + 双语检索

```python
async def cross_lingual_retrieve(
    query: str,
    source_lang: str,
    target_langs: list[str],
    translator,
    embedder,
    vectorstore,
    k: int = 10,
) -> list:
    """跨语言检索：翻译查询 + 多语言检索"""
    all_results = []

    # 原始语言检索
    original_results = await vectorstore.asimilarity_search(query, k=k*2)
    all_results.append(original_results)

    # 翻译查询到其他语言
    for target_lang in target_langs:
        translated_query = await translator.translate(query, source_lang, target_lang)
        results = await vectorstore.asimilarity_search(translated_query, k=k*2)
        all_results.append(results)

    # RRF 融合
    return reciprocal_rank_fusion(all_results)[:k]
```

### 语言检测 + 路由

```python
import langdetect

class LanguageAwareRetriever:
    """语言感知检索器"""

    def __init__(self, embedder, vectorstores: dict[str, VectorStore]):
        self.embedder = embedder
        self.vectorstores = vectorstores  # lang → vectorstore

    async def retrieve(self, query: str, k: int = 10) -> list:
        # 检测查询语言
        detected_lang = langdetect.detect(query)

        # 如果有对应语言的向量库，优先检索
        if detected_lang in self.vectorstores:
            primary_results = await self.vectorstores[detected_lang].asimilarity_search(query, k=k*2)
        else:
            primary_results = []

        # 同时检索多语言向量库
        multi_results = await self.vectorstores["multilingual"].asimilarity_search(query, k=k*2)

        # 融合
        return reciprocal_rank_fusion([primary_results, multi_results])[:k]
```

## 低资源语言处理

### 回译增强

```python
async def back_translation_augmentation(
    query: str,
    source_lang: str,
    pivot_lang: str,  # 中介语言（通常是英文）
    translator,
) -> list[str]:
    """回译增强：通过翻译-回译生成查询变体"""
    # 翻译到中介语言
    translated = await translator.translate(query, source_lang, pivot_lang)

    # 回译到源语言
    back_translated = await translator.translate(translated, pivot_lang, source_lang)

    return [query, translated, back_translated]
```

### 零样本跨语言迁移

利用高资源语言的数据提升低资源语言的效果：

```python
# 使用多语言模型实现零样本跨语言迁移
# 训练数据：英文查询-文档对
# 推理时：直接用于中文查询检索中文文档
# 前提：模型已经学习了跨语言的语义对齐
```

## 多语言 RAG 的最佳实践

1. **优先使用 BGE-M3**：100+ 语言支持，跨语言对齐效果好
2. **构建多语言向量库**：所有语言的文档存储在同一个集合中
3. **启用 Hybrid Search**：dense + sparse 联合检索，稀疏向量对关键词匹配更鲁棒
4. **语言检测 + 路由**：检测查询语言，优先检索对应语言的子集
5. **翻译辅助**：对低资源语言查询，翻译到高资源语言后双语检索

## 关键事实

1. **多语言 Embedding 的核心挑战**是语言不对称、词序差异、分词差异和文化差异，导致不同语言的语义空间不对齐
2. **BGE-M3 支持 100+ 语言**，基于 XLM-RoBERTa 训练，跨语言检索相似度可达 0.87-0.92
3. **跨语言检索的两种策略**：直接使用多语言模型（简单高效）vs 查询翻译+双语检索（更精确但更慢）
4. **Hybrid Search 对多语言场景尤为重要**——稀疏向量对关键词匹配更鲁棒，弥补稠密向量的跨语言精度损失
5. **低资源语言处理**可以通过回译增强和零样本跨语言迁移来提升效果，但高资源语言的数据质量仍是关键
