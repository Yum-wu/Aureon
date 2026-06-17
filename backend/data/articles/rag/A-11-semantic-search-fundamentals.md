# 语义搜索基础：从 TF-IDF 到稠密检索

## 信息检索的演进

语义搜索是信息检索从"关键词匹配"到"语义理解"的演进。这一演进经历了三个主要阶段：统计方法（TF-IDF/BM25）、学习排序（LTR）、以及基于深度学习的稠密检索。

## TF-IDF：统计检索的起点

### 算法原理

TF-IDF（Term Frequency-Inverse Document Frequency）是最经典的文本特征提取方法：

```
TF-IDF(t, d) = TF(t, d) × IDF(t)
```

其中：
- `TF(t, d)`：词 t 在文档 d 中的词频，`count(t, d) / len(d)`
- `IDF(t)`：逆文档频率，`log(N / df(t))`，N 为文档总数，df(t) 为包含词 t 的文档数

### TF-IDF 的局限

1. **无语义理解**：无法区分"苹果"是水果还是公司
2. **词序无关**：丢失了词序信息（"狗咬人" vs "人咬狗"）
3. **稀疏表示**：向量维度等于词表大小，大部分为 0
4. **同义词问题**：无法处理"手机"和"移动电话"的等价关系

## Word2Vec：从稀疏到稠密

### 核心思想

Word2Vec 由 Mikolov 等人在 2013 年提出，将词映射为低维稠密向量，使得语义相似的词在向量空间中距离相近。

### 两种训练方式

1. **CBOW（Continuous Bag of Words）**：根据上下文预测中心词
2. **Skip-Gram**：根据中心词预测上下文

```python
from gensim.models import Word2Vec

# 训练 Word2Vec 模型
sentences = [["检索", "增强", "生成", "技术"], ["语义", "搜索", "是", "信息", "检索"]]
model = Word2Vec(sentences, vector_size=128, window=5, min_count=1, workers=4)

# 获取词向量
vector = model.wv["检索"]

# 语义相似词
similar_words = model.wv.most_similar("检索", topn=5)
```

### Word2Vec 的局限

1. **静态嵌入**：同一词在不同上下文中向量相同（"苹果"水果和公司共享向量）
2. **词级别**：无法直接得到句子/文档级别的表示
3. **OOV 问题**：词表外的词无法获得向量

## BERT：上下文感知的突破

### 核心创新

BERT（Bidirectional Encoder Representations from Transformers）由 Devlin 等人在 2018 年提出，通过双向 Transformer 编码器实现上下文感知的词表示。

### 句子嵌入

BERT 的 [CLS] Token 输出可以直接用作句子嵌入，但效果不如专门训练的句子嵌入模型：

```python
from transformers import AutoTokenizer, AutoModel
import torch

tokenizer = AutoTokenizer.from_pretrained("bert-base-chinese")
model = AutoModel.from_pretrained("bert-base-chinese")

def get_bert_embedding(text: str) -> torch.Tensor:
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
    # 使用 [CLS] token 的输出作为句子嵌入
    return outputs.last_hidden_state[:, 0, :].squeeze()
```

### Mean Pooling

比 [CLS] 更好的策略是对所有 Token 输出取平均：

```python
def mean_pooling(model_output, attention_mask):
    """Mean Pooling：考虑 attention mask 的平均池化"""
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
        input_mask_expanded.sum(1), min=1e-9
    )
```

## Sentence-BERT：专为语义搜索设计

### 核心改进

Sentence-BERT（SBERT）由 Reimers 和 Gurevych 在 2019 年提出，通过 Siamese/Triplet 网络在句子对数据上微调 BERT，使句子嵌入更适合语义相似度计算。

```python
from sentence_transformers import SentenceTransformer

# 使用预训练的 SBERT 模型
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# 编码句子
embeddings = model.encode([
    "什么是检索增强生成？",
    "RAG 技术的原理是什么？",
    "今天天气怎么样？"
])

# 计算相似度
from sklearn.metrics.pairwise import cosine_similarity
sim_matrix = cosine_similarity(embeddings)
# sim_matrix[0][1] ≈ 0.85（语义相似）
# sim_matrix[0][2] ≈ 0.12（语义不相似）
```

