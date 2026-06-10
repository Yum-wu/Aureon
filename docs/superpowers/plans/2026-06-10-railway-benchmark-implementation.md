# Railway Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a comprehensive benchmark system to evaluate Aureon RAG performance in Railway production environment with 100 concurrent connections support.

**Architecture:** Create a new `backend/app/benchmark/` module with configuration management, HTTP client for Railway API calls, concurrency test suite for 100 concurrent connections, cost tracker, and multi-format report generator. Update existing `run_benchmark.py` to support Railway mode.

**Tech Stack:** Python 3.11+, httpx (async HTTP), asyncio, dataclasses, pytest

---

## File Structure

```
backend/app/benchmark/
├── __init__.py              # Module initialization
├── config.py                # BenchmarkEnv, ConcurrencyConfig
├── http_client.py           # RailwayBenchmarkClient
├── concurrency_test.py      # ConcurrencyTestSuite
├── cost_tracker.py          # CostTracker
└── report_generator.py      # generate_markdown_report()

backend/tests/
└── run_benchmark.py         # Updated main entry
```

---

## Task 1: Create Benchmark Module Initialization

**Files:**
- Create: `backend/app/benchmark/__init__.py`

- [ ] **Step 1: Create benchmark module directory and __init__.py**

Create `backend/app/benchmark/__init__.py`:

```python
"""Benchmark module for Railway production testing."""

from .config import BenchmarkEnv, ConcurrencyConfig, detect_environment
from .http_client import RailwayBenchmarkClient
from .cost_tracker import CostTracker
from .concurrency_test import ConcurrencyTestSuite
from .report_generator import generate_markdown_report, generate_terminal_output

__all__ = [
    "BenchmarkEnv",
    "ConcurrencyConfig",
    "detect_environment",
    "RailwayBenchmarkClient",
    "CostTracker",
    "ConcurrencyTestSuite",
    "generate_markdown_report",
    "generate_terminal_output",
]
```

- [ ] **Step 2: Verify module can be imported**

Run: `cd backend && python -c "from app.benchmark import detect_environment; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/benchmark/__init__.py
git commit -m "feat(benchmark): initialize benchmark module"
```

---

## Task 2: Implement Benchmark Configuration

**Files:**
- Create: `backend/app/benchmark/config.py`
- Create: `backend/tests/test_benchmark_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_benchmark_config.py`:

```python
"""Tests for benchmark configuration."""

import os
import pytest
from unittest.mock import patch


def test_detect_environment_local():
    """Test local environment detection."""
    with patch.dict(os.environ, {"BENCHMARK_MODE": "local"}, clear=False):
        from app.benchmark.config import detect_environment
        env = detect_environment()
        assert env.mode == "local"
        assert env.base_url is None
        assert env.api_key is None


def test_detect_environment_railway():
    """Test Railway environment detection."""
    with patch.dict(os.environ, {
        "BENCHMARK_MODE": "railway",
        "RAILWAY_API_URL": "https://test.up.railway.app",
        "RAILWAY_API_KEY": "test-key",
    }, clear=False):
        from app.benchmark.config import detect_environment
        # Reload to pick up new env vars
        import importlib
        import app.benchmark.config
        importlib.reload(app.benchmark.config)
        env = app.benchmark.config.detect_environment()
        assert env.mode == "railway"
        assert env.base_url == "https://test.up.railway.app"
        assert env.api_key == "test-key"


def test_concurrency_config_defaults():
    """Test default concurrency configuration."""
    from app.benchmark.config import ConcurrencyConfig
    config = ConcurrencyConfig()
    assert config.http_pool_limit == 100
    assert config.timeout_seconds == 30
    assert "deepseek-chat" in config.semaphores
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_benchmark_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.benchmark.config'`

- [ ] **Step 3: Write implementation**

Create `backend/app/benchmark/config.py`:

