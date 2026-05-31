---
title: "Embedding 模型选型指南"
slug: "embedding-models-guide"
language: "zh"
source: "embedding-models-guide.md"
---

# Embedding 模型选型指南

## 什么是 Embedding

Embedding（向量嵌入）是将文本转换为固定长度的数值向量的过程。语义相似的文本在向量空间中距离相近，语义不同的文本距离较远。这是 RAG、语义搜索、聚类、分类等应用的基础技术。

核心原理：深度神经网络（通常是 Transformer 架构）将文本编码为高维向量，向量中的每个维度捕捉文本的某种语义特征。

## 主流 Embedding 模型

### OpenAI text-embedding 系列

```python
from langchain_openai import OpenAIEmbeddings

# text-embedding-3-small：性价比最高
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# text-embedding-3-large：最高精度
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

# 支持维度裁剪（MRL，Matryoshka Representation Learning）
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    dimensions=512  # 从 1536 维裁剪到 512 维
)
```

OpenAI embedding 支持 Matryoshka 表示学习，可以用较短维度的向量获得接近完整维度的效果。

### BGE 系列（BAAI）

BGE（BAAI General Embedding）由智源研究院开发，在中文场景表现优异：

```python
from langchain_huggingface import HuggingFaceEmbeddings

# bge-small-zh-v1.5：轻量级，130MB，中文优化
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True}
)

# bge-base-zh-v1.5：中等规模，400MB
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-base-zh-v1.5"
)

# bge-large-zh-v1.5：最高精度，1.3GB
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-large-zh-v.5"
)

# bge-m3：多语言模型，支持 100+ 语言
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3"
)
```

BGE 模型特点：本地部署、无需 API 费用、中文效果好、支持 `instruction` 提升检索精度。

### DashScope（阿里云通义）

```python
from langchain_community.embeddings import DashScopeEmbeddings

# text-embedding-v2：阿里云通义千问 embedding
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",
    dashscope_api_key="your-api-key"
)
```

国内使用友好，延迟低，价格便宜。

### Jina Embeddings

```python
# Jina Embeddings v3：多语言，支持多维度输出
embeddings = HuggingFaceEmbeddings(
    model_name="jinaai/jina-embeddings-v3",
    model_kwargs={"trust_remote_code": True}
)
```

## 模型对比表

| 模型 | 维度 | 大小 | 中文效果 | 部署方式 | 延迟 | 价格 |
|------|------|------|---------|---------|------|------|
| text-embedding-3-small | 1536 | API | 良好 | 云端 API | ~50ms | 低 |
| text-embedding-3-large | 3072 | API | 良好 | 云端 API | ~80ms | 中 |
| bge-small-zh | 512 | 130MB | 优秀 | 本地 | ~10ms | 免费 |
| bge-base-zh | 768 | 400MB | 优秀 | 本地 | ~30ms | 免费 |
| bge-large-zh | 1024 | 1.3GB | 优秀 | 本地(GPU) | ~50ms | 免费 |
| bge-m3 | 1024 | 2.3GB | 优秀 | 本地(GPU) | ~80ms | 免费 |
| DashScope v2 | 1536 | API | 良好 | 云端 API | ~30ms | 低 |
| Jina v3 | 1024 | API | 良好 | 云端/本地 | ~50ms | 中 |

## 本地 vs API 选择

### 选择 API 的场景

- 数据量小，调用频率低
- 不想管理 GPU 资源
- 需要快速原型验证
- 网络延迟可接受

### 选择本地模型的场景

- 数据量大（百万级以上文档）
- 需要控制成本（免费）
- 对延迟敏感（离线场景）
- 数据隐私要求高（不能外传）
- 国内网络环境（API 可能不稳定）

### 本地部署示例

```python
from sentence_transformers import SentenceTransformer
import numpy as np

# 加载模型（首次自动下载）
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

# 编码文档
documents = [
    "RAG 是检索增强生成技术",
    "LangChain 是 LLM 应用开发框架",
    "向量数据库用于存储和检索向量"
]
doc_embeddings = model.encode(documents, normalize_embeddings=True)

# 编码查询（添加 instruction 提升检索效果）
query = "什么是检索增强生成？"
query_embedding = model.encode(
    [f"为这个句子生成表示以用于检索相关文章：{query}"],
    normalize_embeddings=True
)

# 计算相似度
similarities = np.dot(doc_embeddings, query_embedding.T)
print(f"最相似文档：{documents[np.argmax(similarities)]}")
```

## MTEB 排行榜

MTEB（Massive Text Embedding Benchmark）是业界最权威的 Embedding 评估基准：

**主要评估维度**：
- **Classification**：文本分类任务
- **Clustering**：聚类任务
- **PairClassification**：文本对匹配
- **Retrieval**：检索任务（RAG 最相关）
- **STS**：语义相似度
- **Summarization**：摘要质量
- **BitextMining**：双语翻译

**查询方式**：访问 huggingface.co/spaces/mteb/leaderboard 查看最新排名。

**选型建议**：
- Retrieval 维度得分高的模型最适合 RAG
- 中文场景关注 C-MTEB（Chinese MTEB）排名
- 不要只看综合分数，要关注与自己场景相关的维度

## Embedding 维度选择

维度选择影响存储空间、检索速度和精度：

| 维度 | 存储（每百万向量） | 适用场景 |
|------|------------------|---------|
| 384 | ~1.5GB | 资源受限、高吞吐 |
| 512 | ~2GB | 轻量级应用 |
| 768 | ~3GB | 平衡选择 |
| 1024 | ~4GB | 高精度需求 |
| 1536 | ~6GB | OpenAI 默认 |
| 3072 | ~12GB | 最高精度 |

维度越高，表达能力越强，但存储和计算成本也越高。实践中 512-1024 维是较好的平衡点。

## 选型决策流程

```
1. 数据量 < 1万 → OpenAI text-embedding-3-small（简单快速）
2. 数据量 1万-100万，中文为主 → bge-small-zh（免费、快速）
3. 数据量 100万+，需要 GPU → bge-large-zh 或 bge-m3
4. 多语言混合 → bge-m3 或 Jina v3
5. 国内生产环境，不想管 GPU → DashScope text-embedding-v2
6. 已有 OpenAI API key → text-embedding-3-small
```

## 最佳实践

1. **统一模型**：文档编码和查询编码必须使用同一个模型
2. **归一化**：始终设置 `normalize_embeddings=True`，使用余弦相似度
3. **批处理**：大量文档编码时使用 batch 处理，提高吞吐
4. **instruction 提示**：BGE 模型建议在查询前加 instruction 前缀
5. **监控漂移**：模型更新后重新编码所有文档，避免新旧向量不兼容
