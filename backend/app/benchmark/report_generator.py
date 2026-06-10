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


def _check_mark(value: bool, ascii_safe: bool = False) -> str:
    """Return checkmark or X mark."""
    if ascii_safe:
        return "[PASS]" if value else "[FAIL]"
    return f"{COLORS['green']}✅{COLORS['reset']}" if value else f"{COLORS['red']}❌{COLORS['reset']}"


def _colorize(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def generate_terminal_output(results: Dict, ascii_safe: bool = False) -> str:
    """Generate colored terminal output.

    Args:
        results: Benchmark results dictionary

    Returns:
        Formatted string for terminal display
    """
    lines = []
    _cm = lambda v: _check_mark(v, ascii_safe=ascii_safe)

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
    lines.append(f"  Recall@5:      {recall_5*100:.1f}%  {_cm(recall_5 >= 0.95)} (target: ≥95%)")
    mrr = quality.get("mrr", 0)
    lines.append(f"  MRR:           {mrr:.3f}  {_cm(mrr >= 0.80)} (target: ≥0.80)")
    ndcg = quality.get("ndcg_at_10", 0)
    lines.append(f"  nDCG@10:       {ndcg:.3f}  {_cm(ndcg >= 0.80)} (target: ≥0.80)")
    lines.append("")

    # Latency
    latency = results.get("latency", {})
    lines.append(_colorize("> Latency", "cyan"))
    p50 = latency.get("p50_ms", 0)
    lines.append(f"  P50:           {p50:.1f}ms {_cm(p50 <= 20)} (target: ≤20ms)")
    lines.append(f"  P90:           {latency.get('p90_ms', 0):.1f}ms")
    p99 = latency.get("p99_ms", 0)
    lines.append(f"  P99:           {p99:.1f}ms")
    lines.append("")

    # Concurrency
    concurrency = results.get("concurrency", [])
    if concurrency:
        conc_100 = next((c for c in concurrency if c.get("level", c.get("concurrency")) == 100), concurrency[-1])
        level_val = conc_100.get('level', conc_100.get('concurrency', 100))
        lines.append(_colorize(f"> Concurrency ({level_val} concurrent)", "cyan"))
        qps = conc_100.get("qps", 0)
        lines.append(f"  QPS:           {qps:.1f}   {_cm(qps >= 50)} (target: ≥50)")
        success_rate = conc_100.get("success_rate", 0)
        lines.append(f"  Success rate:  {success_rate*100:.1f}%  {_cm(success_rate >= 0.95)} (target: ≥95%)")
        lines.append(f"  Avg latency:   {conc_100.get('avg_latency_ms', 0):.0f}ms")
        lines.append(f"  P99 latency:   {conc_100.get('p99_latency_ms', 0):.0f}ms {_cm(conc_100.get('p99_latency_ms', 0) <= 3000)} (target: ≤3s)")
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
        level = c.get('level', c.get('concurrency', 0))
        report += f"| {level} | {c.get('qps', 0):.1f} | {c.get('p99_latency_ms', 0):.0f}ms | {c.get('success_rate', 0)*100:.1f}% |\n"

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
