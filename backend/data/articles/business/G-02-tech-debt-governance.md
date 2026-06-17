# 敏捷开发中的技术债务治理

## 技术债务的定义

技术债务（Technical Debt）是 Ward Cunningham 提出的比喻，描述为了短期交付速度而牺牲代码质量的后果。就像金融债务一样，技术债务需要"利息"——维护成本随时间增加。

## 技术债务分类

| 类型 | 来源 | 示例 |
|------|------|------|
| 有意债务 | 刻意走捷径 | MVP 阶段硬编码配置 |
| 无意债务 | 经验不足 | 不合理的设计模式 |
| 环境债务 | 外部变化 | 依赖库过时 |
| 增长债务 | 规模变化 | 单体架构无法扩展 |

## 债务量化

```python
class TechDebtTracker:
    """技术债务追踪器"""

    def __init__(self):
        self.debt_items = []

    def add_debt(self, item: dict):
        """记录技术债务"""
        self.debt_items.append({
            "id": len(self.debt_items) + 1,
            "description": item["description"],
            "area": item["area"],
            "severity": item["severity"],  # high/medium/low
            "interest_rate": item["interest_rate"],  # 维护成本增速
            "effort_to_fix": item["effort_to_fix"],  # 修复所需人天
            "created_at": datetime.now(),
        })

    def prioritize(self) -> list[dict]:
        """按 ROI 排序：高利息 + 低修复成本优先"""
        for item in self.debt_items:
            item["roi"] = item["interest_rate"] / item["effort_to_fix"]

        return sorted(self.debt_items, key=lambda x: x["roi"], reverse=True)

    def debt_ratio(self, total_sprint_capacity: int) -> float:
        """计算债务占 Sprint 容量的比例"""
        total_effort = sum(item["effort_to_fix"] for item in self.debt_items)
        return total_effort / total_sprint_capacity
```

## 治理策略

### 策略一：20% 时间规则

每个 Sprint 预留 20% 容量处理技术债务：

```
Sprint 容量：50 人天
├── 新功能：40 人天（80%）
└── 技术债务：10 人天（20%）
```

### 策略二：童子军原则

"离开营地时比到达时更干净"——每次修改代码时顺便改善周边代码。

### 策略三：债务可视化

将技术债务记录在 Backlog 中，与功能需求一起排优先级。

### 策略四：定期重构 Sprint

每 4-6 个功能 Sprint 后安排 1 个重构 Sprint。

## 关键事实

1. **技术债务是 Ward Cunningham 提出的比喻**，描述为短期速度牺牲质量的后果，需要"利息"维护成本
2. **技术债务分为四类**：有意债务（刻意走捷径）、无意债务（经验不足）、环境债务（外部变化）、增长债务（规模变化）
3. **20% 时间规则**是技术债务治理的标准做法——每个 Sprint 预留 20% 容量处理债务
4. **童子军原则**要求每次修改代码时顺便改善周边代码，防止债务持续累积
5. **技术债务应可视化并量化**，记录在 Backlog 中按 ROI（利息率/修复成本）排序优先处理
