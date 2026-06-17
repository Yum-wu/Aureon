# 转化率优化：从漏斗分析到实验设计

## 转化漏斗

转化漏斗描述用户从访问到完成目标行为的路径：

```
访问 → 注册 → 激活 → 付费 → 增购
 100%   30%    15%    5%    2%
```

每一步都有流失，优化转化率就是减少每一步的流失。

## 漏斗分析方法

### 漏斗构建

```python
import pandas as pd

def analyze_funnel(events: pd.DataFrame, steps: list[str]) -> pd.DataFrame:
    """分析转化漏斗"""
    funnel_data = []

    for i, step in enumerate(steps):
        if i == 0:
            users_at_step = events[events["event"] == step]["user_id"].nunique()
        else:
            # 必须先完成前一步
            prev_users = set(events[events["event"] == steps[i-1]]["user_id"])
            current_users = set(events[events["event"] == step]["user_id"])
            users_at_step = len(prev_users & current_users)

        funnel_data.append({
            "step": step,
            "users": users_at_step,
            "conversion_rate": users_at_step / funnel_data[0]["users"] if funnel_data else 1.0,
            "drop_off_rate": 1 - (users_at_step / funnel_data[i-1]["users"]) if i > 0 and funnel_data[i-1]["users"] > 0 else 0,
        })

    return pd.DataFrame(funnel_data)
```

### 流失分析

```python
def analyze_drop_off(funnel: pd.DataFrame) -> dict:
    """分析最大流失点"""
    max_drop_step = funnel.loc[funnel["drop_off_rate"].idxmax()]

    return {
        "biggest_drop_step": max_drop_step["step"],
        "drop_off_rate": max_drop_step["drop_off_rate"],
        "users_lost": funnel.iloc[max_drop_step.name - 1]["users"] - max_drop_step["users"] if max_drop_step.name > 0 else 0,
        "recommendation": f"优先优化 {max_drop_step['step']} 步骤的转化率",
    }
```

## 实验设计

### A/B 测试框架

```python
class ConversionABTest:
    """转化率 A/B 测试"""

    def __init__(self, control_rate: float, treatment_rate: float, sample_size: int):
        self.control_rate = control_rate
        self.treatment_rate = treatment_rate
        self.sample_size = sample_size

    def calculate_significance(self) -> dict:
        """计算统计显著性"""
        from scipy.stats import chi2_contingency

        # 构建列联表
        control_converted = int(self.control_rate * self.sample_size)
        treatment_converted = int(self.treatment_rate * self.sample_size)

        table = [
            [control_converted, self.sample_size - control_converted],
            [treatment_converted, self.sample_size - treatment_converted],
        ]

        chi2, p_value, _, _ = chi2_contingency(table)

        return {
            "control_rate": self.control_rate,
            "treatment_rate": self.treatment_rate,
            "lift": (self.treatment_rate - self.control_rate) / self.control_rate,
            "p_value": p_value,
            "is_significant": p_value < 0.05,
        }
```

### 实验优先级

```python
def prioritize_experiments(ideas: list[dict]) -> list[dict]:
    """实验优先级排序（ICE 框架）"""
    for idea in ideas:
        # ICE = Impact × Confidence × Ease
        ice_score = idea["impact"] * idea["confidence"] * idea["ease"]
        idea["ice_score"] = ice_score

    return sorted(ideas, key=lambda x: x["ice_score"], reverse=True)

# 示例
ideas = [
    {"name": "简化注册流程", "impact": 8, "confidence": 7, "ease": 9},
    {"name": "添加社交登录", "impact": 6, "confidence": 8, "ease": 6},
    {"name": "优化定价页面", "impact": 7, "confidence": 5, "ease": 8},
]
prioritized = prioritize_experiments(ideas)
```

## 常见优化策略

1. **减少步骤**：合并注册步骤、一键登录
2. **降低认知负荷**：简化界面、减少选择
3. **增加紧迫感**：限时优惠、名额限制
4. **社会证明**：用户评价、使用数据
5. **消除风险**：免费试用、退款保证

## 关键事实

1. **转化漏斗的每一步都有流失**，优化转化率就是减少每一步的流失，最大流失点应优先优化
2. **A/B 测试使用卡方检验判断统计显著性**，P 值 <0.05 为显著，样本量不足会导致假阴性
3. **ICE 框架（Impact × Confidence × Ease）**用于实验优先级排序，高分实验优先执行
4. **减少步骤是最有效的转化优化策略**——每减少一个步骤，转化率通常提升 10-30%
5. **实验应持续运行至少 2 周**，避免周期性波动影响结果，且每组至少 1000 个样本