## 稠密检索：从编码到检索

### 架构演进

```
TF-IDF → Word2Vec → BERT → SBERT → 领域微调模型（BGE、GTE）
```

### BGE 系列

BAAI 发布的 BGE 系列是当前最流行的中文嵌入模型：

| 模型 | 维度 | 特点 | 性能 |
|------|------|------|------|
| bge-large-zh-v1.5 | 1024 | 中文最优 | C-MTEB 第一 |
| bge-m3 | 1024 | dense+sparse+colbert | 多语言多粒度 |
| bge-small-zh | 512 | 轻量快速 | 延迟低 |

```python
from FlagEmbedding import FlagModel

model = FlagModel("BAAI/bge-large-zh-v1.5", query_instruction_for_retrieval="为这个句子生成表示以用于检索相关文章：")

# 编码查询（需要添加指令前缀）
query_embedding = model.encode_queries(["什么是 RAG？"])

# 编码文档（不需要指令前缀）
doc_embedding = model.encode(["RAG 是检索增强生成技术..."])
```

### 指令增强嵌入

BGE 等模型引入了指令增强（Instruction-augmented Embedding），在编码查询时添加指令前缀：

```python
# 查询编码时添加指令
query_instruction = "为这个句子生成表示以用于检索相关文章："
query_with_instruction = query_instruction + query
query_embedding = model.encode(query_with_instruction)

# 文档编码不需要指令
doc_embedding = model.encode(doc_text)
```

这种设计使得同一模型在检索任务上表现更好，因为指令帮助模型理解编码的目的。

## 向量检索算法

### HNSW

Hierarchical Navigable Small World（HNSW）是最流行的 ANN 算法：

```python
# HNSW 参数对性能的影响
hnsw_params = {
    "m": 32,           # 每层连接数，越大精度越高、内存越大
    "ef_construct": 200, # 构建时的搜索宽度，越大构建越慢但质量越高
    "ef_search": 128,    # 查询时的搜索宽度，越大查询越慢但精度越高
}
```

### 量化策略

```python
# 标量量化：FP32 → INT8
# 精度损失 < 2%，内存减少 4x，查询速度提升 2-3x

# 乘积量化（PQ）
# 将向量分成子空间分别量化
# 精度损失 5-10%，内存减少 8-16x

# 二值量化
# 将向量二值化（sign 函数）
# 精度损失 10-20%，内存减少 32x，查询速度极快
```

## 从稀疏到稠密的融合

现代 RAG 系统不再在稀疏和稠密之间二选一，而是融合两者优势：

```python
async def hybrid_search(
    query: str,
    embedder,
    vectorstore,
    sparse_search_fn,
    k: int = 10,
    rrf_k: int = 60,
) -> list:
    """Hybrid Search：稠密 + 稀疏联合检索"""
    # 稠密检索
    dense_results = await vectorstore.asimilarity_search(query, k=k*2)

    # 稀疏检索
    sparse_results = await sparse_search_fn(query, k=k*2)

    # RRF 融合
    fused = reciprocal_rank_fusion(
        [dense_results, sparse_results], k=rrf_k
    )

    return fused[:k]
```

## 关键事实

1. **语义搜索经历了从 TF-IDF（统计）→ Word2Vec（稠密词向量）→ BERT（上下文感知）→ SBERT（句子嵌入）→ BGE（领域优化）的演进**
2. **TF-IDF 的核心局限**是无语义理解、词序无关、同义词问题，这些是稠密检索要解决的核心问题
3. **指令增强嵌入（Instruction-augmented Embedding）**在编码查询时添加指令前缀，帮助模型理解编码目的，显著提升检索效果
4. **HNSW 是最流行的 ANN 算法**，参数 m=32、ef_construct=200、ef_search=128 是常用的平衡配置
5. **现代 RAG 系统融合稀疏和稠密检索**，通过 RRF 融合两者结果，兼顾关键词精确匹配和语义理解
