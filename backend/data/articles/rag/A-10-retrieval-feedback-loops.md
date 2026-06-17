# 检索反馈闭环：从用户信号到检索优化

## 反馈闭环的必要性

RAG 系统上线后，检索质量并非一成不变。用户行为、文档更新、查询模式变化都会影响检索效果。建立反馈闭环，持续从用户信号中学习并优化检索，是保持系统长期高质量的关键。

## 用户信号类型

### 显式信号

用户主动提供的反馈：

1. **点赞/点踩**：对答案质量的直接评价
2. **投票**：答案是否有用
3. **纠错**：用户指出答案错误
4. **收藏**：标记有价值的内容

### 隐式信号

用户行为中隐含的反馈：

1. **停留时间**：阅读答案的时长
2. **复制行为**：复制答案内容（正面信号）
3. **重新生成**：请求重新生成答案（负面信号）
4. **追问**：基于答案继续提问（正面信号）
5. **跳出**：获得答案后立即离开（可能负面）
6. **查询改写**：用户自行改写查询重新搜索（检索失败的信号）

## 信号采集架构

### 事件设计

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class SignalType(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    COPY = "copy"
    REGENERATE = "regenerate"
    FOLLOW_UP = "follow_up"
    BOUNCE = "bounce"
    QUERY_REWRITE = "query_rewrite"

class UserSignal(BaseModel):
    session_id: str
    query_id: str
    signal_type: SignalType
    timestamp: datetime
    query: str
    answer: str | None = None
    retrieved_doc_ids: list[str] = []
    metadata: dict = {}
```

### 事件采集

```python
from fastapi import APIRouter, Request
from ..common import sse_event, SSE_HEADERS

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

@router.post("/signal")
async def record_signal(signal: UserSignal, request: Request):
    """记录用户反馈信号"""
    # 异步写入事件存储
    await signal_store.save(signal)

    # 实时更新统计
    await stats_collector.increment(signal.signal_type, signal.query_id)

    return {"status": "ok"}
```

## 从信号到优化

### 检索质量评估

利用用户信号评估检索质量：

```python
class RetrievalQualityAnalyzer:
    """基于用户信号的检索质量分析"""

    async def analyze_query_performance(
        self, query_id: str, signals: list[UserSignal]
    ) -> dict:
        """分析单次查询的检索质量"""
        positive_signals = [
            s for s in signals
            if s.signal_type in (SignalType.THUMBS_UP, SignalType.COPY, SignalType.FOLLOW_UP)
        ]
        negative_signals = [
            s for s in signals
            if s.signal_type in (SignalType.THUMBS_DOWN, SignalType.REGENERATE, SignalType.QUERY_REWRITE)
        ]

        quality_score = len(positive_signals) / max(len(positive_signals) + len(negative_signals), 1)

        return {
            "query_id": query_id,
            "quality_score": quality_score,
            "positive_count": len(positive_signals),
            "negative_count": len(negative_signals),
            "needs_improvement": quality_score < 0.5,
        }
```

### 查询-文档关联分析

识别哪些文档对哪些查询有效：

```python
class QueryDocAnalyzer:
    """查询-文档关联分析"""

    async def build_relevance_matrix(
        self, time_window_days: int = 30
    ) -> dict[str, dict[str, float]]:
        """构建查询-文档相关性矩阵"""
        signals = await signal_store.get_recent_signals(time_window_days)

        relevance = {}
        for signal in signals:
            query = signal.query
            for doc_id in signal.retrieved_doc_ids:
                if query not in relevance:
                    relevance[query] = {}
                if doc_id not in relevance[query]:
                    relevance[query][doc_id] = {"positive": 0, "negative": 0}

                if signal.signal_type in (SignalType.THUMBS_UP, SignalType.COPY):
                    relevance[query][doc_id]["positive"] += 1
                elif signal.signal_type in (SignalType.THUMBS_DOWN, SignalType.REGENERATE):
                    relevance[query][doc_id]["negative"] += 1

        return relevance
```

### 自动优化策略

#### 策略一：查询扩展学习

从成功的查询中学习扩展词：

```python
class QueryExpansionLearner:
    """从用户信号学习查询扩展"""

    async def learn_expansions(self, time_window_days: int = 30) -> dict[str, list[str]]:
        """学习查询扩展词"""
        # 找出高质量查询
        good_queries = await self._get_successful_queries(time_window_days)

        expansions = {}
        for query in good_queries:
            # 找出语义相似但效果差的查询
            similar_bad = await self._find_similar_failed_queries(query)

            for bad_query in similar_bad:
                # 分析差异，提取扩展词
                diff_terms = self._extract_diff_terms(query, bad_query)
                if bad_query not in expansions:
                    expansions[bad_query] = []
                expansions[bad_query].extend(diff_terms)

        return expansions
```

#### 策略二：文档权重调整

根据用户反馈调整文档权重：

```python
class DocumentWeightAdjuster:
    """基于用户反馈调整文档权重"""

    async def adjust_weights(self) -> dict[str, float]:
        """计算文档权重调整因子"""
        relevance = await self.analyzer.build_relevance_matrix()

        weight_adjustments = {}
        for query, docs in relevance.items():
            for doc_id, counts in docs.items():
                total = counts["positive"] + counts["negative"]
                if total >= 3:  # 至少 3 次反馈才调整
                    score = counts["positive"] / total
                    # 权重调整：正反馈提升，负反馈降低
                    adjustment = 1.0 + (score - 0.5) * 0.2  # 调整幅度 ±10%
                    weight_adjustments[doc_id] = adjustment

        return weight_adjustments
```

#### 策略三：负例模式学习

识别系统无法回答的查询模式：

```python
class NegativePatternLearner:
    """学习负例查询模式"""

    NEGATIVE_PATTERNS = []

    async def learn_patterns(self, time_window_days: int = 30) -> list[str]:
        """学习负例查询模式"""
        # 找出频繁触发负面信号的查询
        bad_queries = await self._get_negative_queries(time_window_days)

        # 提取共同关键词
        keyword_freq = {}
        for query in bad_queries:
            keywords = self._extract_keywords(query)
            for kw in keywords:
                keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

        # 高频关键词作为负例模式
        patterns = [
            kw for kw, freq in keyword_freq.items()
            if freq >= 3 and freq / len(bad_queries) > 0.2
        ]

        return patterns
```

## A/B 测试框架

### 检索策略 A/B 测试

```python
class RetrievalABTest:
    """检索策略 A/B 测试"""

    async def run_test(
        self,
        test_name: str,
        control_fn,  # 对照组检索函数
        treatment_fn,  # 实验组检索函数
        queries: list[str],
        traffic_split: float = 0.5,
    ) -> dict:
        """运行 A/B 测试"""
        results = {"control": [], "treatment": []}

        for query in queries:
            import random
            if random.random() < traffic_split:
                # 实验组
                result = await treatment_fn(query)
                results["treatment"].append({"query": query, "result": result})
            else:
                # 对照组
                result = await control_fn(query)
                results["control"].append({"query": query, "result": result})

        # 统计分析
        analysis = self._analyze_results(results)
        return analysis
```

## 闭环自动化

### 自动化 Pipeline

```
用户信号采集 → 信号聚合 → 质量评估 → 优化策略生成 → 策略验证 → 自动应用
```

```python
class FeedbackLoopPipeline:
    """反馈闭环自动化 Pipeline"""

    async def run_daily(self):
        """每日运行反馈闭环"""
        # 1. 聚合最近 7 天的用户信号
        signals = await self.collector.aggregate(days=7)

        # 2. 评估检索质量
        quality_report = await self.analyzer.analyze(signals)

        # 3. 生成优化策略
        optimizations = await self.optimizer.suggest(quality_report)

        # 4. 验证优化策略
        for opt in optimizations:
            validated = await self.validator.validate(opt)
            if validated.confidence > 0.8:
                # 5. 应用优化
                await self.applier.apply(opt)

        # 6. 生成报告
        report = await self.reporter.generate(quality_report, optimizations)
        return report
```

## 关键事实

1. **用户信号分为显式信号（点赞/点踩/纠错）和隐式信号（停留时间/复制/重新生成）**，两者都可用于检索质量评估
2. **查询改写是最强的负面信号**——用户自行改写查询意味着原始检索失败，应重点分析此类信号
3. **查询-文档关联分析**可以识别哪些文档对哪些查询有效，据此调整文档权重（正反馈提升、负反馈降低）
4. **负例模式学习**从频繁触发负面信号的查询中提取共同关键词，构建负例检测规则
5. **反馈闭环应自动化运行**，建议每日聚合信号、评估质量、生成优化策略，置信度 >0.8 的策略自动应用
