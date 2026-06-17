# 新用户引导优化：从激活到习惯养成

## Onboarding 的重要性

新用户引导（Onboarding）是用户与产品的第一次深度接触。研究表明，40-60% 的用户在注册后第一次使用就流失了。优化 Onboarding 是提升激活率和留存率的最有效手段。

## Onboarding 设计原则

### 原则一：快速到 Aha Moment

Aha Moment 是用户第一次体验到产品核心价值的时刻。目标是在 5 分钟内让用户到达 Aha Moment。

### 原则二：渐进式引导

不要一次性展示所有功能，而是根据用户进度逐步引导：

```
第1步：完成核心操作（1分钟）
第2步：发现次要功能（3分钟）
第3步：个性化设置（5分钟）
第4步：邀请协作（10分钟）
```

### 原则三：价值先行

先让用户看到价值，再要求用户付出（填写信息、邀请队友等）。

## Onboarding 优化方法

### 漏斗分析

```python
def analyze_onboarding_funnel(onboarding_events: pd.DataFrame) -> pd.DataFrame:
    """分析 Onboarding 漏斗"""
    steps = ["signup", "complete_profile", "first_action", "aha_moment", "invite_teammate"]

    funnel = []
    for i, step in enumerate(steps):
        if i == 0:
            users = onboarding_events[onboarding_events["event"] == step]["user_id"].nunique()
        else:
            prev_users = set(onboarding_events[onboarding_events["event"] == steps[i-1]]["user_id"])
            current_users = set(onboarding_events[onboarding_events["event"] == step]["user_id"])
            users = len(prev_users & current_users)

        funnel.append({
            "step": step,
            "users": users,
            "conversion_from_prev": users / funnel[i-1]["users"] if i > 0 and funnel[i-1]["users"] > 0 else 1.0,
        })

    return pd.DataFrame(funnel)
```

### 时间到 Aha Moment 分析

```python
def time_to_aha(onboarding_events: pd.DataFrame) -> dict:
    """分析到达 Aha Moment 的时间分布"""
    aha_events = onboarding_events[onboarding_events["event"] == "aha_moment"]
    signup_events = onboarding_events[onboarding_events["event"] == "signup"]

    merged = aha_events.merge(signup_events, on="user_id", suffixes=("_aha", "_signup"))
    merged["time_to_aha_minutes"] = (merged["timestamp_aha"] - merged["timestamp_signup"]).dt.total_seconds() / 60

    return {
        "median_minutes": merged["time_to_aha_minutes"].median(),
        "p75_minutes": merged["time_to_aha_minutes"].quantile(0.75),
        "p90_minutes": merged["time_to_aha_minutes"].quantile(0.90),
        "within_5min_pct": (merged["time_to_aha_minutes"] <= 5).mean(),
    }
```

## 习惯养成模型

### Hook 模型

Nir Eyal 的 Hook 模型描述习惯养成的四个步骤：

1. **触发（Trigger）**：外部提醒或内部需求驱动用户行动
2. **行动（Action）**：用户执行期望行为
3. **奖励（Variable Reward）**：用户获得不确定的奖励
4. **投入（Investment）**：用户投入时间、数据、社交资本

### 习惯养成指标

| 阶段 | 指标 | 目标 |
|------|------|------|
| 触发 | 推送打开率 | >20% |
| 行动 | 日活跃率 | >30% |
| 奖励 | 功能满意度 | >4/5 |
| 投入 | 数据积累量 | 逐周增长 |

## 优化策略

1. **减少注册步骤**：社交登录、邮箱免密
2. **预设模板**：提供行业模板，减少从零开始的成本
3. **进度指示器**：显示 Onboarding 完成进度
4. **空状态设计**：新用户看到引导而非空白页
5. **智能推荐**：根据用户角色推荐功能

## 关键事实

1. **40-60% 的用户在注册后第一次使用就流失**，Onboarding 是最关键的留存环节
2. **Aha Moment 应在 5 分钟内到达**，超过 5 分钟用户流失率急剧上升
3. **渐进式引导**按用户进度逐步展示功能，避免信息过载
4. **Hook 模型（触发→行动→奖励→投入）**是习惯养成的理论框架，每个步骤都需要优化
5. **空状态设计**是新用户体验的关键——新用户看到的应是引导和示例，而非空白页面
