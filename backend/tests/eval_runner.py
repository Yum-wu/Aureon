"""Unified RAG evaluation runner.

Combines existing evaluator.py metrics with DeepEval RAGAS metrics.
Generates reports and stores results in the evaluation database.

Run: cd backend && python -m tests.eval_runner [dataset_name]
"""

import os
import sys
import subprocess
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def get_git_version() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def get_recent_changes(n: int = 5) -> list:
    """Get recent git commit messages."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=5
        )
        return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except Exception:
        return []


def get_system_config() -> dict:
    """Get current RAG system configuration."""
    from app.config import settings
    return {
        "embedding_model": "DashScope text-embedding-v3",
        "embedding_dim": 1024,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "vector_backend": settings.vector_backend,
    }


def run_full_suite(
    dataset_name: str = "core_regression_27qa",
    include_deepeval: bool = True,
    include_existing: bool = True,
    latency_runs: int = 1,
) -> Dict[str, Any]:
    """Run complete evaluation suite.

    Combines existing evaluator.py metrics with DeepEval RAGAS metrics.
    """
    from tests.test_data_golden import load_dataset, get_dataset_info

    qa_pairs = load_dataset(dataset_name)
    info = get_dataset_info(dataset_name)

    results = {
        "dataset": info,
        "git_version": get_git_version(),
        "recent_changes": get_recent_changes(),
        "system_config": get_system_config(),
        "timestamp": datetime.now().isoformat(),
    }

    # ── Existing evaluator metrics ──
    if include_existing:
        print("Running existing evaluator metrics...")
        from app.rag.vector_store import retrieve
        from app.rag.qa_chain import rag_query
        from app.agent.llm import create_llm
        from app.rag.evaluator import evaluate_recall, evaluate_latency

        llm = create_llm()

        def rag_query_fn(query):
            return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

        # Build expected_map from golden dataset (skip negative QA with empty source_article)
        expected_map = {
            qa["question"]: qa["source_article"]
            for qa in qa_pairs
            if qa.get("source_article") and not qa.get("is_negative", False)
        }

        # Recall@3
        recall_result = evaluate_recall(retrieve, qa_pairs=qa_pairs, expected_map=expected_map, k=3)
        results["recall_at_3"] = recall_result["score"]

        # Recall@5
        recall_5 = evaluate_recall(retrieve, qa_pairs=qa_pairs, expected_map=expected_map, k=5)
        results["recall_at_5"] = recall_5["score"]

        # Latency
        if latency_runs > 0:
            latency_result = evaluate_latency(rag_query_fn, qa_pairs=qa_pairs[:10], num_runs=latency_runs)
            results["latency_p50_ms"] = latency_result.get("p50_ms", 0)
            results["latency_p99_ms"] = latency_result.get("p99_ms", 0)
            results["latency_mean_ms"] = latency_result.get("mean_ms", 0)

        print(f"  Recall@3: {results['recall_at_3']:.3f}")
        print(f"  Recall@5: {results['recall_at_5']:.3f}")

    # ── DeepEval RAGAS metrics ──
    if include_deepeval:
        print("Running DeepEval RAGAS metrics...")
        from tests.deepeval_eval import build_test_cases, run_deepeval_metrics, _load_article_texts

        from app.rag.qa_chain import hybrid_retrieve, rag_query
        from app.agent.llm import create_llm

        llm = create_llm()

        def rag_query_fn(query):
            return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

        article_texts = _load_article_texts()
        test_cases, used_qa_indices = build_test_cases(qa_pairs, hybrid_retrieve, rag_query_fn, article_texts)
        print(f"  Built {len(test_cases)} test cases")

        deepeval_scores = run_deepeval_metrics(test_cases, qa_pairs=qa_pairs, used_qa_indices=used_qa_indices)
        results.update({
            "context_precision": deepeval_scores.get("context_precision", 0),
            "context_recall": deepeval_scores.get("context_recall", 0),
            "context_relevancy": deepeval_scores.get("context_relevancy", 0),
            "answer_relevancy": deepeval_scores.get("answer_relevancy", 0),
            "faithfulness": deepeval_scores.get("faithfulness", 0),
            "hallucination": deepeval_scores.get("hallucination", 0),
            "negative_detection_rate": deepeval_scores.get("negative_detection_rate", 0),
            "negative_total": deepeval_scores.get("negative_total", 0),
            "negative_correct": deepeval_scores.get("negative_correct", 0),
            "deepeval_pass_rate": deepeval_scores.get("pass_rate", 0),
            "deepeval_elapsed": deepeval_scores.get("elapsed_seconds", 0),
        })

        for k in ["context_precision", "context_recall", "context_relevancy",
                   "answer_relevancy", "faithfulness", "hallucination"]:
            print(f"  {k}: {results[k]:.3f}")

    return results


def save_results_to_db(results: Dict[str, Any]):
    """Save evaluation results to the evaluation database."""
    from app.evaluation import save_evaluation_metric, init_evaluation_tables, EvaluationMetric

    init_evaluation_tables()

    benchmark_set = results.get("dataset", {}).get("version", "unknown")
    model_version = results.get("system", {}).get("llm_model", "unknown")

    # metric_name -> metric_type mapping
    METRIC_TYPE_MAP = {
        "recall_at_3": "retrieval",
        "recall_at_5": "retrieval",
        "context_precision": "deepeval_ragas",
        "context_recall": "deepeval_ragas",
        "context_relevancy": "deepeval_ragas",
        "answer_relevancy": "deepeval_ragas",
        "faithfulness": "deepeval_ragas",
        "hallucination": "deepeval_ragas",
        "latency_p50_ms": "latency",
        "latency_p99_ms": "latency",
    }

    metric_fields = list(METRIC_TYPE_MAP.keys())

    for field in metric_fields:
        if field in results and results[field] is not None:
            try:
                metric = EvaluationMetric(
                    metric_name=field,
                    metric_value=results[field],
                    metric_type=METRIC_TYPE_MAP.get(field, "other"),
                    benchmark_set=benchmark_set,
                    model_version=model_version,
                )
                save_evaluation_metric(metric)
            except Exception as e:
                print(f"  Warning: Failed to save {field}: {e}")

    print(f"Results saved to database (benchmark_set: {benchmark_set})")


def generate_report(results: Dict[str, Any], output_dir: str = None) -> str:
    """Generate Markdown evaluation report."""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "rag-evaluation", "reports")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = results.get("timestamp", datetime.now().isoformat())
    date_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d-%H%M")
    filename = f"rag-eval-report-{date_str}.md"
    filepath = os.path.join(output_dir, filename)

    config = results.get("system_config", {})
    changes = results.get("recent_changes", [])

    lines = []
    lines.append("# RAG 评估报告")
    lines.append("")
    lines.append(f"**日期**: {timestamp}")
    lines.append(f"**数据集**: {results.get('dataset', {}).get('version', 'N/A')} ({results.get('dataset', {}).get('total', 0)} QA)")
    lines.append(f"**RAG 版本**: main@{results.get('git_version', 'N/A')}")
    lines.append(f"**系统配置**: {config.get('embedding_model', 'N/A')} / {config.get('llm_model', 'N/A')} / {config.get('vector_backend', 'N/A')}")
    lines.append("")

    if changes:
        lines.append("**最近改动**:")
        for change in changes:
            lines.append(f"- {change}")
        lines.append("")

    # Retrieval quality
    lines.append("## 检索质量")
    lines.append("")
    lines.append("| 指标 | 分数 | 阈值 | 状态 |")
    lines.append("|------|------|------|------|")

    for name, display, threshold, higher in [
        ("recall_at_3", "Recall@3", 0.85, True),
        ("recall_at_5", "Recall@5", 0.85, True),
        ("context_precision", "Context Precision", 0.70, True),
        ("context_recall", "Context Recall", 0.75, True),
        ("context_relevancy", "Context Relevancy", 0.70, True),
    ]:
        val = results.get(name, 0)
        ok = val >= threshold if higher else val <= threshold
        lines.append(f"| {display} | {val:.3f} | {'≥' if higher else '≤'}{threshold:.2f} | {'✅' if ok else '⚠️'} |")

    # Generation quality
    lines.append("")
    lines.append("## 生成质量")
    lines.append("")
    lines.append("| 指标 | 分数 | 阈值 | 状态 |")
    lines.append("|------|------|------|------|")

    for name, display, threshold, higher in [
        ("faithfulness", "Faithfulness", 0.70, True),
        ("answer_relevancy", "Answer Relevancy", 0.60, True),
        ("hallucination", "Hallucination", 0.20, False),
    ]:
        val = results.get(name, 0)
        ok = val >= threshold if higher else val <= threshold
        lines.append(f"| {display} | {val:.3f} | {'≥' if higher else '≤'}{threshold:.2f} | {'✅' if ok else '⚠️'} |")

    # Latency
    if results.get("latency_p50_ms"):
        lines.append("")
        lines.append("## 延迟")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| P50 | {results['latency_p50_ms']:.0f}ms |")
        lines.append(f"| P99 | {results.get('latency_p99_ms', 0):.0f}ms |")
        lines.append(f"| Mean | {results.get('latency_mean_ms', 0):.0f}ms |")

    # Summary
    lines.append("")
    lines.append("## 总结")
    lines.append("")
    pass_rate = results.get("deepeval_pass_rate", 0)
    lines.append(f"- **DeepEval Pass Rate**: {pass_rate:.0%}")
    lines.append(f"- **评估耗时**: {results.get('deepeval_elapsed', 0):.1f}s")

    report = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report saved: {filepath}")
    return filepath


if __name__ == "__main__":
    dataset_name = sys.argv[1] if len(sys.argv) > 1 else "core_regression_27qa"
    skip_db = "--no-db" in sys.argv

    print("=" * 60)
    print("  Aureon RAG — Full Evaluation Suite")
    print(f"  Dataset: {dataset_name}")
    print("=" * 60)

    results = run_full_suite(dataset_name=dataset_name)

    if not skip_db:
        save_results_to_db(results)

    report_path = generate_report(results)
    print(f"\nDone! Report: {report_path}")
