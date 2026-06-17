# 用户留存分析框架

## 留存的重要性

留存是 SaaS 最重要的指标之一。研究表明，留存率提升 5% 可以带来 25-95% 的利润增长。没有留存的增长只是"漏水桶"——新用户不断进来，老用户不断流失。

## 留存指标体系

### 核心指标

| 指标 | 定义 | 计算方式 |
|------|------|---------|
| 次日留存 | 新用户次日回访比例 | 次日回访用户/新用户 |
| 7日留存 | 新用户7日后回访比例 | 7日后回访/新用户 |
| 30日留存 | 新用户30日后回访比例 | 30日后回访/新用户 |
| 月留存率 | 月活跃用户中下月仍活跃的比例 | 下月活跃/本月活跃 |
| 净留存率（NRR） | 考虑增购和流失的留存 | (期初MRR+增购-流失-降级)/期初MRR |

### 留存曲线分析

```
留存率
100% |████
 80% |████ ████
 60% |████ ████ ████
 40% |████ ████ ████ ████ ← 留存拐点
 20% |████ ████ ████ ████ ████ ████
     ───────────────────────────────
     D1   D7   D14  D30  D60  D90
```

健康的留存曲线应有明显的"拐点"——用户度过拐点后留存趋于稳定。

## 留存分析方法

### 队列分析（Cohort Analysis）

按注册时间分组，追踪每组的留存率变化：

```python
import pandas as pd

def cohort_retention(users: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """队列留存分析"""
    # 计算每个用户的注册月份
    users['cohort_month'] = users['signup_date'].dt.to_period('M')

    # 计算每个用户的活跃月份
    events['active_month'] = events['event_date'].dt.to_period('M')
    events['months_since_signup'] = (events['active_month'] - events['cohort_month']).astype(int)

    # 计算留存率
    retention = events.groupby(['cohort_month', 'months_since_signup'])['user_id'].nunique()
    cohort_sizes = users.groupby('cohort_month')['user_id'].nunique()

    retention_rate = retention / cohort_sizes
    return retention_rate.unstack()
```

### 留存归因

识别影响留存的关键行为：

```python
def retention_attribution(users: pd.DataFrame, key_actions: list[str]) -> dict:
    """留存归因：哪些行为与留存强相关"""
    results = {}

    for action in key_actions:
        # 执行了该行为的用户
        did_action = users[users[action] == True]
        # 未执行该行为的用户
        didnt_action = users[users[action] == False]

        # 两组的 30 日留存率
        retention_did = did_action['retained_30d'].mean()
        retention_didnt = didnt_action['retained_30d'].mean()

        results[action] = {
            "retention_with_action": retention_did,
            "retention_without_action": retention_didnt,
            "impact": retention_did - retention_didnt,
        }

    return results
```

## 留存提升策略

### 策略一：优化 Onboarding

新用户前 5 分钟的体验决定留存。确保用户快速到达 Aha Moment。

### 策略二：培养习惯

通过定期推送、邮件提醒、成就系统培养用户使用习惯。

### 策略三：增加切换成本

数据积累、工作流定制、团队协作等增加用户离开的成本。

### 策略四：流失预警

识别流失信号（登录频率下降、功能使用减少），主动干预。

## 关键事实

1. **留存率提升 5% 可带来 25-95% 的利润增长**，留存是 SaaS 最重要的指标之一
2. **健康的留存曲线应有明显的"拐点"**，用户度过拐点后留存趋于稳定
3. **队列分析（Cohort Analysis）**按注册时间分组追踪留存率，是最基础的留存分析方法
4. **留存归因**识别与留存强相关的关键行为，通常 3-5 个核心行为决定 80% 的留存
5. **净留存率（NRR）>100%**意味着现有客户增购超过流失，是 SaaS 健康的黄金标准
