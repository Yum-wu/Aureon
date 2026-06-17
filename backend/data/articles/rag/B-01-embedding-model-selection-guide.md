# Embedding 模型选型指南：BGE vs OpenAI vs Cohere

## Embedding 模型的重要性

Embedding 模型是 RAG 系统的基础设施，直接影响检索质量。选择合适的 Embedding 模型需要综合考虑：**检索精度、推理延迟、成本、多语言支持、部署方式**等因素。

## 主流 Embedding 模型对比

### 模型概览

| 模型 | 提供方 | 维度 | 语言 | 部署方式 | 价格 |
|------|--------|------|------|---------|------|
| bge-large-zh-v1.5 | BAAI | 1024 | 中文优先 | 本地/API | 免费 |
| bge-m3 | BAAI | 1024 | 多语言 | 本地/API | 免费 |
| text-embedding-3-large | OpenAI | 3072 | 多语言 | API | $0.13/1M tokens |
| text-embedding-3-small | OpenAI | 1536 | 多语言 | API | $0.02/1M tokens |
| embed-multilingual-v3 | Cohere | 1024 | 多语言 | API | $0.10/1K calls |
| gte-large-zh | Alibaba | 1024 | 中文 | API | ¥0.0007/1K tokens |
| bce-embedding-base | NetEase | 768 | 中英 | 本地 | 免费 |

### C-MTEB 排行榜（中文检索）

C-MTEB（Chinese Massive Text Embedding Benchmark）是中文 Embedding 模型的权威评测：

| 排名 | 模型 | 检索平均分 |
|------|------|-----------|
| 1 | bge-large-zh-v1.5 | 70.5 |
| 2 | bge-m3 | 69.8 |
| 3 | gte-large-zh | 68.2 |
| 4 | text-embedding-3-large | 67.5 |
| 5 | bce-embedding-base | 66.8 |

## BGE 系列

### BGE-large-zh-v1.5

BAAI 发布的中文最优嵌入模型：

```python
from FlagEmbedding import FlagModel

model = FlagModel("BAAI/bge-large-zh-v1.5", use_fp16=True)

# 查询编码（需要添加指令前缀）
queries = ["什么是 RAG？"]
query_embeddings = model.encode_queries(queries)

# 文档编码
documents = ["RAG 是检索增强生成技术..."]
doc_embeddings = model.encode(documents)
```

**优势**：
- 中文检索 C-MTEB 第一
- 支持本地部署，无 API 调用成本
- 1024 维，与 Qdrant 等向量库兼容
- 指令增强设计，检索效果好

**局限**：
- 模型较大（1.3GB），需要 GPU 或高性能 CPU
- 多语言支持不如 bge-m3

### BGE-M3

多功能嵌入模型，同时支持 dense、sparse、ColBERT 三种向量：

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

output = model.encode(
    ["什么是 RAG？"],
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=True,
)

dense_vec = output["dense_vecs"]       # [1024]
sparse_vec = output["lexical_weights"] # {token_id: weight}
colbert_vec = output["colbert_vecs"]   # [seq_len, 1024]
```

**优势**：
- 一次推理输出三种向量
- 多语言支持（100+ 语言）
- 适合 Hybrid Search 场景

**局限**：
- 模型更大（2.2GB）
- 推理速度比 bge-large-zh 慢约 30%

## OpenAI Embedding

### text-embedding-3-large / small

OpenAI 的最新嵌入模型，支持可变维度：

```python
from openai import AsyncOpenAI

client = AsyncOpenAI()

async def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    response = await client.embeddings.create(
        input=text,
        model=model,
        dimensions=1024,  # 可选：降维到 1024
    )
    return response.data[0].embedding
```

**优势**：
- API 调用简单，无需本地部署
- 支持可变维度（通过 Matryoshka 表示学习）
- 多语言支持好

**局限**：
- API 调用成本
- 数据隐私（文本发送到 OpenAI 服务器）
- 延迟受网络影响（200-500ms）
- 中文检索效果不如 BGE

## Cohere Embed

### embed-multilingual-v3

Cohere 的多语言嵌入模型：

```python
import cohere

co = cohere.AsyncClient("YOUR_API_KEY")

async def get_cohere_embedding(texts: list[str]) -> list[list[float]]:
    response = await co.embed(
        texts=texts,
        model="embed-multilingual-v3",
        input_type="search_query",  # 或 "search_document"
    )
    return response.embeddings
```

**优势**：
- input_type 参数区分查询和文档编码
- 多语言支持优秀
- 搜索场景优化

**局限**：
- API 调用成本较高
- 中文效果不如 BGE
- 维度固定 1024

## 选型决策树

```
是否需要本地部署？
├── 是 → 中文为主？
│   ├── 是 → bge-large-zh-v1.5（中文最优）
│   └── 否 → bge-m3（多语言 + 多功能）
└── 否 → 预算敏感？
    ├── 是 → text-embedding-3-small（$0.02/1M tokens）
    └── 否 → 需要最高精度？
        ├── 是 → text-embedding-3-large（3072 维）
        └── 否 → embed-multilingual-v3（搜索优化）
```

## 混合部署策略

在 Aureon 中，采用本地 + API 混合部署：

```python
class EmbeddingService:
    """Embedding 服务：本地优先 + API 降级"""

    def __init__(self):
        self.local_model = FlagModel("BAAI/bge-large-zh-v1.5", use_fp16=True)
        self.fallback_chain = [
            self._dashscope_embed,
            self._siliconflow_embed,
            self._zhipu_embed,
        ]

    async def embed(self, text: str) -> list[float]:
        """嵌入文本，本地优先，API 降级"""
        try:
            # 本地模型
            return self.local_model.encode([text])[0].tolist()
        except Exception:
            # 逐级降级
            for fallback in self.fallback_chain:
                try:
                    return await fallback(text)
                except Exception:
                    continue
            raise RuntimeError("所有 Embedding 服务不可用")
```

## 性能对比（Aureon 实测）

| 模型 | 编码延迟（单条） | 吞吐量 | Recall@5 | 月成本 |
|------|----------------|--------|----------|--------|
| bge-large-zh（本地） | 15ms | 200/s | 92.4% | ¥0 |
| bge-m3（本地） | 22ms | 130/s | 91.8% | ¥0 |
| text-embedding-3-small | 250ms | 50/s | 87.5% | ¥200 |
| gte-large-zh（DashScope） | 180ms | 80/s | 90.2% | ¥50 |

## 关键事实

1. **BGE-large-zh-v1.5 在中文检索 C-MTEB 排行榜排名第一**，是中文 RAG 系统的首选本地部署模型
2. **BGE-M3 同时输出 dense + sparse + ColBERT 三种向量**，一次推理获得三种检索能力，适合 Hybrid Search
3. **OpenAI text-embedding-3 支持可变维度**，通过 Matryoshka 表示学习可以在 1536/3072 维之间选择，降低存储成本
4. **Cohere Embed 的 input_type 参数**区分 search_query 和 search_document，为搜索场景优化编码策略
5. **混合部署策略（本地优先 + API 降级）**是生产环境的最佳实践，Aureon 的 Fallback Chain 为：本地 BGE → DashScope → SiliconFlow → Zhipu