```python
"""Benchmark configuration management."""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class BenchmarkEnv:
    """Benchmark environment configuration."""
    mode: str  # "local" | "railway"
    base_url: Optional[str]
    api_key: Optional[str]
    vector_backend: str  # "chroma" | "qdrant"
    embedding_provider: str  # "local" | "dashscope" | "siliconflow"
    rerank_provider: str  # "api" | "local"


@dataclass
class ConcurrencyConfig:
    """Concurrency and connection pool configuration."""
    http_pool_limit: int = 100
    semaphores: Dict[str, int] = field(default_factory=dict)
    timeout_seconds: int = 30
    queue_timeout_seconds: int = 60

    def __post_init__(self):
        if not self.semaphores:
            mode = os.getenv("BENCHMARK_MODE", "local").lower()
            if mode == "railway":
                self.semaphores = {
                    "deepseek-chat": int(os.getenv("LLM_SEMAPHORE_DEEPSEEK", "80")),
                    "dashscope-embedding": int(os.getenv("LLM_SEMAPHORE_EMBEDDING", "80")),
                    "rag_pipeline": int(os.getenv("RAG_SEMAPHORE", "80")),
                    "rerank": int(os.getenv("RERANK_SEMAPHORE", "40")),
                }
            else:
                self.semaphores = {
                    "deepseek-chat": 30,
                    "dashscope-embedding": 50,
                    "rag_pipeline": 40,
                    "rerank": 20,
                }


# Pricing table (USD per 1000 tokens)
PRICING = {
    "dashscope_embedding": 0.00007,   # $0.07/1M tokens
    "dashscope_rerank": 0.0001,       # $0.1/1M tokens
    "deepseek_chat": 0.00028,         # $0.28/1M input
}


def detect_environment() -> BenchmarkEnv:
    """Auto-detect or configure benchmark environment."""
    mode = os.getenv("BENCHMARK_MODE", "local").lower()

    if mode == "railway":
        return BenchmarkEnv(
            mode="railway",
            base_url=os.getenv("RAILWAY_API_URL"),
            api_key=os.getenv("RAILWAY_API_KEY"),
            vector_backend=os.getenv("VECTOR_BACKEND", "qdrant"),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "dashscope"),
            rerank_provider=os.getenv("RERANK_PROVIDER", "dashscope"),
        )
    else:
        # Local mode - try to import from app settings
        try:
            from app.config import settings
            return BenchmarkEnv(
                mode="local",
                base_url=None,
                api_key=None,
                vector_backend=settings.vector_backend,
                embedding_provider="local",
                rerank_provider="api",
            )
        except ImportError:
            # Fallback if settings not available
            return BenchmarkEnv(
                mode="local",
                base_url=None,
                api_key=None,
                vector_backend=os.getenv("VECTOR_BACKEND", "chroma"),
                embedding_provider="local",
                rerank_provider="api",
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_benchmark_config.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/benchmark/config.py backend/tests/test_benchmark_config.py
git commit -m "feat(benchmark): add configuration management with environment detection"
```

---

## Task 3: Implement HTTP Client for Railway Mode

**Files:**
- Create: `backend/app/benchmark/http_client.py`
- Create: `backend/tests/test_http_client.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_http_client.py`:

```python
"""Tests for Railway HTTP client."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_response():
    """Create mock httpx response."""
    def _create(status_code=200, json_data=None):
        response = AsyncMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data or {"results": []}
        response.raise_for_status.return_value = None
        return response
    return _create


@pytest.mark.asyncio
async def test_retrieve_calls_api():
    """Test that retrieve() calls the correct API endpoint."""
    from app.benchmark.http_client import RailwayBenchmarkClient

    client = RailwayBenchmarkClient(
        base_url="https://test.up.railway.app",
        api_key="test-key",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": [{"text": "test", "score": 0.9}]}
    mock_response.raise_for_status.return_value = None

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        results = await client.retrieve("test query", top_k=5)
        assert len(results) == 1
        assert results[0]["text"] == "test"

    await client.close()


@pytest.mark.asyncio
async def test_health_check_success():
    """Test health check returns True when API is reachable."""
    from app.benchmark.http_client import RailwayBenchmarkClient

    client = RailwayBenchmarkClient(
        base_url="https://test.up.railway.app",
        api_key="test-key",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
        is_healthy = await client.health_check()
        assert is_healthy is True

    await client.close()


@pytest.mark.asyncio
async def test_health_check_failure():
    """Test health check returns False when API is unreachable."""
    from app.benchmark.http_client import RailwayBenchmarkClient

    client = RailwayBenchmarkClient(
        base_url="https://test.up.railway.app",
        api_key="test-key",
    )

    with patch.object(client._client, "get", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection failed")):
        is_healthy = await client.health_check()
        assert is_healthy is False

    await client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_http_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.benchmark.http_client'`

- [ ] **Step 3: Write implementation**

Create `backend/app/benchmark/http_client.py`:

