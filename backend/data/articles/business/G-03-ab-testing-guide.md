# 数据驱动决策：A/B 测试设计指南

## A/B 测试基础

A/B 测试是数据驱动决策的核心工具，通过随机分组对比两个方案的效果差异，消除主观偏见。

## 测试设计流程

### 第一步：定义假设

```
假设格式：如果我们做 [改变]，那么 [指标] 会 [提升/降低] [幅度]，因为 [原因]

示例：如果我们简化注册流程（从3步减为1步），
那么注册转化率会提升20%，因为减少了用户流失点
```

### 第二步：确定样本量

```python
def sample_size_for_proportion(
    baseline: float,
    mde: float,  # 最小可检测效应
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    """计算比例类指标的样本量"""
    from scipy.stats import norm

    p1 = baseline
    p2 = baseline * (1 + mde)
    p_avg = (p1 + p2) / 2

    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)

    n = (
        (z_alpha * math.sqrt(2 * p_avg * (1 - p_avg)) +
         z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    ) / (p2 - p1) ** 2

    return math.ceil(n)
```

### 第三步：随机分组

```python
def assign_variant(user_id: str, test_name: str, traffic_split: float = 0.5) -> str:
    """一致性哈希分组"""
    hash_val = int(hashlib.md5(f"{test_name}:{user_id}".encode()).hexdigest(), 16)
    return "treatment" if (hash_val % 100) < (traffic_split * 100) else "control"
```

### 第四步：运行测试

测试应运行足够长的时间（至少 2 周），覆盖完整的用户行为周期。

### 第五步：分析结果

```python
from scipy.stats import chi2_contingency

def analyze_ab_test(
    control_converted: int, control_total: int,
    treatment_converted: int, treatment_total: int,
) -> dict:
    """分析 A/B 测试结果"""
    table = [
        [control_converted, control_total - control_converted],
        [treatment_converted, treatment_total - treatment_converted],
    ]

    chi2, p_value, _, _ = chi2_contingency(table, correction=False)

    control_rate = control_converted / control_total
    treatment_rate = treatment_converted / treatment_total
    lift = (treatment_rate - control_rate) / control_rate

    return {
        "control_rate": control_rate,
        "treatment_rate": treatment_rate,
        "lift": lift,
        "p_value": p_value,
        "is_significant": p_value < 0.05,
        "recommendation": "上线实验组" if p_value < 0.05 and lift > 0 else "保持对照组",
    }
```

## 常见错误

1. **过早停止**：看到初步显著就停止，可能假阳性
2. **多重比较**：同时测试多个指标，需 Bonferroni 校正
3. **新奇效应**：新功能初期效果可能偏高
4. **样本量不足**：统计功效不够，无法检测真实差异
5. **选择偏见**：分组不随机，存在系统性差异

## 关键事实

1. **A/B 测试的五个步骤**：定义假设 → 确定样本量 → 随机分组 → 运行测试 → 分析结果
2. **样本量取决于基线率、最小可检测效应和统计功效**，基线转化率 5%、期望提升 20% 时需要约 15000 样本/组
3. **卡方检验是比例类指标的标准分析方法**，P 值 <0.05 为统计显著
4. **测试应运行至少 2 周**，覆盖完整的用户行为周期，避免周期性波动影响
5. **过早停止是最常见的 A/B 测试错误**——看到初步显著就停止可能导致假阳性
