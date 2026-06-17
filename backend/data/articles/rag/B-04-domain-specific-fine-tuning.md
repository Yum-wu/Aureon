# 领域微调 Embedding：何时需要与如何做

## 通用 Embedding 的局限

通用 Embedding 模型（如 BGE、OpenAI）在通用场景表现优异，但在特定领域可能存在不足：

1. **术语不匹配**：医疗领域的"心梗"vs"心肌梗死"，通用模型可能无法识别等价关系
2. **语义偏差**：金融领域的"牛市"（市场上涨）vs 日常语境的"牛市"（动物），通用模型可能混淆
3. **细粒度区分不足**：法律领域"合同解除"vs"合同终止"，语义差异微妙但法律后果不同
4. **领域知识缺失**：通用模型的训练数据可能不包含特定领域的专业文本

## 何时需要领域微调

### 评估指标

通过以下指标判断是否需要微调：

```python
async def evaluate_domain_gap(
    domain_queries: list[str],
    domain_docs: list[str],
    general_embedder,
    domain_expert_labels: list[list[int]],
) -> dict:
    """评估通用模型在领域数据上的性能差距"""
    # 通用模型检索
    query_embeddings = [await general_embedder.aembed_query(q) for q in domain_queries]
    doc_embeddings = [await general_embedder.aembed_query(d) for d in domain_docs]

    # 计算 Recall@5
    recalls = []
    for i, query_emb in enumerate(query_embeddings):
        similarities = [
            cosine_similarity(query_emb, doc_emb)
            for doc_emb in doc_embeddings
        ]
        top_k_indices = sorted(range(len(similarities)), key=lambda j: similarities[j], reverse=True)[:5]
        hit = any(j in domain_expert_labels[i] for j in top_k_indices)
        recalls.append(hit)

    recall_at_5 = sum(recalls) / len(recalls)

    return {
        "recall_at_5": recall_at_5,
        "needs_finetuning": recall_at_5 < 0.85,  # 低于 85% 建议微调
        "gap_severity": "high" if recall_at_5 < 0.7 else "medium" if recall_at_5 < 0.85 else "low",
    }
```

### 决策标准

| Recall@5 | 建议 | 理由 |
|----------|------|------|
| > 90% | 不需要微调 | 通用模型足够好 |
| 80-90% | 考虑 Prompt 增强 | 低成本改进 |
| 70-80% | 建议微调 | 领域差距明显 |
| < 70% | 必须微调 | 通用模型不可用 |

## 微调方法

### 方法一：对比学习微调

使用领域内的查询-文档对进行对比学习：

```python
from sentence_transformers import SentenceTransformer, losses, InputExample
from torch.utils.data import DataLoader

# 准备训练数据
train_examples = []
for query, positive_doc, negative_doc in domain_pairs:
    train_examples.append(InputExample(texts=[query, positive_doc, negative_doc]))

# 加载预训练模型
model = SentenceTransformer("BAAI/bge-large-zh-v1.5")

# Multiple Negatives Ranking Loss
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=32)
train_loss = losses.MultipleNegativesRankingLoss(model)

# 微调
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=100,
    output_path="./domain-finetuned-model",
)
```

### 方法二：领域自适应预训练（DAPT）

先在领域语料上继续预训练，再进行对比学习微调：

```python
from transformers import AutoModelForMaskedLM, AutoTokenizer, DataCollatorForLanguageModeling

# 阶段 1：领域自适应预训练
model = AutoModelForMaskedLM.from_pretrained("BAAI/bge-large-zh-v1.5")
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-zh-v1.5")

# 准备领域语料
domain_corpus = load_domain_corpus()  # 领域文本数据集

# MLM 预训练
data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=True, mlm_probability=0.15)

from transformers import Trainer, TrainingArguments

training_args = TrainingArguments(
    output_dir="./dapt-model",
    num_train_epochs=5,
    per_device_train_batch_size=16,
    learning_rate=2e-5,
    weight_decay=0.01,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=domain_corpus,
    data_collator=data_collator,
)

trainer.train()

# 阶段 2：对比学习微调（同方法一）
```

### 方法三：合成数据微调

当缺乏标注数据时，用 LLM 生成合成训练数据：

```python
async def generate_synthetic_training_data(
    domain_docs: list[str],
    llm,
    n_queries_per_doc: int = 3,
) -> list[tuple[str, str]]:
    """用 LLM 生成合成查询-文档对"""
    prompt = """根据以下文档内容，生成 {n} 个可能的用户查询。
查询应该涵盖不同角度和表述方式。

文档：{doc}

查询："""

    pairs = []
    for doc in domain_docs:
        response = await llm.ainvoke(prompt.format(n=n_queries_per_doc, doc=doc))
        queries = [q.strip() for q in response.split("\n") if q.strip()]
        for query in queries:
            pairs.append((query, doc))

    return pairs
```

