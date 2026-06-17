# 流失预测：识别高风险用户信号

## 流失预测的重要性

客户流失是 SaaS 企业的最大威胁之一。获取一个新客户的成本是保留现有客户的 5-25 倍。提前识别高风险用户并主动干预，是降低流失率的关键。

## 流失信号分类

### 行为信号

1. **登录频率下降**：从每天登录变为每周登录
2. **核心功能使用减少**：关键功能使用次数下降
3. **支持工单增加**：频繁提交问题可能表示不满
4. **数据导出增加**：用户可能在准备迁移
5. **团队规模缩减**：减少席位是流失前兆

### 财务信号

1. **付款失败**：信用卡过期或余额不足
2. **降级计划**：从高级版降为基础版
3. **合同缩短**：从年付改为月付

### 互动信号

1. **NPS 评分低**：评分 < 7 的用户流失风险高
2. **取消反馈**：用户提交取消原因
3. **社交媒体负面评价**

## 流失预测模型

### 基于规则的预警

```python
class ChurnRiskScorer:
    """流失风险评分器"""

    def calculate_risk(self, user: dict) -> dict:
        """计算用户流失风险"""
        risk_score = 0
        risk_factors = []

        # 登录频率
        if user["days_since_last_login"] > 14:
            risk_score += 30
            risk_factors.append("超过14天未登录")

        # 核心功能使用
        if user["weekly_feature_usage"] < user["avg_weekly_usage"] * 0.3:
            risk_score += 25
            risk_factors.append("核心功能使用下降70%")

        # 支持工单
        if user["support_tickets_last_30d"] > 3:
            risk_score += 15
            risk_factors.append("30天内超过3个工单")

        # 降级
        if user["plan_downgraded"]:
            risk_score += 20
            risk_factors.append("近期降级计划")

        # NPS
        if user.get("nps_score", 10) < 7:
            risk_score += 10
            risk_factors.append("NPS评分低于7")

        return {
            "user_id": user["id"],
            "risk_score": min(risk_score, 100),
            "risk_level": "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low",
            "risk_factors": risk_factors,
        }
```

### 机器学习模型

```python
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split

def train_churn_model(features: pd.DataFrame, labels: pd.Series):
    """训练流失预测模型"""
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=42
    )

    model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
    )
    model.fit(X_train, y_train)

    # 特征重要性
    feature_importance = pd.DataFrame({
        "feature": features.columns,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)

    return {
        "model": model,
        "accuracy": model.score(X_test, y_test),
        "top_features": feature_importance.head(10),
    }
```

## 流失干预策略

### 分级干预

| 风险等级 | 干预措施 | 响应时间 |
|---------|---------|---------|
| 低（<30） | 定期关怀邮件 | 1 周 |
| 中（30-60） | 客户经理主动联系 | 3 天 |
| 高（>60） | 高管介入 + 专属方案 | 1 天 |

### 干预效果追踪

```python
class ChurnInterventionTracker:
    """流失干预效果追踪"""

    async def track_intervention(self, user_id: str, intervention: str, outcome: str):
        """记录干预结果"""
        await self.db.insert({
            "user_id": user_id,
            "intervention": intervention,
            "outcome": outcome,  # retained / churned / pending
            "timestamp": datetime.now(),
        })

    async def calculate_intervention_effectiveness(self) -> dict:
        """计算干预效果"""
        interventions = await self.db.get_all()

        results = {}
        for intervention_type in set(i["intervention"] for i in interventions):
            type_interventions = [i for i in interventions if i["intervention"] == intervention_type]
            retained = sum(1 for i in type_interventions if i["outcome"] == "retained")
            total = len(type_interventions)

            results[intervention_type] = {
                "retention_rate": retained / total if total > 0 else 0,
                "total_interventions": total,
            }

        return results
```

## 关键事实

1. **获取新客户的成本是保留现有客户的 5-25 倍**，流失预防比获客更具成本效益
2. **流失的三大信号类别**：行为信号（登录下降、功能使用减少）、财务信号（付款失败、降级）、互动信号（NPS 低、负面评价）
3. **基于规则的流失评分**通过加权求和行为和财务信号，风险分 >60 为高风险
4. **机器学习模型（如 GradientBoosting）**可以更精确地预测流失，特征重要性帮助识别关键流失因素
5. **分级干预策略**：低风险定期关怀、中风险客户经理联系、高风险高管介入，响应时间从 1 周到 1 天
