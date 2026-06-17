# 从 0 到 1 的产品路线图规划

## 路线图的目的

产品路线图是战略沟通工具，不是项目计划。它回答"为什么做"和"什么时候做"，而非"怎么做"。

## 路线图框架

### Now-Next-Later

最简洁的路线图格式：

```
Now（当前季度）：正在做的
  ├── RAG Hybrid Search 优化
  └── 用户反馈系统

Next（下季度）：计划做的
  ├── 多模态 RAG
  └── 企业 SSO

Later（未来）：可能做的
  ├── Agentic RAG
  └── 多语言支持
```

### 主题驱动

按主题而非功能列表组织路线图：

```python
class ThemeBasedRoadmap:
    """主题驱动路线图"""

    def __init__(self):
        self.themes = []

    def add_theme(self, theme: dict):
        """添加主题"""
        self.themes.append({
            "name": theme["name"],
            "objective": theme["objective"],
            "success_metrics": theme["success_metrics"],
            "initiatives": theme["initiatives"],
            "quarter": theme["quarter"],
        })

# 示例
roadmap = ThemeBasedRoadmap()
roadmap.add_theme({
    "name": "检索质量提升",
    "objective": "将 Recall@5 提升到 95%",
    "success_metrics": ["Recall@5 >= 95%", "MRR >= 0.90"],
    "initiatives": ["BGE-M3 Hybrid Search", "Contextual Retrieval", "Rerank 优化"],
    "quarter": "Q3 2026",
})
```

## 优先级排序

### RICE 框架

```python
def rice_score(initiative: dict) -> float:
    """RICE 优先级评分"""
    reach = initiative["reach"]          # 影响用户数
    impact = initiative["impact"]        # 影响程度（0.25-3）
    confidence = initiative["confidence"] # 信心度（0-1）
    effort = initiative["effort"]        # 所需人月

    return (reach * impact * confidence) / effort
```

### 优先级矩阵

```
         高影响
           |
    快赢    |    大项目
           |
───────────┼─────────── 低努力 → 高努力
           |
    填充    |    避免
           |
         低影响
```

## 路线图沟通

### 对不同受众

| 受众 | 展示内容 | 格式 |
|------|---------|------|
| 高管 | 战略方向 + 关键里程碑 | 季度时间线 |
| 销售 | 即将发布的功能 | 功能列表 + 时间 |
| 工程 | 技术方案 + 依赖关系 | Epic + Story |
| 客户 | 产品方向 + 发布计划 | Now-Next-Later |

## 关键事实

1. **产品路线图是战略沟通工具**，回答"为什么做"和"什么时候做"，而非"怎么做"
2. **Now-Next-Later 是最简洁的路线图格式**，避免过度承诺具体时间点
3. **主题驱动路线图**按业务目标组织，而非功能列表，每个主题有明确的成功指标
4. **RICE 框架（Reach × Impact × Confidence / Effort）**是优先级排序的标准方法
5. **路线图应对不同受众展示不同内容**：高管看战略方向，工程看技术方案，客户看发布计划