## 微调数据准备

### 数据质量要求

1. **查询多样性**：同一文档的查询应涵盖不同表述方式
2. **负例质量**：Hard Negative 比随机负例更有效
3. **数据量**：至少 1000 对查询-文档对，推荐 5000+ 对

### Hard Negative Mining

```python
async def mine_hard_negatives(
    queries: list[str],
    positive_docs: list[str],
    embedder,
    vectorstore,
    n_negatives: int = 5,
) -> list[tuple[str, str, list[str]]]:
    """挖掘 Hard Negative"""
    training_data = []

    for query, positive in zip(queries, positive_docs):
        # 检索相似但不相关的文档作为 Hard Negative
        results = await vectorstore.asimilarity_search(query, k=n_negatives + 1)

        negatives = []
        for doc in results:
            # 排除正例文档
            if doc.page_content != positive and doc.page_content not in negatives:
                negatives.append(doc.page_content)

        training_data.append((query, positive, negatives[:n_negatives]))

    return training_data
```

## 微调效果评估

### 评估方法

```python
async def evaluate_finetuned_model(
    model,
    test_queries: list[str],
    test_docs: list[str],
    ground_truth: list[list[int]],
    k: int = 5,
) -> dict:
    """评估微调后的模型"""
    # 编码
    query_embeddings = model.encode(test_queries)
    doc_embeddings = model.encode(test_docs)

    # 计算 Recall@K
    recalls = []
    for i, query_emb in enumerate(query_embeddings):
        similarities = np.dot(doc_embeddings, query_emb)
        top_k = np.argsort(similarities)[-k:][::-1]
        hit = any(j in ground_truth[i] for j in top_k)
        recalls.append(hit)

    recall_at_k = sum(recalls) / len(recalls)

    # 计算 MRR
    mrr_sum = 0
    for i, query_emb in enumerate(query_embeddings):
        similarities = np.dot(doc_embeddings, query_emb)
        ranking = np.argsort(similarities)[::-1]
        for rank, j in enumerate(ranking, 1):
            if j in ground_truth[i]:
                mrr_sum += 1 / rank
                break

    mrr = mrr_sum / len(test_queries)

    return {"recall_at_k": recall_at_k, "mrr": mrr}
```

### 典型提升效果

| 领域 | 通用模型 Recall@5 | 微调后 Recall@5 | 提升 |
|------|-------------------|-----------------|------|
| 医疗 | 78% | 91% | +13% |
| 金融 | 82% | 93% | +11% |
| 法律 | 75% | 89% | +14% |
| 电商 | 85% | 92% | +7% |

## 微调的注意事项

### 过拟合风险

```python
# 防止过拟合的策略
strategies = {
    "数据增强": "同义改写、回译、随机删除",
    "正则化": "Weight Decay、Dropout、Early Stopping",
    "学习率": "小学习率（1e-5 ~ 5e-5），Warmup",
    "数据量": "训练数据至少 1000 对，推荐 5000+",
    "评估": "保留 20% 数据作为验证集，监控验证集指标",
}
```

### 模型更新策略

```python
class EmbeddingModelManager:
    """Embedding 模型版本管理"""

    async def update_model(self, new_model_path: str):
        """安全更新模型"""
        # 1. 加载新模型
        new_model = self.load_model(new_model_path)

        # 2. 在测试集上评估
        evaluation = await self.evaluate(new_model, self.test_set)

        # 3. 对比旧模型
        old_evaluation = await self.evaluate(self.current_model, self.test_set)

        # 4. 确认提升
        if evaluation["recall_at_5"] > old_evaluation["recall_at_5"]:
            # 5. 重新编码所有文档
            await self.reindex_all_docs(new_model)
            self.current_model = new_model
        else:
            # 回滚
            pass
```

## 关键事实

1. **领域微调的决策标准**：通用模型 Recall@5 > 90% 不需要微调，80-90% 考虑 Prompt 增强，< 80% 建议微调
2. **对比学习微调是最常用的方法**，使用 Multiple Negatives Ranking Loss 在查询-文档对上训练，通常 3 个 epoch 即可
3. **Hard Negative Mining 是提升微调效果的关键**——用检索到但不相关的文档作为负例，比随机负例更有效
4. **合成数据微调**可以在缺乏标注数据时使用 LLM 生成训练数据，但质量不如人工标注
5. **微调后需要重新编码所有文档**，这是模型更新的主要成本，建议通过 A/B 测试验证效果后再全量更新
