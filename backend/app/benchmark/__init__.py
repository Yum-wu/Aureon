"""Benchmark module for Railway production testing."""

from .config import BenchmarkEnv, ConcurrencyConfig, detect_environment

__all__ = [
    "BenchmarkEnv",
    "ConcurrencyConfig",
    "detect_environment",
]

try:
    from .http_client import RailwayBenchmarkClient
    __all__.append("RailwayBenchmarkClient")
except ImportError:
    pass

try:
    from .cost_tracker import CostTracker
    __all__.append("CostTracker")
except ImportError:
    pass

try:
    from .concurrency_test import ConcurrencyTestSuite
    __all__.append("ConcurrencyTestSuite")
except ImportError:
    pass

try:
    from .report_generator import generate_markdown_report, generate_terminal_output
    __all__.extend(["generate_markdown_report", "generate_terminal_output"])
except ImportError:
    pass
