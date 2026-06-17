# Embedding 漂移检测：模型更新后的数据一致性

## 什么是 Embedding 漂移

Embedding 漂移（Embedding Drift）是指当 Embedding 模型更新后，同一文本的向量表示发生变化，导致：

1. **检索质量下降**：新模型编码的查询与旧模型编码的文档不匹配
2. **排序混乱**：新旧文档的相似度分数不可比
3. **缓存失效**：语义缓存的向量与查询向量不在同一空间

### 漂移的来源

1. **模型版本更新**：从 bge-large-zh-v1.0 升级到 v1.5
2. **微调后部署**：领域微调改变了向量空间
3. **API 提供方更新**：OpenAI/DashScope 静默更新模型
4. **训练数据变化**：模型重新训练后向量空间偏移

## 漂移检测方法

### 方法一：向量距离监控

监控同一文本在新旧模型下的向量距离：

```python
import numpy as np

class EmbeddingDriftDetector:
    """Embedding 漂移检测器"""

    def __init__(self, reference_embeddings: dict[str, np.ndarray]):
        """初始化参考嵌入

        Args:
            reference_embeddings: {text: old_embedding} 参考文本的旧嵌入
        """
        self.reference_embeddings = reference_embeddings
        self.reference_texts = list(reference_embeddings.keys())

    async def detect_drift(
        self,
        new_embedder,
        threshold: float = 0.05,
    ) -> dict:
        """检测漂移"""
        # 用新模型编码参考文本
        new_embeddings = {}
        for text in self.reference_texts:
            new_embeddings[text] = await new_embedder.aembed_query(text)

        # 计算新旧嵌入的余弦相似度
        similarities = []
        for text in self.reference_texts:
            old_emb = self.reference_embeddings[text]
            new_emb = new_embeddings[text]

            # 归一化
            old_emb = old_emb / np.linalg.norm(old_emb)
            new_emb = new_emb / np.linalg.norm(new_emb)

            sim = np.dot(old_emb, new_emb)
            similarities.append(sim)

        mean_sim = np.mean(similarities)
        min_sim = np.min(similarities)

        # 漂移判断
        drift_detected = mean_sim < (1 - threshold)

        return {
            "mean_similarity": mean_sim,
            "min_similarity": min_sim,
            "drift_detected": drift_detected,
            "drift_severity": "high" if mean_sim < 0.9 else "medium" if mean_sim < 0.95 else "low",
            "n_reference_texts": len(self.reference_texts),
        }
```

### 方法二：检索一致性检测

监控同一查询在新旧模型下的检索结果一致性：

```python
async def retrieval_consistency_check(
    test_queries: list[str],
    old_vectorstore,
    new_embedder,
    k: int = 10,
    consistency_threshold: float = 0.7,
) -> dict:
    """检索一致性检测"""
    consistency_scores = []

    for query in test_queries:
        # 旧模型检索结果
        old_results = await old_vectorstore.asimilarity_search(query, k=k)
        old_ids = [doc.metadata.get("id") for doc in old_results]

        # 新模型检索（临时索引）
        new_results = await search_with_new_model(query, new_embedder, k=k)
        new_ids = [doc.metadata.get("id") for doc in new_results]

        # 计算 Jaccard 相似度
        intersection = len(set(old_ids) & set(new_ids))
        union = len(set(old_ids) | set(new_ids))
        jaccard = intersection / union if union > 0 else 0

        consistency_scores.append(jaccard)

    mean_consistency = np.mean(consistency_scores)

    return {
        "mean_consistency": mean_consistency,
        "consistency_below_threshold": mean_consistency < consistency_threshold,
        "needs_reindex": mean_consistency < consistency_threshold,
    }
```

### 方法三：下游任务性能监控

监控 RAG 系统的端到端性能指标：

```python
class RAGPerformanceMonitor:
    """RAG 性能监控器"""

    def __init__(self, baseline_metrics: dict):
        self.baseline = baseline_metrics

    async def check_performance(self, current_metrics: dict) -> dict:
        """检查性能是否下降"""
        alerts = []

        for metric, baseline_value in self.baseline.items():
            current_value = current_metrics.get(metric)
            if current_value is None:
                continue

            change = (current_value - baseline_value) / baseline_value

            # 性能下降超过 5% 告警
            if change < -0.05:
                alerts.append({
                    "metric": metric,
                    "baseline": baseline_value,
                    "current": current_value,
                    "change_pct": change * 100,
                    "severity": "high" if change < -0.1 else "medium",
                })

        return {
            "alerts": alerts,
            "has_drift": len(alerts) > 0,
            "metrics_compared": len(self.baseline),
        }
```

