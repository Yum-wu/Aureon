# RAG A/B 测试：如何科学对比两个 Pipeline

## A/B 测试的必要性

RAG 系统的优化需要验证——新的检索策略是否真的提升了质量？Rerank 阈值调整是否改善了延迟？A/B 测试是科学对比两个 Pipeline 的标准方法，避免"感觉更好"的主观判断。

## A/B 测试设计

### 测试变量

| 变量类型 | 示例 | 测试方式 |
|---------|------|---------|
| 检索策略 | Hybrid vs Dense-only | 对比 Recall@5 |
| Rerank 阈值 | 0.3 vs 0.5 vs 0.7 | 对比 MRR 和延迟 |
| Embedding 模型 | BGE-large vs BGE-M3 | 对比 Recall@5 |
| 查询路由 | 规则路由 vs LLM 路由 | 对比路由准确率和延迟 |
| Prompt 模板 | 模板 A vs 模板 B | 对比 Faithfulness |

### 流量分配

```python
import hashlib
import random

class ABTestRouter:
    """A/B 测试路由器"""

    def __init__(self, test_name: str, traffic_split: float = 0.5):
        self.test_name = test_name
        self.traffic_split = traffic_split

    def get_variant(self, user_id: str) -> str:
        """根据用户 ID 分配变体（一致性哈希）"""
        hash_value = int(hashlib.md5(f"{self.test_name}:{user_id}".encode()).hexdigest(), 16)
        return "treatment" if (hash_value % 100) < (self.traffic_split * 100) else "control"
```

### 测试执行

```python
class RAGABTest:
    """RAG A/B 测试框架"""

    def __init__(
        self,
        control_pipeline,
        treatment_pipeline,
        test_queries: list[str],
        ground_truth: list[dict],
        traffic_split: float = 0.5,
    ):
        self.control = control_pipeline
        self.treatment = treatment_pipeline
        self.queries = test_queries
        self.ground_truth = ground_truth
        self.traffic_split = traffic_split

    async def run(self) -> dict:
        """执行 A/B 测试"""
        control_results = []
        treatment_results = []

        for query, truth in zip(self.queries, self.ground_truth):
            variant = "treatment" if random.random() < self.traffic_split else "control"

            if variant == "control":
                result = await self._run_pipeline(self.control, query)
                control_results.append({"query": query, **result, **truth})
            else:
                result = await self._run_pipeline(self.treatment, query)
                treatment_results.append({"query": query, **result, **truth})

        # 统计分析
        analysis = self._analyze(control_results, treatment_results)
        return analysis

    async def _run_pipeline(self, pipeline, query: str) -> dict:
        """执行 Pipeline 并收集指标"""
        start = time.perf_counter()
        result = await pipeline.run(query)
        elapsed = time.perf_counter() - start

        return {
            "answer": result["answer"],
            "docs": result.get("docs", []),
            "latency_ms": elapsed * 1000,
        }

    def _analyze(self, control: list, treatment: list) -> dict:
        """统计分析结果"""
        from scipy import stats

        # 延迟对比
        control_latencies = [r["latency_ms"] for r in control]
        treatment_latencies = [r["latency_ms"] for r in treatment]

        latency_stat, latency_p = stats.mannwhitneyu(
            control_latencies, treatment_latencies, alternative="two-sided"
        )

        # 质量对比（需要评估）
        # ...

        return {
            "control_size": len(control),
            "treatment_size": len(treatment),
            "control_mean_latency": np.mean(control_latencies),
            "treatment_mean_latency": np.mean(treatment_latencies),
            "latency_p_value": latency_p,
            "latency_significant": latency_p < 0.05,
        }
```

## 统计显著性

### 最小样本量

```python
def minimum_sample_size(
    baseline_rate: float,
    expected_lift: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    """计算 A/B 测试最小样本量"""
    from scipy.stats import norm

    p1 = baseline_rate
    p2 = baseline_rate * (1 + expected_lift)
    p_avg = (p1 + p2) / 2

    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)

    n = (
        (z_alpha * math.sqrt(2 * p_avg * (1 - p_avg)) +
         z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    ) / (p2 - p1) ** 2

    return math.ceil(n)

# 示例：基线 Recall@5=0.85，期望提升 5%
# minimum_sample_size(0.85, 0.05) ≈ 600 条查询
```

### 结果解读

```python
def interpret_ab_result(analysis: dict) -> str:
    """解读 A/B 测试结果"""
    if analysis["latency_significant"]:
        if analysis["treatment_mean_latency"] < analysis["control_mean_latency"]:
            latency_verdict = "treatment 延迟显著更低 ✅"
        else:
            latency_verdict = "treatment 延迟显著更高 ❌"
    else:
        latency_verdict = "延迟无显著差异"

    return f"""
A/B 测试结果：
- 对照组样本：{analysis['control_size']}
- 实验组样本：{analysis['treatment_size']}
- 对照组平均延迟：{analysis['control_mean_latency']:.0f}ms
- 实验组平均延迟：{analysis['treatment_mean_latency']:.0f}ms
- P 值：{analysis['latency_p_value']:.4f}
- 结论：{latency_verdict}
"""
```

## 常见陷阱

1. **样本量不足**：统计功效不够，无法检测真实差异
2. **新奇效应**：新功能初期效果可能因新奇感而偏高
3. ** Simpson 悖论**：分组数据与汇总数据结论相反
4. **多重比较**：同时测试多个变量时，假阳性率上升
5. **流量污染**：同一用户可能同时出现在对照组和实验组

## 关键事实

1. **RAG A/B 测试的核心变量**：检索策略、Rerank 阈值、Embedding 模型、查询路由、Prompt 模板
2. **流量分配应使用一致性哈希**，确保同一用户始终分配到同一变体，避免流量污染
3. **最小样本量取决于基线率和期望提升**，基线 Recall@5=0.85、期望提升 5% 时需要约 600 条查询
4. **统计显著性判断使用 Mann-Whitney U 检验**（非参数检验，不假设正态分布），P 值 <0.05 为显著
5. **常见陷阱包括样本量不足、新奇效应和多重比较**，需要通过 Bonferroni 校正等方法控制假阳性率
