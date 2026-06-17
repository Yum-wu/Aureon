# RAG 回归测试：防止优化变劣化

## 回归测试的必要性

RAG 系统的优化是一个迭代过程，每次修改都可能引入回归——新的优化改善了某些指标，但恶化了其他指标。回归测试通过在每次变更后运行固定测试集，确保优化不会导致已有功能劣化。

## 回归测试设计

### 测试集构建

```python
# 回归测试集：包含关键查询和预期结果
REGRESSION_TEST_CASES = [
    {
        "id": "reg-001",
        "query": "什么是 RAG？",
        "min_faithfulness": 0.8,
        "min_relevancy": 0.8,
        "max_latency_ms": 3000,
        "must_contain": ["检索", "生成"],
        "must_not_contain": ["我不知道"],
    },
    {
        "id": "reg-002",
        "query": "Aureon 的定价是多少？",
        "expected_action": "reject",  # 负例，应该被拒绝
        "max_latency_ms": 1000,
    },
    {
        "id": "reg-003",
        "query": "比较 BM25 和稀疏向量",
        "min_faithfulness": 0.7,
        "min_relevancy": 0.7,
        "max_latency_ms": 5000,
        "must_contain": ["BM25", "稀疏向量"],
    },
]
```

### 回归测试执行

```python
class RegressionTestRunner:
    """回归测试执行器"""

    async def run(self, pipeline, test_cases: list[dict]) -> dict:
        """执行回归测试"""
        results = []
        all_passed = True

        for case in test_cases:
            result = await self._run_single(pipeline, case)
            results.append(result)
            if not result["passed"]:
                all_passed = False

        return {
            "total": len(test_cases),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
            "all_passed": all_passed,
            "details": results,
        }

    async def _run_single(self, pipeline, case: dict) -> dict:
        """执行单个回归测试"""
        start = time.perf_counter()
        output = await pipeline.run(case["query"])
        latency = (time.perf_counter() - start) * 1000

        failures = []

        # 延迟检查
        if latency > case.get("max_latency_ms", float("inf")):
            failures.append(f"延迟超标：{latency:.0f}ms > {case['max_latency_ms']}ms")

        # 负例检查
        if case.get("expected_action") == "reject":
            if "我不知道" not in output["answer"] and "无法" not in output["answer"]:
                failures.append("负例未被正确拒绝")

        # 关键词检查
        answer = output["answer"]
        for keyword in case.get("must_contain", []):
            if keyword not in answer:
                failures.append(f"缺少关键词：{keyword}")

        for keyword in case.get("must_not_contain", []):
            if keyword in answer:
                failures.append(f"包含禁止关键词：{keyword}")

        return {
            "id": case["id"],
            "query": case["query"],
            "latency_ms": latency,
            "passed": len(failures) == 0,
            "failures": failures,
        }
```

### CI 集成

```yaml
# .github/workflows/rag-regression.yml
name: RAG Regression Test
on:
  pull_request:
    paths:
      - 'backend/app/rag/**'

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r backend/requirements.txt
      - name: Run regression tests
        run: cd backend && python -m pytest tests/test_rag_regression.py -v
        env:
          QDRANT_URL: ${{ secrets.QDRANT_URL }}
          DASHSCOPE_API_KEY: ${{ secrets.DASHSCOPE_API_KEY }}
```

## 回归监控

### 指标趋势追踪

```python
class RegressionMonitor:
    """回归监控器"""

    async def check_regression(
        self,
        current_metrics: dict,
        baseline_metrics: dict,
        tolerance: float = 0.05,
    ) -> dict:
        """检查指标是否回归"""
        regressions = []

        for metric, baseline_value in baseline_metrics.items():
            current_value = current_metrics.get(metric)
            if current_value is None:
                continue

            change = (current_value - baseline_value) / baseline_value

            # 对于越高越好的指标（如 Faithfulness）
            if metric in ("faithfulness", "answer_relevancy", "recall_at_5", "mrr"):
                if change < -tolerance:
                    regressions.append({
                        "metric": metric,
                        "baseline": baseline_value,
                        "current": current_value,
                        "change_pct": change * 100,
                        "direction": "degraded",
                    })

            # 对于越低越好的指标（如延迟、幻觉率）
            elif metric in ("latency_p50", "hallucination_rate"):
                if change > tolerance:
                    regressions.append({
                        "metric": metric,
                        "baseline": baseline_value,
                        "current": current_value,
                        "change_pct": change * 100,
                        "direction": "degraded",
                    })

        return {
            "has_regression": len(regressions) > 0,
            "regressions": regressions,
            "tolerance": tolerance,
        }
```

### 自动回滚

```python
class AutoRollback:
    """自动回滚"""

    async def deploy_with_rollback(
        self,
        new_pipeline,
        baseline_metrics: dict,
        test_queries: list[str],
        max_regression_rate: float = 0.1,
    ) -> dict:
        """部署新 Pipeline，检测到回归则自动回滚"""
        # 运行回归测试
        current_metrics = await self._evaluate(new_pipeline, test_queries)

        # 检查回归
        regression_report = await self.monitor.check_regression(
            current_metrics, baseline_metrics
        )

        if regression_report["has_regression"]:
            regression_rate = len(regression_report["regressions"]) / len(baseline_metrics)

            if regression_rate > max_regression_rate:
                # 回滚
                return {
                    "action": "rollback",
                    "reason": f"回归率 {regression_rate:.1%} 超过阈值 {max_regression_rate:.1%}",
                    "regressions": regression_report["regressions"],
                }

        # 部署
        return {"action": "deploy", "metrics": current_metrics}
```

## 关键事实

1. **回归测试通过在每次变更后运行固定测试集**，确保优化不会导致已有功能劣化
2. **回归测试用例应包含关键查询、延迟上限、关键词检查和负例**，覆盖功能和质量两个维度
3. **CI 集成**将回归测试加入 Pull Request 流程，RAG 相关代码变更自动触发测试
4. **指标趋势追踪**对比当前指标与基线指标，变化超过容差（通常 5%）视为回归
5. **自动回滚机制**在回归率超过阈值（通常 10%）时自动回退到上一版本，防止劣化上线