## 漂移应对策略

### 策略一：全量重索引

最安全但最耗时的方案：

```python
async def full_reindex(
    old_vectorstore,
    new_embedder,
    document_store,
    batch_size: int = 100,
) -> dict:
    """全量重索引"""
    total_docs = await document_store.count()
    processed = 0
    start_time = time.time()

    # 分批处理
    for offset in range(0, total_docs, batch_size):
        docs = await document_store.get_batch(offset, batch_size)

        # 用新模型编码
        texts = [doc.content for doc in docs]
        embeddings = await new_embedder.aembed_documents(texts)

        # 更新向量
        for doc, embedding in zip(docs, embeddings):
            await old_vectorstore.aupdate_embedding(doc.id, embedding)

        processed += len(docs)

    elapsed = time.time() - start_time
    return {
        "total_docs": total_docs,
        "processed": processed,
        "elapsed_seconds": elapsed,
        "docs_per_second": processed / elapsed,
    }
```

### 策略二：双索引过渡

新旧索引并行运行，逐步切换流量：

```python
class DualIndexRetriever:
    """双索引过渡检索器"""

    def __init__(self, old_vectorstore, new_vectorstore):
        self.old_vectorstore = old_vectorstore
        self.new_vectorstore = new_vectorstore
        self.traffic_ratio = 0.0  # 新索引流量比例

    async def retrieve(self, query: str, k: int = 10) -> list:
        """检索：按流量比例分配到新旧索引"""
        import random

        if random.random() < self.traffic_ratio:
            # 新索引
            return await self.new_vectorstore.asimilarity_search(query, k=k)
        else:
            # 旧索引
            return await self.old_vectorstore.asimilarity_search(query, k=k)

    def increase_traffic(self, step: float = 0.1):
        """逐步增加新索引流量"""
        self.traffic_ratio = min(1.0, self.traffic_ratio + step)
```

### 策略三：向量空间对齐

通过线性变换将旧向量映射到新空间：

```python
def align_vector_spaces(
    old_embeddings: np.ndarray,
    new_embeddings: np.ndarray,
) -> np.ndarray:
    """学习旧空间到新空间的线性变换

    使用 Procrustes 对齐
    """
    # 中心化
    old_centered = old_embeddings - old_embeddings.mean(axis=0)
    new_centered = new_embeddings - new_embeddings.mean(axis=0)

    # SVD 分解
    U, _, Vt = np.linalg.svd(new_centered.T @ old_centered)

    # 旋转矩阵
    R = U @ Vt

    return R


def transform_old_embeddings(
    old_embeddings: np.ndarray,
    rotation_matrix: np.ndarray,
) -> np.ndarray:
    """将旧嵌入变换到新空间"""
    return old_embeddings @ rotation_matrix.T
```

## 自动化漂移管理

```python
class EmbeddingDriftManager:
    """Embedding 漂移自动化管理"""

    async def run_drift_check(self):
        """定期漂移检查"""
        # 1. 检测漂移
        drift_report = await self.detector.detect_drift(self.new_embedder)

        if not drift_report["drift_detected"]:
            return {"status": "no_drift"}

        # 2. 评估影响
        consistency = await retrieval_consistency_check(
            self.test_queries, self.old_vectorstore, self.new_embedder
        )

        # 3. 决定应对策略
        if drift_report["drift_severity"] == "high":
            # 严重漂移：全量重索引
            return await self.full_reindex()
        elif drift_report["drift_severity"] == "medium":
            # 中等漂移：双索引过渡
            return await self.dual_index_transition()
        else:
            # 轻微漂移：监控即可
            return {"status": "monitoring", "report": drift_report}
```

## 关键事实

1. **Embedding 漂移是模型更新后同一文本向量表示发生变化的现象**，会导致检索质量下降、排序混乱和缓存失效
2. **向量距离监控**是最直接的检测方法，计算同一文本在新旧模型下的余弦相似度，低于 0.95 表示存在漂移
3. **检索一致性检测**通过 Jaccard 相似度比较新旧模型的检索结果，一致性低于 70% 需要重索引
4. **全量重索引是最安全但最耗时的方案**，百万级文档重索引通常需要数小时
5. **Procrustes 对齐**通过线性变换将旧向量映射到新空间，可以避免全量重索引，但对非线性漂移效果有限