```python
"""HTTP client for Railway benchmark API calls."""

import time
from typing import List, Dict, Optional
import httpx
import structlog

logger = structlog.get_logger()


class RailwayBenchmarkClient:
    """Async HTTP client for Railway-deployed RAG services."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        pool_limit: int = 100,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self._request_count = 0
        self._total_latency_ms = 0.0

        # Connection pool for concurrent requests
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=pool_limit,
                max_keepalive_connections=pool_limit // 2,
                keepalive_expiry=30,
            ),
        )

    async def close(self):
        """Close connection pool."""
        await self._client.aclose()

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Call RAG query API endpoint.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of retrieved chunks with text and metadata

        Raises:
            httpx.HTTPStatusError: If API returns error
            httpx.ConnectError: If connection fails
        """
        start = time.perf_counter()
        try:
            resp = await self._client.post(
                f"{self.base_url}/api/rag/query",
                json={"query": query, "top_k": top_k},
                headers=self.headers,
            )
            resp.raise_for_status()
            latency = (time.perf_counter() - start) * 1000

            self._request_count += 1
            self._total_latency_ms += latency

            return resp.json().get("results", [])
        except Exception as e:
            logger.warning("retrieve_failed", query=query[:50], error=str(e))
            raise

    async def health_check(self) -> bool:
        """Verify API is reachable.

        Returns:
            True if API responds with 200, False otherwise
        """
        try:
            resp = await self._client.get(
                f"{self.base_url}/api/health",
                headers=self.headers,
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning("health_check_failed", error=str(e))
            return False

    def get_stats(self) -> Dict:
        """Return client statistics."""
        avg_latency = (
            self._total_latency_ms / self._request_count
            if self._request_count > 0
            else 0.0
        )
        return {
            "request_count": self._request_count,
            "total_latency_ms": round(self._total_latency_ms, 1),
            "avg_latency_ms": round(avg_latency, 1),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_http_client.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/benchmark/http_client.py backend/tests/test_http_client.py
git commit -m "feat(benchmark): add HTTP client for Railway API calls"
```

---

## Task 4: Implement Cost Tracker

**Files:**
- Create: `backend/app/benchmark/cost_tracker.py`
- Create: `backend/tests/test_cost_tracker.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_cost_tracker.py`:

```python
"""Tests for cost tracker."""

import pytest
from app.benchmark.cost_tracker import CostTracker, TokenUsage


def test_record_usage():
    """Test recording token usage."""
    tracker = CostTracker()
    usage = TokenUsage(embedding=1000, rerank=500, llm=200, total=1700)
    tracker.record(usage)
    assert len(tracker.usages) == 1


def test_summary_calculation():
    """Test cost summary calculation."""
    tracker = CostTracker()
    tracker.record(TokenUsage(embedding=10000, rerank=5000, llm=2000, total=17000))
    tracker.record(TokenUsage(embedding=10000, rerank=5000, llm=2000, total=17000))

    summary = tracker.summary()
    assert summary["total_tokens"] == 34000
    assert summary["queries"] == 2
    assert summary["avg_tokens_per_query"] == 17000
    assert summary["estimated_cost_usd"] > 0


def test_empty_tracker():
    """Test empty tracker returns zeros."""
    tracker = CostTracker()
    summary = tracker.summary()
    assert summary["total_tokens"] == 0
    assert summary["queries"] == 0
    assert summary["estimated_cost_usd"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cost_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.benchmark.cost_tracker'`

- [ ] **Step 3: Write implementation**

Create `backend/app/benchmark/cost_tracker.py`:

```python
"""Cost tracking for API usage."""

from dataclasses import dataclass
from typing import Dict, List
from .config import PRICING


@dataclass
class TokenUsage:
    """Token usage for a single request."""
    embedding: int = 0
    rerank: int = 0
    llm: int = 0
    total: int = 0


class CostTracker:
    """Track API usage and estimate costs."""

    def __init__(self):
        self.usages: List[TokenUsage] = []

    def record(self, usage: TokenUsage):
        """Record token usage for a request."""
        self.usages.append(usage)

    def summary(self) -> Dict:
        """Calculate cost summary across all recorded usages."""
        total = TokenUsage()
        for u in self.usages:
            total.embedding += u.embedding
            total.rerank += u.rerank
            total.llm += u.llm
            total.total += u.total

        # Calculate costs using pricing table
        embedding_cost = total.embedding * PRICING["dashscope_embedding"] / 1000
        rerank_cost = total.rerank * PRICING["dashscope_rerank"] / 1000
        total_cost = embedding_cost + rerank_cost

        num_queries = len(self.usages)
        avg_tokens = total.total // max(num_queries, 1)

        return {
            "total_tokens": total.total,
            "embedding_tokens": total.embedding,
            "rerank_tokens": total.rerank,
            "llm_tokens": total.llm,
            "estimated_cost_usd": round(total_cost, 4),
            "queries": num_queries,
            "avg_tokens_per_query": avg_tokens,
            "cost_per_query_usd": round(total_cost / max(num_queries, 1), 6),
        }

    def reset(self):
        """Clear all recorded usages."""
        self.usages.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cost_tracker.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/benchmark/cost_tracker.py backend/tests/test_cost_tracker.py
git commit -m "feat(benchmark): add cost tracker for API usage"
```

