# RAG 可观测性：全链路追踪与异常检测

## 可观测性的三大支柱

RAG 系统的可观测性建立在三大支柱上：

1. **日志（Logging）**：记录每个请求的详细处理过程
2. **指标（Metrics）**：量化系统性能和质量
3. **追踪（Tracing）**：跟踪请求在各个组件间的流转

## LangFuse 集成

### 架构设计

Aureon 使用 LangFuse 作为全链路追踪平台：

```
请求 → LangChain Agent → astream_events → LangFuse CallbackHandler → LangFuse Cloud
```

### 初始化

```python
# langfuse_integration.py

from langfuse.callback import CallbackHandler

_langfuse_handler: CallbackHandler | None = None

async def init_langfuse():
    """FastAPI lifespan startup 中调用"""
    global _langfuse_handler

    if not settings.LANGFUSE_ENABLED:
        return

    _langfuse_handler = CallbackHandler(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
        release=settings.LANGFUSE_RELEASE,
    )

    # 验证连接
    await _langfuse_handler.async_client.health()

def get_langfuse_handler() -> CallbackHandler | None:
    """返回 LangFuse CallbackHandler 单例"""
    return _langfuse_handler

async def shutdown_langfuse():
    """lifespan shutdown 中调用，flush 所有待发送事件"""
    if _langfuse_handler:
        await _langfuse_handler.async_flush()

def get_trace_url(trace_id: str) -> str:
    """生成 trace 链接"""
    return f"{settings.LANGFUSE_HOST}/trace/{trace_id}"
```

### 注入到 Agent

```python
# executor.py

async def stream_agent(query: str, session_id: str):
    """流式 Agent 执行，注入 LangFuse 追踪"""
    handler = get_langfuse_handler()

    config = {}
    if handler:
        config["callbacks"] = [handler]
        config["metadata"] = {"session_id": session_id}

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=query)]},
        version="v2",
        config=config,
    ):
        yield event
```

### 自动追踪内容

LangFuse CallbackHandler 自动追踪：

1. **LLM 调用**：输入、输出、Token 使用、延迟
2. **Tool 调用**：工具名称、输入参数、输出结果
3. **Chain 步骤**：检索、Rerank、压缩等步骤
4. **RAG 查询**：查询文本、检索文档、生成答案

## 结构化日志

### structlog 配置

```python
import structlog

logger = structlog.get_logger(__name__)

# RAG 查询日志
async def log_rag_query(
    query: str,
    route: str,
    docs_count: int,
    latency_ms: float,
    faithfulness: float | None = None,
    session_id: str | None = None,
):
    """结构化日志记录 RAG 查询"""
    logger.info(
        "rag_query_completed",
        query=query[:100],  # 截断避免日志过大
        route=route,
        docs_count=docs_count,
        latency_ms=round(latency_ms, 1),
        faithfulness=faithfulness,
        session_id=session_id,
    )
```

### 日志规范

```python
# 禁止使用 print 和 logging.getLogger
# 必须使用 structlog.get_logger(__name__)

# ✅ 正确
logger.info("query_processed", query_id=qid, latency=latency)

# ❌ 错误
print(f"Query {qid} processed in {latency}ms")
logging.getLogger(__name__).info(f"Query {qid} processed")
```

## Prometheus 指标

### 自定义指标

```python
from prometheus_client import Histogram, Counter, Gauge

# RAG 查询延迟
rag_query_duration = Histogram(
    "rag_query_duration_seconds",
    "RAG query duration in seconds",
    ["route", "status"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# RAG 查询计数
rag_query_total = Counter(
    "rag_query_total",
    "Total RAG queries",
    ["route", "status"],
)

# 检索文档数
rag_retrieved_docs = Histogram(
    "rag_retrieved_docs",
    "Number of retrieved documents",
    ["route"],
    buckets=[1, 3, 5, 10, 20],
)

# Faithfulness 评分
rag_faithfulness = Histogram(
    "rag_faithfulness_score",
    "RAG Faithfulness score",
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
```

### 指标采集

```python
async def track_rag_query(query: str, pipeline):
    """追踪 RAG 查询指标"""
    start = time.perf_counter()

    try:
        result = await pipeline.run(query)
        status = "success"
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        rag_query_duration.labels(route=result.get("route", "unknown"), status=status).observe(duration)
        rag_query_total.labels(route=result.get("route", "unknown"), status=status).inc()
```

## 异常检测

### 延迟异常检测

```python
class LatencyAnomalyDetector:
    """延迟异常检测"""

    def __init__(self, window_size: int = 100, z_threshold: float = 3.0):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.recent_latencies = []

    def check(self, latency_ms: float) -> dict:
        """检查延迟是否异常"""
        self.recent_latencies.append(latency_ms)
        if len(self.recent_latencies) > self.window_size:
            self.recent_latencies = self.recent_latencies[-self.window_size:]

        if len(self.recent_latencies) < 10:
            return {"is_anomaly": False}

        mean = np.mean(self.recent_latencies)
        std = np.std(self.recent_latencies)

        if std == 0:
            return {"is_anomaly": False}

        z_score = (latency_ms - mean) / std
        is_anomaly = abs(z_score) > self.z_threshold

        return {
            "is_anomaly": is_anomaly,
            "z_score": z_score,
            "mean_latency": mean,
            "current_latency": latency_ms,
        }
```

### 质量异常检测

```python
class QualityAnomalyDetector:
    """质量异常检测"""

    def __init__(self, min_faithfulness: float = 0.7, min_relevancy: float = 0.75):
        self.min_faithfulness = min_faithfulness
        self.min_relevancy = min_relevancy

    def check(self, metrics: dict) -> list[str]:
        """检查质量是否异常"""
        alerts = []

        if metrics.get("faithfulness", 1.0) < self.min_faithfulness:
            alerts.append(f"Faithfulness 低于阈值：{metrics['faithfulness']:.3f} < {self.min_faithfulness}")

        if metrics.get("answer_relevancy", 1.0) < self.min_relevancy:
            alerts.append(f"Answer Relevancy 低于阈值：{metrics['answer_relevancy']:.3f} < {self.min_relevancy}")

        return alerts
```

## 关键事实

1. **RAG 可观测性的三大支柱**：日志（structlog）、指标（Prometheus）、追踪（LangFuse）
2. **LangFuse 自动追踪 LLM 调用、Tool 调用、Chain 步骤和 RAG 查询**，session_id 自动映射到 trace 的 session 标签
3. **LangFuse 集成架构**：`init_langfuse()` 在 startup 调用，`get_langfuse_handler()` 返回单例注入到 `astream_events`，`shutdown_langfuse()` 在 shutdown 时 flush
4. **Prometheus 自定义指标**包括查询延迟直方图、查询计数器、检索文档数和 Faithfulness 评分
5. **异常检测使用 Z-Score 方法**，当延迟的 Z 分数超过 3.0 时标记为异常，Faithfulness 低于 0.7 时告警
