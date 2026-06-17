# MVP 方法论：最小可行产品的验证循环

## MVP 的定义

MVP（Minimum Viable Product）由 Eric Ries 在《精益创业》中提出：**用最低成本构建刚好能验证核心假设的产品版本**。MVP 不是半成品，而是精心设计的验证工具。

## MVP 的核心原则

### 原则一：假设驱动

每个功能背后都是一个假设，MVP 的目的是验证假设：

```
假设：用户愿意为 AI 辅助搜索付费
MVP：手动后台处理搜索请求，前端展示结果
验证：有多少用户愿意付费
```

### 原则二：最小化构建

只构建验证假设所需的最少功能：

```
❌ 完整的搜索系统（3个月）
✅ 人工后台 + 简单前端（1周）
```

### 原则三：快速迭代

Build-Measure-Learn 循环：

```
构建 MVP → 衡量结果 → 学习洞察 → 调整方向 → 构建下一个 MVP
```

## MVP 类型

| 类型 | 描述 | 成本 | 速度 |
|------|------|------|------|
| 门口测试 | 假装产品存在，看用户是否感兴趣 | 极低 | 1天 |
| 绿野仙踪 | 人工后台模拟自动化 | 低 | 1周 |
| 核心功能 | 只实现核心功能 | 中 | 2-4周 |
| 通用版 | 功能完整但粗糙 | 高 | 1-2月 |

## MVP 验证指标

```python
def evaluate_mvp(metrics: dict) -> dict:
    """评估 MVP 验证结果"""
    signals = {
        "strong_positive": metrics.get("conversion_rate", 0) > 0.05,
        "weak_positive": metrics.get("activation_rate", 0) > 0.3,
        "neutral": metrics.get("nps", 0) > 30,
        "negative": metrics.get("bounce_rate", 1) > 0.7,
    }

    if signals["strong_positive"]:
        recommendation = "继续投入，加速开发"
    elif signals["weak_positive"]:
        recommendation = "调整方向，优化核心体验"
    elif signals["negative"]:
        recommendation = "Pivot，重新定义问题"
    else:
        recommendation = "需要更多数据，延长测试"

    return {"signals": signals, "recommendation": recommendation}
```

## 常见错误

1. **MVP 太大**：包含过多功能，延迟验证
2. **MVP 太粗糙**：质量低到无法验证假设
3. **跳过验证**：直接全量开发
4. **忽略学习**：只构建不分析
5. **过早优化**：MVP 阶段优化转化漏斗

## 关键事实

1. **MVP 由 Eric Ries 在《精益创业》中提出**，核心目的是用最低成本验证核心假设
2. **Build-Measure-Learn 循环**是 MVP 的核心方法论：构建 → 衡量 → 学习 → 调整
3. **绿野仙踪 MVP**是最常用的验证方式——人工后台模拟自动化，1 周内可验证
4. **MVP 验证的三个信号**：强正面（转化率 >5%）、弱正面（激活率 >30%）、负面（跳出率 >70%）
5. **MVP 不是半成品**，而是精心设计的验证工具——每个功能都对应一个待验证的假设
