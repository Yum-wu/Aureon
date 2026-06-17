# PMF 验证：如何确认产品市场匹配

## PMF 的定义

产品市场匹配（Product-Market Fit，PMF）是 Marc Andreessen 提出的概念：**产品满足了一个足够大的市场的需求**。PMF 不是二元的"有或没有"，而是一个光谱——从完全没匹配到完美匹配。

## PMF 的信号

### 定性信号

1. **用户主动推荐**：不请自来地推荐给朋友
2. **用户强烈反应**：如果产品消失，用户会非常沮丧
3. **口碑传播**：新用户主要来自现有用户推荐
4. **用户深度使用**：高频使用核心功能
5. **付费意愿**：用户愿意为产品付费

### 定量信号

1. **Sean Ellis 测试**：40%+ 用户表示"如果产品消失会非常失望"
2. **留存曲线拐点**：留存率在下降后趋于平稳
3. **自然增长率**：不依赖营销的自然增长 > 5%/月
4. **NPS > 50**：净推荐值超过 50
5. **付费转化率 > 5%**：免费用户转付费比例

## PMF 验证方法

### 方法一：Sean Ellis 测试

```python
SURVEY_QUESTIONS = [
    "如果明天无法再使用这个产品，你会：",
    "A. 非常失望",  # PMF 信号
    "B. 有点失望",
    "C. 不会失望",
]

def calculate_pmf_score(responses: list[str]) -> dict:
    """计算 PMF 分数"""
    very_disappointed = sum(1 for r in responses if r == "A")
    total = len(responses)

    pmf_score = very_disappointed / total if total > 0 else 0

    return {
        "pmf_score": pmf_score,
        "has_pmf": pmf_score >= 0.4,
        "sample_size": total,
        "very_disappointed_pct": pmf_score * 100,
    }
```

### 方法二：留存曲线分析

```python
def analyze_retention_curve(retention_data: list[float]) -> dict:
    """分析留存曲线是否出现拐点"""
    # 检查留存是否趋于稳定
    if len(retention_data) < 7:
        return {"has_inflection": False, "reason": "数据不足"}

    # 计算留存下降率
    declines = [retention_data[i] - retention_data[i+1] for i in range(len(retention_data)-1)]

    # 找拐点：下降率从大变小的位置
    inflection_point = None
    for i in range(1, len(declines)):
        if declines[i] < declines[i-1] * 0.5:  # 下降率减半
            inflection_point = i
            break

    return {
        "has_inflection": inflection_point is not None,
        "inflection_day": inflection_point,
        "stable_retention": retention_data[inflection_point] if inflection_point else None,
    }
```

### 方法三：用户行为分析

```python
def analyze_user_engagement(users: list[dict]) -> dict:
    """分析用户参与度"""
    dau = sum(1 for u in users if u["active_today"])
    mau = sum(1 for u in users if u["active_last_30d"])

    # DAU/MAU 比率（粘性）
    stickiness = dau / mau if mau > 0 else 0

    return {
        "dau_mau_ratio": stickiness,
        "is_healthy": stickiness > 0.2,  # >20% 为健康
        "dau": dau,
        "mau": mau,
    }
```

## PMF 之前的常见陷阱

1. **过早规模化**：PMF 之前大量投入营销，获客成本高但留存低
2. **目标市场过大**：试图服务所有人，结果没人满意
3. **忽视留存**：只看获客不看留存，增长是虚假的
4. **功能驱动**：不断加功能而非解决核心问题
5. **过早优化**：在找到 PMF 之前优化转化漏斗

## 关键事实

1. **PMF 由 Marc Andreessen 提出**，定义是"产品满足了一个足够大的市场的需求"
2. **Sean Ellis 测试是 PMF 验证的黄金标准**：40%+ 用户表示"如果产品消失会非常失望"即达到 PMF
3. **留存曲线拐点是 PMF 的关键定量信号**——留存率在下降后趋于稳定，说明核心用户群已形成
4. **DAU/MAU 比率（粘性）>20%** 是用户参与度健康的指标，也是 PMF 的辅助验证
5. **过早规模化是 PMF 之前最常见的陷阱**——在找到 PMF 之前大量投入营销，获客成本高但留存低
