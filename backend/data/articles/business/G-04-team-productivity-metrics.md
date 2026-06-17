# 团队生产力度量：从代码到交付

## 度量的目的

团队生产力度量的目的不是监控个人，而是识别瓶颈、优化流程、持续改进。好的度量体系应关注**交付价值和流动效率**，而非单纯的代码量。

## DORA 四大指标

Google 的 DORA 研究提出四个关键指标：

| 指标 | 定义 | 高绩效标准 |
|------|------|-----------|
| 部署频率 | 多频繁部署到生产 | 按需（每天多次） |
| 变更前置时间 | 从提交到部署的时间 | <1 天 |
| 变更失败率 | 部署导致故障的比例 | <5% |
| 服务恢复时间 | 从故障到恢复的时间 | <1 小时 |

## 流动效率度量

### 关键指标

```python
class FlowMetrics:
    """流动效率度量"""

    def calculate_flow_efficiency(
        self,
        total_lead_time_hours: float,
        active_work_hours: float,
    ) -> float:
        """计算流动效率

        流动效率 = 实际工作时间 / 总前置时间
        """
        return active_work_hours / total_lead_time_hours if total_lead_time_hours > 0 else 0

    def calculate_cycle_time_distribution(self, cycle_times: list[float]) -> dict:
        """分析周期时间分布"""
        import numpy as np

        return {
            "p50": np.percentile(cycle_times, 50),
            "p75": np.percentile(cycle_times, 75),
            "p85": np.percentile(cycle_times, 85),
            "p95": np.percentile(cycle_times, 95),
        }
```

### WIP 限制

```python
def optimal_wip_limit(
    team_size: int,
    avg_cycle_time_days: float,
    throughput_per_week: float,
) -> int:
    """根据 Little's Law 计算 WIP 限制"""
    # Little's Law: WIP = Throughput × Cycle Time
    wip = throughput_per_week * (avg_cycle_time_days / 7)
    return max(int(wip * 1.2), team_size)  # 留 20% 余量
```

## 代码质量度量

| 指标 | 含义 | 目标 |
|------|------|------|
| 代码审查覆盖率 | PR 经过审查的比例 | >95% |
| 首次审查时间 | PR 提交到首次审查的时间 | <4 小时 |
| 变更大小 | 每个 PR 的代码行数 | <400 行 |
| 测试覆盖率 | 代码被测试覆盖的比例 | >80% |
| 缺陷逃逸率 | 逃逸到生产的缺陷比例 | <5% |

## 度量仪表盘

```python
class TeamDashboard:
    """团队生产力度量仪表盘"""

    def generate_report(self, sprint_data: dict) -> dict:
        """生成 Sprint 度量报告"""
        return {
            "delivery": {
                "stories_completed": sprint_data["stories_completed"],
                "story_points_completed": sprint_data["story_points"],
                "deployment_count": sprint_data["deployments"],
            },
            "quality": {
                "bug_escape_rate": sprint_data["bugs_in_prod"] / max(sprint_data["stories_completed"], 1),
                "test_coverage": sprint_data["test_coverage"],
                "code_review_coverage": sprint_data["pr_reviewed"] / max(sprint_data["pr_total"], 1),
            },
            "flow": {
                "cycle_time_p50": sprint_data["cycle_time_p50"],
                "flow_efficiency": self.calculate_flow_efficiency(
                    sprint_data["lead_time"], sprint_data["active_time"]
                ),
                "wip_violations": sprint_data["wip_violations"],
            },
        }
```

## 关键事实

1. **DORA 四大指标**是团队生产力的黄金标准：部署频率、变更前置时间、变更失败率、服务恢复时间
2. **流动效率 = 实际工作时间 / 总前置时间**，大多数团队流动效率仅 15-20%，80%+ 时间在等待
3. **Little's Law（WIP = Throughput × Cycle Time）**用于计算最优 WIP 限制，避免过载
4. **代码审查覆盖率应 >95%**，首次审查时间 <4 小时，PR 变更大小 <400 行
5. **度量的目的是识别瓶颈和优化流程**，不是监控个人，应关注交付价值和流动效率
