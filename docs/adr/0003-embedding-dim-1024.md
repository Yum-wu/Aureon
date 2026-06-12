# ADR-0003: Embedding 维度统一 1024d

## 状态：已批准

## 上下文

当前 embedding 维度不一致：
- 本地 bge-large-zh-v1.5：1024d
- DashScope text-embedding-v4：默认 768d（支持 64-2048d）
- Zhipu embedding-3：支持 256-2048d
- SiliconFlow bge-large-zh-v1.5：1024d

维度不匹配导致：API 模式建索引后切本地模式（或反过来）搜索失败。

## 决策

统一为 1024d：
- DashScope text-embedding-v4 设置 `dimensions=1024`
- Zhipu embedding-3 设置 1024d
- SiliconFlow bge-large-zh-v1.5 / bge-m3 默认 1024d
- `settings.embedding_dim` 默认值改为 1024

## 依据

- 1024d 是中文+多语言场景的最佳平衡点（搜索结果确认）
- 所有 API 提供商都支持 1024d
- INT8 量化后内存差异可忽略（5000 chunks: 768d≈4MB vs 1024d≈5MB）
- 1024d 多语言质量比 768d 高 5-10%
- 与 BGE-M3 dense 输出维度一致，便于后续迁移

## 后果

- 消除维度不匹配风险
- 多语言检索质量提升
- 需要重建现有索引（768d → 1024d）
- API 调用成本略增（1024d vs 768d 差异极小）
