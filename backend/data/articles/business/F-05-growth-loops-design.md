# 增长飞轮设计：从获客到留存

## 飞轮模型

增长飞轮（Growth Flywheel）借鉴了亚马逊的飞轮效应：**每一个环节的产出都是下一个环节的输入，形成自我加速的正向循环**。

### 飞轮 vs 漏斗

传统漏斗模型是线性的：获客 → 激活 → 留存 → 变现 → 推荐。飞轮模型是循环的，推荐又驱动获客，形成闭环。

## 飞轮设计框架

### 五个环节

1. **获客（Acquire）**：吸引新用户
2. **激活（Activate）**：让用户体验核心价值
3. **留存（Retain）**：让用户持续使用
4. **变现（Revenue）**：将用户价值转化为收入
5. **推荐（Refer）**：让用户带来新用户

### 飞轮加速器

每个环节的"加速器"——即推动飞轮转动的关键动作：

| 环节 | 加速器 | 度量 |
|------|--------|------|
| 获客 | 内容营销、SEO、病毒传播 | CAC、新用户数 |
| 激活 | 优化 Onboarding、快速到 Aha Moment | 激活率、TTV |
| 留存 | 习惯培养、价值递增、切换成本 | 留存率、NRR |
| 变现 | 定价优化、增购路径、扩展收入 | ARPU、LTV |
| 推荐 | 推荐奖励、社交分享、口碑传播 | K因子、NPS |

## 飞轮设计案例

### 协作工具飞轮

```
获客：免费版吸引个人用户
  → 激活：5分钟创建第一个项目
    → 留存：团队协作形成习惯
      → 变现：团队规模扩大，升级付费版
        → 推荐：邀请队友加入（自带获客）
```

### API 服务飞轮

```
获客：免费额度吸引开发者
  → 激活：5分钟完成首次 API 调用
    → 留存：数据积累增加切换成本
      → 变现：用量增长超出免费额度
        → 推荐：开发者社区分享经验
```

## 飞轮诊断

### 诊断问题

1. **哪个环节最弱？**——飞轮速度由最弱环节决定
2. **飞轮是否自转？**——推荐是否能驱动足够的获客
3. **加速器是否有效？**——每个环节的关键动作是否执行到位
4. **飞轮是否在加速？**——关键指标是否逐月改善

### 诊断工具

```python
def diagnose_flywheel(metrics: dict) -> dict:
    """诊断飞轮健康度"""
    scores = {
        "acquire": min(metrics.get("new_users_weekly", 0) / 100, 1.0),
        "activate": metrics.get("activation_rate", 0),
        "retain": metrics.get("d30_retention", 0),
        "revenue": min(metrics.get("ltv_cac_ratio", 0) / 3, 1.0),
        "refer": min(metrics.get("k_factor", 0) / 0.5, 1.0),
    }

    weakest = min(scores, key=scores.get)
    strongest = max(scores, key=scores.get)

    return {
        "scores": scores,
        "weakest_link": weakest,
        "strongest_link": strongest,
        "is_self_sustaining": scores["refer"] > 0.3 and scores["activate"] > 0.5,
        "recommendation": f"优先优化 {weakest} 环节",
    }
```

## 关键事实

1. **增长飞轮是循环模型**，每个环节的产出是下一个环节的输入，推荐驱动获客形成闭环
2. **飞轮速度由最弱环节决定**——诊断飞轮首先要找到最弱环节并优先优化
3. **飞轮自转的条件**：推荐环节（K因子 > 0.3）能驱动足够的获客，激活率 > 50%
4. **Aha Moment 是激活环节的关键**——用户应在 5 分钟内体验核心价值
5. **飞轮设计应基于产品特性**：协作工具靠团队邀请驱动，API 服务靠开发者社区驱动
