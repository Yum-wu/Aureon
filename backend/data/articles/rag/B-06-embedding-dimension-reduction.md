# Embedding 降维：PCA vs AutoEncoder vs MRL

## 降维的动机

Embedding 向量的维度直接影响存储成本和检索速度。1024 维向量每个文档占 4KB，百万级文档需要约 4GB。降维可以在保留大部分语义信息的前提下，显著降低存储和计算成本。

## PCA（主成分分析）

### 原理

PCA 通过正交变换将高维数据投影到方差最大的方向，保留主要信息：

```python
import numpy as np
from sklearn.decomposition import PCA

def pca_reduce(
    embeddings: np.ndarray,
    target_dim: int = 256,
) -> tuple[np.ndarray, PCA]:
    """PCA 降维

    Args:
        embeddings: [n_docs, original_dim] 原始嵌入
        target_dim: 目标维度

    Returns:
        reduced: 降维后的嵌入
        pca: PCA 模型（用于新数据的降维）
    """
    pca = PCA(n_components=target_dim)
    reduced = pca.fit_transform(embeddings)

    # 解释方差比
    explained_variance = pca.explained_variance_ratio_.sum()
    print(f"保留方差比: {explained_variance:.3f}")

    return reduced, pca


# 使用示例
original_embeddings = np.random.randn(10000, 1024)  # 10000 个 1024 维向量
reduced, pca_model = pca_reduce(original_embeddings, target_dim=256)

# 对新查询降维
query_embedding = np.random.randn(1, 1024)
reduced_query = pca_model.transform(query_embedding)
```

### PCA 的优劣

**优势**：
- 线性方法，计算快速
- 可解释性强（主成分对应方差最大的方向）
- 新数据降维只需矩阵乘法

**局限**：
- 只能捕捉线性关系
- 降维后需要重新构建索引
- 精度损失较大（256 维通常损失 5-10%）

## AutoEncoder

### 原理

AutoEncoder 通过编码器-解码器架构学习非线性降维：

```python
import torch
import torch.nn as nn

class EmbeddingAutoEncoder(nn.Module):
    """Embedding 降维 AutoEncoder"""

    def __init__(self, input_dim: int = 1024, latent_dim: int = 256):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 512),
            nn.ReLU(),
            nn.Linear(512, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 512),
            nn.ReLU(),
            nn.Linear(512, input_dim),
        )

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        return self.decoder(z)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        z = self.encode(x)
        x_reconstructed = self.decode(z)
        return z, x_reconstructed


# 训练
def train_autoencoder(
    embeddings: np.ndarray,
    input_dim: int = 1024,
    latent_dim: int = 256,
    epochs: int = 50,
    batch_size: int = 256,
    lr: float = 1e-3,
) -> EmbeddingAutoEncoder:
    """训练 AutoEncoder"""
    model = EmbeddingAutoEncoder(input_dim, latent_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    dataset = torch.FloatTensor(embeddings)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

    for epoch in range(epochs):
        total_loss = 0
        for batch in dataloader:
            optimizer.zero_grad()
            z, reconstructed = model(batch)
            loss = criterion(reconstructed, batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        if (epoch + 1) % 10 == 0:
            print(f"Epoch {epoch+1}, Loss: {total_loss/len(dataloader):.6f}")

    return model
```

### AutoEncoder 的优劣

**优势**：
- 可以捕捉非线性关系
- 降维效果通常优于 PCA
- 可以加入正则化约束（如 VAE）

**局限**：
- 需要训练，计算成本高
- 推理需要前向传播，比 PCA 慢
- 降维后需要重新构建索引

## MRL（Matryoshka 表示学习）

### 原理

MRL 训练模型使前 N 维就是有效的低维表示，无需额外的降维步骤：

```python
# MRL 降维：直接截断
full_embedding = mrl_model.encode("文本")  # 1024 维
reduced_256 = full_embedding[:256]          # 直接取前 256 维
reduced_512 = full_embedding[:512]          # 直接取前 512 维
```

### MRL vs PCA vs AutoEncoder 对比

| 维度 | PCA | AutoEncoder | MRL |
|------|-----|-------------|-----|
| 降维方式 | 线性投影 | 非线性编码 | 前缀截断 |
| 需要训练 | 是（fit） | 是（端到端） | 是（嵌入模型训练时） |
| 需要重建索引 | 是 | 是 | 否（多粒度索引） |
| 精度损失 | 5-10% | 3-7% | 2-5% |
| 推理速度 | 快（矩阵乘法） | 中（前向传播） | 快（截断） |
| 新数据处理 | 需 PCA transform | 需编码器推理 | 直接截断 |
| 灵活性 | 固定维度 | 固定维度 | 多粒度 |

### 精度对比（1024→256 维）

| 方法 | Recall@5 | MRR | 说明 |
|------|----------|-----|------|
| 原始 1024 维 | 92.4% | 0.888 | 基准 |
| PCA 256 维 | 84.2% | 0.795 | 损失 8.2% |
| AutoEncoder 256 维 | 86.5% | 0.818 | 损失 5.9% |
| MRL 256 维 | 87.2% | 0.825 | 损失 5.2% |

## 实践建议

### 场景选择

```
是否可以重新训练嵌入模型？
├── 是 → MRL（最优选择）
└── 否 → 已有训练数据？
    ├── 是 → AutoEncoder（非线性降维）
    └── 否 → PCA（快速降维）
```

### 组合策略

```python
async def adaptive_dimension_retrieve(
    query: str,
    embedder,  # MRL 模型
    vectorstores: dict[int, VectorStore],
    query_router,
    k: int = 10,
) -> list:
    """自适应维度检索"""
    route = await query_router.aroute(query)

    if route == "simple":
        # 简单查询：256 维快速检索
        dim = 256
    elif route == "medium":
        dim = 512
    else:
        dim = 1024

    full_embedding = await embedder.aembed_query(query)
    truncated = full_embedding[:dim]

    return await vectorstores[dim].asimilarity_search_by_vector(truncated, k=k)
```

## 关键事实

1. **PCA 通过正交变换保留方差最大的方向**，计算快速但只能捕捉线性关系，256 维通常损失 5-10% 精度
2. **AutoEncoder 通过编码器-解码器架构学习非线性降维**，精度优于 PCA（损失 3-7%），但需要训练和推理开销
3. **MRL（Matryoshka 表示学习）通过前缀截断实现降维**，无需额外步骤，精度损失最小（2-5%），是最优选择
4. **MRL 256 维的 Recall@5 为 87.2%**，比 PCA 256 维高 3%，比 AutoEncoder 256 维高 0.7%
5. **如果可以重新训练嵌入模型，MRL 是降维的最优方案**；否则 AutoEncoder 适合有训练数据的场景，PCA 适合快速降维