---

## Task 5: Implement Concurrency Test Suite

**Files:**
- Create: `backend/app/benchmark/concurrency_test.py`
- Create: `backend/tests/test_concurrency.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_concurrency.py`:

```python
"""Tests for concurrency test suite."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_calculate_p99():
    """Test P99 latency calculation."""
    from app.benchmark.concurrency_test import ConcurrencyTestSuite

    suite = ConcurrencyTestSuite()
    results = [{"latency_ms": i * 10} for i in range(100)]
    p99 = suite._calculate_p99(results)
    assert p99 == 900.0  # 90th index = 900ms


@pytest.mark.asyncio
async def test_calculate_p99_empty():
    """Test P99 with empty results."""
    from app.benchmark.concurrency_test import ConcurrencyTestSuite

    suite = ConcurrencyTestSuite()
    p99 = suite._calculate_p99([])
    assert p99 == 0.0


@pytest.mark.asyncio
async def test_concurrency_levels():
    """Test that concurrency levels are defined."""
    from app.benchmark.concurrency_test import ConcurrencyTestSuite, CONCURRENCY_LEVELS

    assert 1 in CONCURRENCY_LEVELS
    assert 100 in CONCURRENCY_LEVELS
    assert len(CONCURRENCY_LEVELS) >= 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_concurrency.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.benchmark.concurrency_test'`

- [ ] **Step 3: Write implementation**

Create `backend/app/benchmark/concurrency_test.py`:

```python
"""Concurrency test suite for 100 concurrent connections."""

import asyncio
import time
from typing import List, Dict, Any
import structlog

logger = structlog.get_logger()

# Concurrency test levels
CONCURRENCY_LEVELS = [1, 10, 25, 50, 75, 100]

# Performance thresholds
THRESHOLDS = {
    "min_qps_at_100": 50,
    "max_p99_at_100_ms": 3000,
    "min_success_rate": 0.95,
    "max_timeout_rate": 0.05,
    "max_429_rate": 0.01,
}


class ConcurrencyTestSuite:
    """Test system under high concurrency load."""

    def __init__(self):
        self.results: List[Dict[str, Any]] = []

    async def test_http_concurrent(
        self,
        client,
        queries: List[str],
        concurrency: int,
    ) -> Dict[str, Any]:
        """Run concurrent HTTP requests.

        Args:
            client: RailwayBenchmarkClient instance
            queries: List of query strings to use
            concurrency: Number of concurrent requests

        Returns:
            Dictionary with test results
        """
        semaphore = asyncio.Semaphore(concurrency)
        tasks = []

        # Create tasks with rotating queries
        for i in range(concurrency):
            query = queries[i % len(queries)]
            task = self._throttled_query(client, query, semaphore)
            tasks.append(task)

        # Execute all tasks
        start = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.perf_counter() - start

        # Analyze results
        successes = [r for r in results if not isinstance(r, Exception) and r.get("success")]
        failures = [r for r in results if isinstance(r, Exception) or not r.get("success")]

        # Count bottleneck types
        bottlenecks = []
        rate_limits = sum(1 for r in failures if "429" in str(r))
        timeouts = sum(1 for r in failures if "timeout" in str(r).lower())

        if rate_limits > 0:
            bottlenecks.append(f"rate_limit: {rate_limits}")
        if timeouts > 0:
            bottlenecks.append(f"timeout: {timeouts}")

        return {
            "concurrency": concurrency,
            "total_queries": len(results),
            "successes": len(successes),
            "failures": len(failures),
            "elapsed_seconds": round(elapsed, 2),
            "qps": round(concurrency / elapsed, 2) if elapsed > 0 else 0,
            "avg_latency_ms": round(
                sum(r.get("latency_ms", 0) for r in successes) / max(len(successes), 1),
                1,
            ),
            "p99_latency_ms": self._calculate_p99(successes),
            "bottlenecks": bottlenecks,
            "success_rate": len(successes) / len(results) if results else 0,
        }

    async def _throttled_query(self, client, query: str, semaphore: asyncio.Semaphore):
        """Execute query with concurrency control."""
        async with semaphore:
            try:
                start = time.perf_counter()
                results = await client.retrieve(query, top_k=5)
                latency = (time.perf_counter() - start) * 1000

                return {
                    "success": True,
                    "latency_ms": latency,
                    "results_count": len(results),
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "latency_ms": 0,
                }

    def _calculate_p99(self, results: List[Dict]) -> float:
        """Calculate P99 latency from results."""
        if not results:
            return 0.0

        latencies = sorted([r.get("latency_ms", 0) for r in results])
        idx = int(len(latencies) * 0.99)
        return round(latencies[min(idx, len(latencies) - 1)], 1)

    def validate_thresholds(self, result: Dict) -> Dict[str, bool]:
        """Validate results against thresholds."""
        passed = {}

        if result["concurrency"] == 100:
            passed["qps"] = result["qps"] >= THRESHOLDS["min_qps_at_100"]
            passed["p99_latency"] = result["p99_latency_ms"] <= THRESHOLDS["max_p99_at_100_ms"]
            passed["success_rate"] = result["success_rate"] >= THRESHOLDS["min_success_rate"]

        return passed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_concurrency.py -v`
