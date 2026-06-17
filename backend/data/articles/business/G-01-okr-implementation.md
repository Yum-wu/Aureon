# OKR 落地实践：从目标到关键结果

## OKR 概述

OKR（Objectives and Key Results）由 Intel 的 Andy Grove 发明，后经 Google 推广。O 是方向性目标（定性），KR 是可衡量的关键结果（定量）。

### OKR vs KPI

| 维度 | OKR | KPI |
|------|-----|-----|
| 性质 | 挑战性目标 | 维持性指标 |
| 完成度 | 70% 即优秀 | 100% 才达标 |
| 周期 | 季度 | 月度/年度 |
| 透明度 | 全公司可见 | 部门内可见 |
| 关联 | 上下对齐 | 各自独立 |

## OKR 制定

### 好的 Objective

- 有方向感和激励性
- 定性描述，不用数字
- 季度内可推进
- 与公司战略对齐

### 好的 Key Result

- 可量化、可验证
- 3-5 个 KR 支持 1 个 O
- 结果导向，非过程导向
- 有挑战性（70% 完成度为佳）

### 示例

```
O：成为最可靠的企业级 RAG 平台
  KR1：系统可用性达到 99.9%
  KR2：P50 查询延迟降至 800ms 以下
  KR3：客户 NPS 提升至 60+
  KR4：Faithfulness 评分达到 0.95+
```

## OKR 落地流程

### 季度循环

```
第1周：公司级 OKR 制定
第2周：团队级 OKR 对齐
第3-11周：执行 + 周同步
第12周：复盘 + 评分
```

### 周同步（Check-in）

```python
class OKRCheckin:
    """OKR 周同步模板"""

    def __init__(self, okr_id: str):
        self.okr_id = okr_id

    def generate_template(self) -> dict:
        return {
            "kr_progress": "每个 KR 的当前进度（0-100%）",
            "confidence_level": "完成信心（高/中/低）",
            "blockers": "阻碍进度的因素",
            "next_actions": "下周的关键行动",
            "help_needed": "需要什么帮助",
        }
```

## 常见陷阱

1. **OKR 变成任务列表**：KR 应是结果而非待办事项
2. **目标过低**：70% 完成度是健康的，100% 说明目标太低
3. **OKR 过多**：每个周期 3-5 个 O，每个 O 3-5 个 KR
4. **缺乏对齐**：团队 OKR 与公司 OKR 不对齐
5. **设定后遗忘**：需要周同步保持关注

## 关键事实

1. **OKR 由 Andy Grove 发明、Google 推广**，O 是定性目标，KR 是定量关键结果
2. **OKR 的完成度 70% 即为优秀**，100% 完成说明目标设定过低
3. **每个周期 3-5 个 O，每个 O 3-5 个 KR**，过多会分散注意力
4. **周同步（Check-in）是 OKR 落地的关键**，每周更新进度、信心和阻碍
5. **OKR 与 KPI 的核心区别**：OKR 是挑战性目标（完成 70% 即优秀），KPI 是维持性指标（必须 100% 达标）
