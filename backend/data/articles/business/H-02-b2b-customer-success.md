# B2B 客户成功管理框架

## 客户成功的定义

客户成功（Customer Success）是主动帮助客户实现其业务目标，从而驱动续费和增购。与客户支持（被动响应问题）不同，客户成功是**主动的、预防性的**。

## 客户健康度模型

### 健康度评分

```python
class CustomerHealthScore:
    """客户健康度评分"""

    def calculate(self, customer: dict) -> dict:
        """计算客户健康度"""
        score = 0
        signals = []

        # 产品使用（40%）
        usage_score = self._usage_score(customer)
        score += usage_score * 0.4

        # 互动参与（20%）
        engagement_score = self._engagement_score(customer)
        score += engagement_score * 0.2

        # 业务成果（20%）
        outcome_score = self._outcome_score(customer)
        score += outcome_score * 0.2

        # 关系强度（20%）
        relationship_score = self._relationship_score(customer)
        score += relationship_score * 0.2

        return {
            "health_score": score,
            "health_level": "healthy" if score >= 70 else "at_risk" if score >= 40 else "critical",
            "signals": signals,
        }

    def _usage_score(self, customer: dict) -> float:
        """产品使用评分"""
        dau_mau = customer.get("dau_mau_ratio", 0)
        feature_adoption = customer.get("feature_adoption_rate", 0)
        return min((dau_mau * 100 + feature_adoption) / 2, 100)
```

## 客户分层

| 层级 | ARR | CSM 配比 | 服务模式 |
|------|-----|---------|---------|
| 战略客户 | >¥500K | 1:5 | 高触达，定期业务评审 |
| 成长客户 | ¥100-500K | 1:20 | 中触达，季度检查 |
| SMB | <¥100K | 1:50+ | 低触达，自动化 + 社区 |

## 关键时刻

### Onboarding（0-90天）

确保客户快速实现价值，到达 Aha Moment。

### 首次续费（90-365天）

证明持续价值，确保续费。

### 增购（365天+）

识别增购机会，扩展使用场景。

## 关键事实

1. **客户成功是主动的、预防性的**，与客户支持（被动响应）不同，目标是帮助客户实现业务目标
2. **客户健康度评分**综合产品使用（40%）、互动参与（20%）、业务成果（20%）和关系强度（20%）
3. **客户分层**：战略客户（1:5 CSM 配比）、成长客户（1:20）、SMB（1:50+，自动化为主）
4. **三个关键时刻**：Onboarding（0-90天，快速到价值）、首次续费（90-365天，证明持续价值）、增购（365天+，扩展场景）
5. **净留存率（NRR）>100%**是客户成功的黄金标准——现有客户增购超过流失