Expected: PASS (3 tests passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/benchmark/concurrency_test.py backend/tests/test_concurrency.py
git commit -m "feat(benchmark): add 100-concurrent test suite"
```

---

## Task 6: Implement Report Generator

**Files:**
- Create: `backend/app/benchmark/report_generator.py`
- Create: `backend/tests/test_report_generator.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_report_generator.py`:

```python
"""Tests for report generator."""

import pytest
import json
from pathlib import Path
from app.benchmark.report_generator import generate_terminal_output, generate_markdown_report


def test_terminal_output_contains_sections():
    """Test terminal output contains all required sections."""
    results = {
        "metadata": {"mode": "railway", "vector_backend": "qdrant"},
        "quality": {"recall_at_5": 0.96, "mrr": 0.85},
        "latency": {"p50_ms": 18.5, "p99_ms": 125.3},
        "concurrency": [{"level": 100, "qps": 83.5, "success_rate": 0.97}],
        "cost": {"total_tokens": 125000, "estimated_cost_usd": 0.012},
    }

    output = generate_terminal_output(results)
    assert "Retrieval Quality" in output
    assert "Latency" in output
    assert "Concurrency" in output
    assert "Cost Analysis" in output


def test_markdown_report_generation(tmp_path):
    """Test Markdown report file creation."""
    results = {
        "metadata": {"timestamp": "2026-06-10T15:30:00Z", "mode": "railway"},
        "quality": {"recall_at_5": 0.96},
        "latency": {"p50_ms": 18.5},
        "concurrency": [],
        "cost": {"total_tokens": 1000},
    }

    output_file = tmp_path / "test_report.md"
    report = generate_markdown_report(results, str(output_file))

    assert output_file.exists()
    assert "# Railway Benchmark Report" in report
    assert "2026-06-10" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_report_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.benchmark.report_generator'`

- [ ] **Step 3: Write implementation**

Create `backend/app/benchmark/report_generator.py`:

```python
"""Report generation for benchmark results."""

import json
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path


# ANSI color codes
COLORS = {
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "cyan": "\033[96m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def _check_mark(value: bool) -> str:
    """Return checkmark or X mark."""
    return f"{COLORS['green']}✅{COLORS['reset']}" if value else f"{COLORS['red']}❌{COLORS['reset']}"


def _colorize(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def generate_terminal_output(results: Dict) -> str:
    """Generate colored terminal output.

    Args:
        results: Benchmark results dictionary

    Returns:
        Formatted string for terminal display
    """
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append(_colorize("  AUREON RAG - Railway Production Benchmark", "bold"))
    lines.append("=" * 70)
    lines.append("")

    # Environment
    metadata = results.get("metadata", {})
    lines.append(_colorize("> Environment", "cyan"))
    lines.append(f"  Mode:          {metadata.get('mode', 'unknown').upper()}")
    lines.append(f"  Vector:        {metadata.get('vector_backend', 'unknown')}")
    lines.append(f"  Embedding:     {metadata.get('embedding_provider', 'unknown')}")
    lines.append(f"  Rerank:        {metadata.get('rerank_provider', 'unknown')}")
    lines.append("")

    # Retrieval Quality
    quality = results.get("quality", {})
    lines.append(_colorize("> Retrieval Quality", "cyan"))
    recall_5 = quality.get("recall_at_5", 0)
    lines.append(f"  Recall@5:      {recall_5*100:.1f}%  {_check_mark(recall_5 >= 0.95)} (target: ≥95%)")
    mrr = quality.get("mrr", 0)
    lines.append(f"  MRR:           {mrr:.3f}  {_check_mark(mrr >= 0.80)} (target: ≥0.80)")
    ndcg = quality.get("ndcg_at_10", 0)
    lines.append(f"  nDCG@10:       {ndcg:.3f}  {_check_mark(ndcg >= 0.80)} (target: ≥0.80)")
    lines.append("")

    # Latency
    latency = results.get("latency", {})
    lines.append(_colorize("> Latency", "cyan"))
    p50 = latency.get("p50_ms", 0)
    lines.append(f"  P50:           {p50:.1f}ms {_check_mark(p50 <= 20)} (target: ≤20ms)")
    lines.append(f"  P90:           {latency.get('p90_ms', 0):.1f}ms")
    p99 = latency.get("p99_ms", 0)
    lines.append(f"  P99:           {p99:.1f}ms")
    lines.append("")

    # Concurrency
    concurrency = results.get("concurrency", [])
    if concurrency:
        conc_100 = next((c for c in concurrency if c.get("level") == 100), concurrency[-1])
        lines.append(_colorize(f"> Concurrency ({conc_100.get('level', 100)} concurrent)", "cyan"))
        qps = conc_100.get("qps", 0)
        lines.append(f"  QPS:           {qps:.1f}   {_check_mark(qps >= 50)} (target: ≥50)")
        success_rate = conc_100.get("success_rate", 0)
        lines.append(f"  Success rate:  {success_rate*100:.1f}%  {_check_mark(success_rate >= 0.95)} (target: ≥95%)")
        lines.append(f"  Avg latency:   {conc_100.get('avg_latency_ms', 0):.0f}ms")
        lines.append(f"  P99 latency:   {conc_100.get('p99_latency_ms', 0):.0f}ms {_check_mark(conc_100.get('p99_latency_ms', 0) <= 3000)} (target: ≤3s)")
        lines.append("")

    # Cost Analysis
    cost = results.get("cost", {})
    lines.append(_colorize("> Cost Analysis", "cyan"))
    lines.append(f"  Total tokens:  {cost.get('total_tokens', 0):,}")
    lines.append(f"  Cost/query:    ${cost.get('cost_per_query_usd', 0):.6f}")
    lines.append(f"  Total cost:    ${cost.get('estimated_cost_usd', 0):.4f}")
    lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)


def generate_markdown_report(results: Dict, output_path: str) -> str:
    """Generate comprehensive Markdown report.

    Args:
        results: Benchmark results dictionary
        output_path: Path to save the report

    Returns:
        Markdown report content
    """
    metadata = results.get("metadata", {})
    quality = results.get("quality", {})
    latency = results.get("latency", {})
    concurrency = results.get("concurrency", [])
    cost = results.get("cost", {})

    report = f"""# Railway Benchmark Report

**Generated:** {metadata.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}
**Environment:** {metadata.get('mode', 'unknown').upper()}
**Vector Backend:** {metadata.get('vector_backend', 'unknown')}
**Embedding Provider:** {metadata.get('embedding_provider', 'unknown')}

---

## Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Recall@5 | {quality.get('recall_at_5', 0):.1%} | ≥95% | {'✅' if quality.get('recall_at_5', 0) >= 0.95 else '❌'} |
| MRR | {quality.get('mrr', 0):.3f} | ≥0.80 | {'✅' if quality.get('mrr', 0) >= 0.80 else '❌'} |
| Latency P50 | {latency.get('p50_ms', 0):.1f}ms | ≤20ms | {'✅' if latency.get('p50_ms', 0) <= 20 else '❌'} |
| QPS (100 concurrent) | {concurrency[-1].get('qps', 0) if concurrency else 0:.1f} | ≥50 | {'✅' if (concurrency[-1].get('qps', 0) if concurrency else 0) >= 50 else '❌'} |

---

## Detailed Results

### Retrieval Quality

```json
{json.dumps(quality, indent=2, ensure_ascii=False)}
```

### Latency Distribution

```json
{json.dumps(latency, indent=2)}
```

### Concurrency Results

| Level | QPS | P99 Latency | Success Rate |
|-------|-----|-------------|--------------|
"""
    for c in concurrency:
        report += f"| {c.get('level', 0)} | {c.get('qps', 0):.1f} | {c.get('p99_latency_ms', 0):.0f}ms | {c.get('success_rate', 0)*100:.1f}% |\n"

    report += f"""
### Cost Analysis

```json
{json.dumps(cost, indent=2)}
```

---
*Generated by Aureon Benchmark Suite*
"""

    # Save report
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report, encoding="utf-8")

    return report


def save_json_report(results: Dict, output_path: str) -> None:
    """Save results as JSON file.

    Args:
        results: Benchmark results dictionary
        output_path: Path to save the JSON file
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_report_generator.py -v`
Expected: PASS (2 tests passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/benchmark/report_generator.py backend/tests/test_report_generator.py
git commit -m "feat(benchmark): add multi-format report generator"
```

---

## Task 7: Update Main Benchmark Entry

**Files:**
- Modify: `backend/tests/run_benchmark.py`

- [ ] **Step 1: Read existing run_benchmark.py**

Read `backend/tests/run_benchmark.py` to understand current structure.

- [ ] **Step 2: Add Railway mode support**

Update `backend/tests/run_benchmark.py` with the following changes:

Add at the top of file (after existing imports):

```python
import argparse
import asyncio
from pathlib import Path


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Aureon RAG Benchmark")
    parser.add_argument(
        "--mode",
        choices=["local", "railway"],
        default=os.getenv("BENCHMARK_MODE", "local"),
        help="Benchmark mode",
    )
    parser.add_argument("--compare", help="Compare with previous run (JSON file)")
    parser.add_argument("--full", action="store_true", help="Run all concurrency levels")
    parser.add_argument("--output-dir", default="data", help="Output directory")
    return parser.parse_args()


async def run_railway_benchmark(args):
    """Run benchmark in Railway mode."""
    from app.benchmark import (
        detect_environment,
        RailwayBenchmarkClient,
        ConcurrencyTestSuite,
        CostTracker,
        generate_terminal_output,
        generate_markdown_report,
        save_json_report,
    )

    env = detect_environment()
    print(f"\n> Environment: {env.mode.upper()}")
    print(f"  URL: {env.base_url}")
    print(f"  Vector: {env.vector_backend}")

    # Create client
    client = RailwayBenchmarkClient(
        base_url=env.base_url,
        api_key=env.api_key,
    )

    # Health check
    print("\n> Checking API health...")
    if not await client.health_check():
        print("  ❌ API health check failed!")
        return
    print("  ✅ API is healthy")

    # Load test queries
    from app.rag.test_data import TEST_QA_PAIRS
    queries = [qa["question"] for qa in TEST_QA_PAIRS]

    # Run concurrency tests
    print("\n> Running concurrency tests...")
    suite = ConcurrencyTestSuite()
    concurrency_results = []

    levels = [1, 10, 25, 50, 75, 100] if args.full else [10, 50, 100]
    for level in levels:
        print(f"\n  Testing {level} concurrent...")
        result = await suite.test_http_concurrent(client, queries, level)
        concurrency_results.append(result)
        print(f"    QPS: {result['qps']}, Success: {result['success_rate']*100:.1f}%")

    # Build results
    results = {
        "metadata": {
            "timestamp": asyncio.get_event_loop().time(),
            "mode": env.mode,
            "vector_backend": env.vector_backend,
            "embedding_provider": env.embedding_provider,
        },
        "quality": {},  # Quality tests require local mode
        "latency": {},
        "concurrency": concurrency_results,
        "cost": CostTracker().summary(),
    }

    # Generate reports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)

    # Terminal output
    print("\n" + generate_terminal_output(results))

    # JSON report
    json_path = output_dir / f"benchmark_railway_{timestamp}.json"
    save_json_report(results, str(json_path))
    print(f"\n  JSON report: {json_path}")

    # Markdown report
    md_path = output_dir / f"benchmark_railway_{timestamp}.md"
    generate_markdown_report(results, str(md_path))
    print(f"  Markdown report: {md_path}")

    await client.close()


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "railway":
        asyncio.run(run_railway_benchmark(args))
    else:
        # Existing local mode logic
        main()  # Keep existing main() function
```

- [ ] **Step 3: Test local mode still works**

Run: `cd backend && python -m tests.run_benchmark --help`
Expected: Shows help with --mode, --compare, --full, --output-dir options

- [ ] **Step 4: Test Railway mode argument parsing**

Run: `cd backend && python -m tests.run_benchmark --mode railway --help`
Expected: Shows help with Railway mode options

- [ ] **Step 5: Commit**

```bash
git add backend/tests/run_benchmark.py
git commit -m "feat(benchmark): add Railway mode support to main entry"
```

---

## Task 8: Add httpx Dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Check if httpx is already installed**

Run: `cd backend && pip list | grep httpx`
Expected: If not installed, proceed to add it.

- [ ] **Step 2: Add httpx to requirements.txt**

Add to `backend/requirements.txt`:

```
httpx>=0.27.0
```

- [ ] **Step 3: Install dependency**

Run: `cd backend && pip install httpx>=0.27.0`
Expected: Successfully installed httpx

- [ ] **Step 4: Verify all tests pass**

Run: `cd backend && pytest tests/test_benchmark_config.py tests/test_http_client.py tests/test_cost_tracker.py tests/test_concurrency.py tests/test_report_generator.py -v`
Expected: All 14 tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore(deps): add httpx for async HTTP client"
```

---

## Task 9: Integration Test with Railway

**Files:**
- Create: `backend/tests/test_integration_railway.py`

- [ ] **Step 1: Write integration test**

Create `backend/tests/test_integration_railway.py`:

```python
"""Integration tests for Railway benchmark (requires live API)."""

import os
import pytest
import asyncio


@pytest.mark.skipif(
    os.getenv("BENCHMARK_MODE") != "railway",
    reason="Railway mode not enabled"
)
@pytest.mark.asyncio
async def test_railway_health_check():
    """Test health check against live Railway API."""
    from app.benchmark import detect_environment, RailwayBenchmarkClient

    env = detect_environment()
    if not env.base_url:
        pytest.skip("RAILWAY_API_URL not set")

    client = RailwayBenchmarkClient(env.base_url, env.api_key)
    is_healthy = await client.health_check()
    await client.close()

    assert is_healthy, "Railway API health check failed"


@pytest.mark.skipif(
    os.getenv("BENCHMARK_MODE") != "railway",
    reason="Railway mode not enabled"
)
@pytest.mark.asyncio
async def test_railway_retrieve():
    """Test single query against live Railway API."""
    from app.benchmark import detect_environment, RailwayBenchmarkClient

    env = detect_environment()
    if not env.base_url:
        pytest.skip("RAILWAY_API_URL not set")

    client = RailwayBenchmarkClient(env.base_url, env.api_key)
    results = await client.retrieve("What is RAG?", top_k=3)
    await client.close()

    assert len(results) > 0, "No results returned"


@pytest.mark.skipif(
    os.getenv("BENCHMARK_MODE") != "railway",
    reason="Railway mode not enabled"
)
@pytest.mark.asyncio
async def test_railway_concurrent():
    """Test 10 concurrent requests against live Railway API."""
    from app.benchmark import detect_environment, RailwayBenchmarkClient, ConcurrencyTestSuite

    env = detect_environment()
    if not env.base_url:
        pytest.skip("RAILWAY_API_URL not set")

    client = RailwayBenchmarkClient(env.base_url, env.api_key)
    queries = ["What is RAG?", "How does vector search work?", "Explain embeddings"]

    suite = ConcurrencyTestSuite()
    result = await suite.test_http_concurrent(client, queries, concurrency=10)

    await client.close()

    assert result["success_rate"] >= 0.9, f"Success rate too low: {result['success_rate']}"
    assert result["qps"] > 0, "QPS should be positive"
```

- [ ] **Step 2: Verify test file is valid**

Run: `cd backend && python -c "from tests.test_integration_railway import *; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_integration_railway.py
git commit -m "test(benchmark): add Railway integration tests"
```

---

## Task 10: Final Validation

**Files:**
- Run all benchmark tests
- Verify module imports

- [ ] **Step 1: Run all benchmark unit tests**

Run: `cd backend && pytest tests/test_benchmark_config.py tests/test_http_client.py tests/test_cost_tracker.py tests/test_concurrency.py tests/test_report_generator.py -v`
Expected: All 14 tests pass

- [ ] **Step 2: Verify module can be imported**

Run: `cd backend && python -c "from app.benchmark import detect_environment, RailwayBenchmarkClient, ConcurrencyTestSuite, CostTracker, generate_markdown_report; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Test CLI help**

Run: `cd backend && python -m tests.run_benchmark --help`
Expected: Shows all options including --mode, --compare, --full, --output-dir

- [ ] **Step 4: Final commit with all changes**

```bash
git add -A
git commit -m "feat(benchmark): complete Railway production benchmark system

- Add benchmark config module with environment detection
- Add HTTP client for Railway API calls with connection pool
- Add 100-concurrent test suite with bottleneck detection
- Add cost tracker for API usage
- Add multi-format report generator (terminal/JSON/Markdown)
- Update run_benchmark.py with Railway mode support
- Add integration tests for Railway deployment
- All 14 unit tests passing"
```

---

## Summary

**New Files Created:**
- `backend/app/benchmark/__init__.py`
- `backend/app/benchmark/config.py`
- `backend/app/benchmark/http_client.py`
- `backend/app/benchmark/cost_tracker.py`
- `backend/app/benchmark/concurrency_test.py`
- `backend/app/benchmark/report_generator.py`
- `backend/tests/test_benchmark_config.py`
- `backend/tests/test_http_client.py`
- `backend/tests/test_cost_tracker.py`
- `backend/tests/test_concurrency.py`
- `backend/tests/test_report_generator.py`
- `backend/tests/test_integration_railway.py`

**Modified Files:**
- `backend/tests/run_benchmark.py` (added Railway mode)
- `backend/requirements.txt` (added httpx)

**Total Tests:** 14 unit tests + 3 integration tests

**Next Steps:**
1. Set Railway environment variables
2. Deploy to Railway
3. Run benchmark: `python -m tests.run_benchmark --mode railway --full`
4. Review generated reports in `data/` directory
