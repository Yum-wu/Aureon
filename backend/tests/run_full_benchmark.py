"""
统一 RAG Benchmark 测试 — 三阶段端到端测试流程

Phase 1: Railway 生产环境数据采集（192 queries + TTFT/TPOT）
Phase 2: 本地 LLM-as-Judge 评估生成质量（Faithfulness + Answer Relevancy）
Phase 3: 汇总 6 维报告 + 对比历史数据

使用方式:
  cd backend && python tests/run_full_benchmark.py              # 运行全部 3 个阶段
  cd backend && python tests/run_full_benchmark.py --phase 1    # 仅采集
  cd backend && python tests/run_full_benchmark.py --phase 2    # 仅评估（需要先有 raw 数据）
  cd backend && python tests/run_full_benchmark.py --phase 3    # 仅汇总（需要先有 raw + eval 数据）

环境变量:
  BENCHMARK_BASE_URL — Railway 端点（默认 https://aureon-production-1247.up.railway.app）
  BENCHMARK_SAMPLE_N — LLM-as-Judge 采样数（默认 30）
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

# ── 路径设置 ──
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://aureon-production-1247.up.railway.app"
SAMPLE_N = 30
PRECISION = 0.6  # 进度条宽度


def _load_api_key() -> str:
    """从 .env 读取 API Key"""
    env_path = BACKEND_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("DASHSCOPE_API_KEY=") or line.startswith("LLM_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    import os
    return os.getenv("DASHSCOPE_API_KEY") or os.getenv("LLM_API_KEY") or ""


def _progress(current: int, total: int, prefix: str = "", suffix: str = "") -> None:
    """打印进度条"""
    pct = current / total if total else 0
    filled = int(PRECISION * 50 * pct)
    bar = "█" * filled + "░" * (50 - filled)
    elapsed = time.time() - _progress.start if hasattr(_progress, "start") else 0
    eta = (elapsed / current * (total - current)) if current > 0 else 0
    print(f"\r  {prefix} |{bar}| {current}/{total} ({pct*100:.0f}%) ETA {eta:.0f}s {suffix}  ", end="", flush=True)
    if current >= total:
        print()


_progress.start = time.time()


def _print_header(title: str) -> None:
    """打印阶段标题"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════
# Phase 1: Railway 生产环境数据采集
# ══════════════════════════════════════════════════════════════

async def phase1_collect() -> tuple:
    """调用 Railway /api/rag/query 采集 192 条 QA 数据 + 流式 TTFT/TPOT"""
    import httpx
    from app.rag.test_data import TEST_QA_PAIRS

    _print_header(f"Phase 1: Railway 数据采集 ({len(TEST_QA_PAIRS)} queries)")
    _progress.start = time.time()
    _progress(0, len(TEST_QA_PAIRS), prefix="采集进度")

    async with httpx.AsyncClient(timeout=60) as client:
        # 健康检查
        resp = await client.get(f"{BASE_URL}/api/health")
        health = resp.json()
        print(f"  模型: {health.get('model')} | 索引: {health.get('index_ready')}")

        raw_results = []
        latencies = []

        for i, qa in enumerate(TEST_QA_PAIRS):
            query = qa["question"]
            source_article = qa.get("source_article", "")
            expected_answer = qa.get("answer", "")
            is_negative = source_article == "none" or qa.get("type") == "negative"

            start = time.perf_counter()
            try:
                resp = await client.post(
                    f"{BASE_URL}/api/rag/query",
                    json={"query": query, "top_k": 10},
                )
                latency_ms = (time.perf_counter() - start) * 1000
                latencies.append(latency_ms)

                if resp.status_code == 200:
                    data = resp.json()
                    raw_results.append({
                        "id": qa["id"],
                        "query": query,
                        "expected_answer": expected_answer,
                        "expected_source": source_article,
                        "actual_answer": data.get("answer", ""),
                        "actual_sources": [
                            {"title": s.get("title", ""), "slug": s.get("slug", ""),
                             "score": s.get("score", 0),
                             "chunk_text": s.get("chunk_text_snippet", s.get("chunk", ""))[:200]}
                            for s in data.get("sources", [])[:5]
                        ],
                        "latency_ms": round(latency_ms),
                        "is_negative": is_negative,
                        "type": qa.get("type", ""),
                        "difficulty": qa.get("difficulty", ""),
                    })
                else:
                    raw_results.append({
                        "id": qa["id"], "query": query, "expected_answer": expected_answer,
                        "expected_source": source_article, "actual_answer": "", "actual_sources": [],
                        "latency_ms": round(latency_ms), "is_negative": is_negative,
                        "type": qa.get("type", ""), "difficulty": qa.get("difficulty", ""),
                        "error": f"HTTP {resp.status_code}",
                    })
            except Exception as e:
                latency_ms = (time.perf_counter() - start) * 1000
                raw_results.append({
                    "id": qa["id"], "query": query, "expected_answer": expected_answer,
                    "expected_source": source_article, "actual_answer": "", "actual_sources": [],
                    "latency_ms": round(latency_ms), "is_negative": is_negative,
                    "type": qa.get("type", ""), "difficulty": qa.get("difficulty", ""),
                    "error": str(e),
                })

            _progress(i + 1, len(TEST_QA_PAIRS), prefix="采集进度",
                      suffix=f"{latency_ms:.0f}ms")
            await asyncio.sleep(0.3)

        # ── TTFT/TPOT 流式采样（每 5 条取 1 条）──
        _print_header("Phase 1b: 流式延迟测量 (TTFT/TPOT, 采样 20%)")
        sample_indices = list(range(0, len(TEST_QA_PAIRS), 5))
        _progress.start = time.time()
        _progress(0, len(sample_indices), prefix="流式测量")

        ttft_list, tpot_list = [], []
        for si, idx in enumerate(sample_indices):
            query = TEST_QA_PAIRS[idx]["question"]
            try:
                stream_start = time.perf_counter()
                first_token_time = None
                last_token_time = None
                token_count = 0

                async with client.stream(
                    "POST", f"{BASE_URL}/api/rag/query/stream",
                    json={"query": query, "top_k": 3}, timeout=60,
                ) as stream_resp:
                    async for line in stream_resp.aiter_lines():
                        if line.startswith("data: "):
                            if first_token_time is None:
                                first_token_time = time.perf_counter()
                                ttft_ms = (first_token_time - stream_start) * 1000
                                ttft_list.append(ttft_ms)
                            last_token_time = time.perf_counter()
                            token_count += 1

                if first_token_time and last_token_time and token_count > 1:
                    tpot_ms = ((last_token_time - first_token_time) / token_count) * 1000
                    tpot_list.append(tpot_ms)
            except Exception:
                pass

            _progress(si + 1, len(sample_indices), prefix="流式测量")
            await asyncio.sleep(0.3)

    # ── 计算统计 ──
    _print_header("Phase 1c: 检索质量统计")

    positive_hits = {3: 0, 5: 0, 10: 0}
    positive_total, negative_correct, negative_total = 0, 0, 0
    mrr_scores, answer_has_content = [], 0

    for r in raw_results:
        if r.get("error"):
            continue
        answer = r["actual_answer"]
        sources = r["actual_sources"]
        source_article = r["expected_source"]

        if answer and len(answer) > 10:
            answer_has_content += 1

        if r["is_negative"]:
            negative_total += 1
            # 负例被正确拒绝：无 sources 或答案含"超出"/"未提及"
            rejected = (not sources or "超出" in answer or "未提及" in answer
                        or "outside" in answer.lower() or "not mentioned" in answer.lower()
                        or len(answer) < 30)
            if rejected:
                negative_correct += 1
        else:
            positive_total += 1
            slugs = [s.get("slug", "") for s in sources]
            for k in [3, 5, 10]:
                if any(source_article.lower() in s.lower() for s in slugs[:k]):
                    positive_hits[k] += 1
            rr = 0
            for rank, slug in enumerate(slugs[:10], 1):
                if source_article.lower() in slug.lower():
                    rr = 1.0 / rank
                    break
            mrr_scores.append(rr)

    n_lat = len(lat_sorted := sorted(latencies))
    latency_stats = {
        "e2e": {
            "mean_ms": round(statistics.mean(lat_sorted), 1),
            "p50_ms": round(lat_sorted[n_lat // 2], 1),
            "p90_ms": round(lat_sorted[int(n_lat * 0.9)], 1),
            "p99_ms": round(lat_sorted[min(int(n_lat * 0.99), n_lat - 1)], 1),
            "min_ms": round(lat_sorted[0], 1),
            "max_ms": round(lat_sorted[-1], 1),
            "samples": n_lat,
        },
    }
    if ttft_list:
        ts = sorted(ttft_list)
        latency_stats["ttft"] = {
            "mean_ms": round(statistics.mean(ts), 1),
            "p50_ms": round(ts[len(ts) // 2], 1),
            "p90_ms": round(ts[int(len(ts) * 0.9)], 1),
            "samples": len(ts),
        }
    if tpot_list:
        latency_stats["tpot"] = {
            "mean_ms": round(statistics.mean(tpot_list), 1),
            "p50_ms": round(sorted(tpot_list)[len(tpot_list) // 2], 1),
            "samples": len(tpot_list),
        }

    recall = {k: positive_hits[k] / positive_total if positive_total > 0 else 0 for k in [3, 5, 10]}
    mrr = statistics.mean(mrr_scores) if mrr_scores else 0
    neg_rate = negative_correct / negative_total if negative_total > 0 else 0
    answer_comp = answer_has_content / len(raw_results) if raw_results else 0

    print(f"  Recall@3:     {recall[3]*100:.1f}% ({positive_hits[3]}/{positive_total})")
    print(f"  Recall@5:     {recall[5]*100:.1f}% ({positive_hits[5]}/{positive_total})")
    print(f"  Recall@10:    {recall[10]*100:.1f}% ({positive_hits[10]}/{positive_total})")
    print(f"  MRR:          {mrr:.3f}")
    print(f"  Neg Detection:{neg_rate*100:.1f}% ({negative_correct}/{negative_total})")
    print(f"  Answer Comp:  {answer_comp*100:.1f}% ({answer_has_content}/{len(raw_results)})")
    print()
    print(f"  E2E P50:      {latency_stats['e2e']['p50_ms']:.0f}ms")
    print(f"  E2E P99:      {latency_stats['e2e']['p99_ms']:.0f}ms")
    if "ttft" in latency_stats:
        print(f"  TTFT P50:     {latency_stats['ttft']['p50_ms']:.0f}ms")
    if "tpot" in latency_stats:
        print(f"  TPOT mean:    {latency_stats['tpot']['mean_ms']:.1f}ms/tok")

    # ── 保存 ──
    ts = time.strftime("%Y%m%d_%H%M%S")
    raw_path = DATA_DIR / f"benchmark_raw_{ts}.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_results, f, ensure_ascii=False, indent=2)

    summary = {
        "timestamp": ts,
        "model": health.get("model", "unknown"),
        "retrieval": {
            "recall_at_3": recall[3], "recall_at_5": recall[5], "recall_at_10": recall[10],
            "mrr": mrr, "negative_detection_rate": neg_rate, "answer_completeness": answer_comp,
        },
        "latency": latency_stats,
        "total_queries": len(raw_results),
    }
    summary_path = DATA_DIR / f"benchmark_summary_{ts}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n  原始数据: {raw_path}")
    print(f"  摘要数据: {summary_path}")
    return raw_path, summary_path


# ══════════════════════════════════════════════════════════════
# Phase 2: 本地 LLM-as-Judge 评估
# ══════════════════════════════════════════════════════════════

def phase2_evaluate(raw_path: Path = None) -> Path:
    """本地 LLM-as-Judge: Faithfulness + Answer Relevancy. 返回 eval 文件路径。"""
    _print_header("Phase 2: 本地 LLM-as-Judge 评估")

    # 加载 raw 数据
    if raw_path is None:
        raw_files = sorted(DATA_DIR.glob("benchmark_raw_*.json"))
        if not raw_files:
            print("  ERROR: 无 raw 数据，先运行 --phase 1")
            sys.exit(1)
        raw_path = raw_files[-1]

    print(f"  数据源: {raw_path}")
    with open(raw_path, encoding="utf-8") as f:
        raw_data = json.load(f)

    # 筛选可评估样本
    eval_candidates = [
        r for r in raw_data
        if r.get("actual_answer") and len(r.get("actual_answer", "")) > 20
        and not r.get("is_negative") and not r.get("error")
    ]
    print(f"  总查询: {len(raw_data)} | 可评估: {len(eval_candidates)}")

    random.seed(42)
    sample = random.sample(eval_candidates, min(SAMPLE_N, len(eval_candidates)))
    print(f"  采样数: {len(sample)}")
    _progress.start = time.time()

    # 初始化 Judge
    api_key = _load_api_key()
    if not api_key:
        print("  ERROR: 未找到 API Key，请设置 .env 中的 DASHSCOPE_API_KEY")
        sys.exit(1)

    from openai import OpenAI
    judge = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

    def _judge(prompt: str) -> float:
        try:
            resp = judge.chat.completions.create(
                model="qwen3.5-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0, max_tokens=10,
            )
            return float(resp.choices[0].message.content.strip())
        except Exception as e:
            print(f"\n  Judge error: {e}")
            return 0.5

    faith_scores, rel_scores, details = [], [], []

    for i, r in enumerate(sample):
        query = r["query"]
        answer = r["actual_answer"]
        sources = r.get("actual_sources", [])
        context = " ".join(s.get("chunk_text", "") for s in sources[:5])

        faith_prompt = (
            f"你是一个RAG系统评估专家。判断以下回答是否忠实于检索到的上下文。\n\n"
            f"查询：{query}\n检索到的上下文（摘要）：{context[:800]}\n"
            f"生成的回答：{answer[:300]}\n\n"
            f"评分标准：\n- 1.0：完全基于上下文，没有幻觉\n"
            f"- 0.7：基本基于上下文，有少量推测\n"
            f"- 0.5：部分基于上下文，有明显推测\n"
            f"- 0.3：大部分是幻觉\n- 0.0：完全是幻觉\n\n只回答一个数字（0-1）。"
        )
        rel_prompt = (
            f"你是一个RAG系统评估专家。判断以下回答是否切题。\n\n"
            f"查询：{query}\n生成的回答：{answer[:300]}\n\n"
            f"评分标准：\n- 1.0：完全切题\n- 0.7：基本切题\n"
            f"- 0.5：部分切题\n- 0.3：大部分偏题\n- 0.0：完全不相关\n\n只回答一个数字（0-1）。"
        )

        f_score = _judge(faith_prompt)
        r_score = _judge(rel_prompt)
        faith_scores.append(f_score)
        rel_scores.append(r_score)
        details.append({"id": r["id"], "query": query[:60], "faithfulness": f_score, "relevancy": r_score})

        _progress(i + 1, len(sample), prefix="评估进度",
                  suffix=f"F={f_score:.2f} R={r_score:.2f}")
        time.sleep(0.5)

    # ── 汇总 ──
    avg_f = statistics.mean(faith_scores)
    avg_r = statistics.mean(rel_scores)
    pass_count = sum(1 for f, r in zip(faith_scores, rel_scores) if f >= 0.7 and r >= 0.7)

    print()
    print(f"  Faithfulness:     {avg_f:.3f} (target: >=0.70) {'✅' if avg_f >= 0.7 else '❌'}")
    print(f"  Answer Relevancy: {avg_r:.3f} (target: >=0.75) {'✅' if avg_r >= 0.75 else '❌'}")
    print(f"  通过率:           {pass_count}/{len(sample)} ({pass_count/len(sample)*100:.0f}%)")

    # 保存
    summary_files = sorted(DATA_DIR.glob("benchmark_summary_*.json"))
    if summary_files:
        with open(summary_files[-1], encoding="utf-8") as f:
            summary = json.load(f)
    else:
        summary = {}

    summary["generation_quality"] = {
        "faithfulness": round(avg_f, 3),
        "answer_relevancy": round(avg_r, 3),
        "samples": len(sample),
        "pass_rate": round(pass_count / len(sample), 3),
        "details": details,
    }

    eval_path = DATA_DIR / f"benchmark_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  评估结果: {eval_path}")
    return eval_path


# ══════════════════════════════════════════════════════════════
# Phase 3: 汇总 6 维报告 + 历史对比
# ══════════════════════════════════════════════════════════════

def phase3_report(summary_path: Path = None, eval_path: Path = None) -> None:
    """汇总生成 6 维 Benchmark 报告"""
    _print_header("Phase 3: 汇总报告")

    # 加载 summary：优先使用传入的路径，否则找最新文件
    if summary_path is None:
        summary_files = sorted(DATA_DIR.glob("benchmark_summary_*.json"))
        summary_path = summary_files[-1] if summary_files else None
    if eval_path is None:
        eval_files = sorted(DATA_DIR.glob("benchmark_eval_*.json"))
        eval_path = eval_files[-1] if eval_files else None

    if not summary_path or not summary_path.exists():
        print("  ERROR: 无 summary 数据")
        return

    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    if eval_path and eval_path.exists():
        with open(eval_path, encoding="utf-8") as f:
            eval_data = json.load(f)
        gq = eval_data.get("generation_quality", {})
    else:
        gq = {}

    ret = summary.get("retrieval", {})
    lat = summary.get("latency", {})
    e2e = lat.get("e2e", {})
    ttft = lat.get("ttft", {})
    tpot = lat.get("tpot", {})

    # ── 6 维评分 ──
    THRESHOLDS = {
        "recall_5": 0.95, "mrr": 0.85, "neg_detect": 0.80,
        "faith": 0.70, "relevancy": 0.75, "answer_comp": 0.90,
        "ttft_p50": 2000, "e2e_p50": 5000, "tpot": 100,
    }

    def _pass(val, threshold, higher_better=True):
        return val >= threshold if higher_better else val <= threshold

    print(f"  模型: {summary.get('model', 'unknown')}")
    print(f"  时间: {summary.get('timestamp', 'unknown')}")
    print()
    print(f"  {'维度':<25} {'当前值':>10} {'目标值':>10} {'状态':>4}")
    print(f"  {'-'*55}")

    rows = [
        ("1. 检索质量", [
            ("Recall@5", f"{ret.get('recall_at_5',0)*100:.1f}%", ">=95%", _pass(ret.get('recall_at_5',0), THRESHOLDS['recall_5'])),
            ("MRR", f"{ret.get('mrr',0):.3f}", ">=0.85", _pass(ret.get('mrr',0), THRESHOLDS['mrr'])),
        ]),
        ("2. 生成质量", [
            ("Faithfulness", f"{gq.get('faithfulness',0):.3f}", ">=0.70", _pass(gq.get('faithfulness',0), THRESHOLDS['faith'])),
            ("Answer Relevancy", f"{gq.get('answer_relevancy',0):.3f}", ">=0.75", _pass(gq.get('answer_relevancy',0), THRESHOLDS['relevancy'])),
            ("Negative Detection", f"{ret.get('negative_detection_rate',0)*100:.1f}%", ">=80%", _pass(ret.get('negative_detection_rate',0), THRESHOLDS['neg_detect'])),
            ("Answer Completeness", f"{ret.get('answer_completeness',0)*100:.1f}%", ">=90%", _pass(ret.get('answer_completeness',0), THRESHOLDS['answer_comp'])),
        ]),
        ("3. 延迟性能", [
            ("TTFT P50", f"{ttft.get('p50_ms',0):.0f}ms", "<=2000ms", _pass(ttft.get('p50_ms',9999), THRESHOLDS['ttft_p50'], False)),
            ("TPOT mean", f"{tpot.get('mean_ms',0):.1f}ms/tok", "<=100ms", _pass(tpot.get('mean_ms',9999), THRESHOLDS['tpot'], False)),
            ("E2E P50", f"{e2e.get('p50_ms',0):.0f}ms", "<=5000ms", _pass(e2e.get('p50_ms',9999), THRESHOLDS['e2e_p50'], False)),
            ("E2E P99", f"{e2e.get('p99_ms',0):.0f}ms", "-", True),
        ]),
    ]

    for section_name, metrics in rows:
        print(f"\n  {section_name}")
        for name, value, target, ok in metrics:
            status = "✅" if ok else "❌"
            print(f"    {name:<23} {value:>10}  {target:>8}  {status}")

    # ── 保存最终报告 ──
    report_path = DATA_DIR / f"benchmark_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "model": summary.get("model"),
        "retrieval": ret,
        "generation": gq,
        "latency": lat,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: {report_path}")


# ══════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="统一 RAG Benchmark 测试")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], help="仅运行指定阶段（默认全部）")
    args = parser.parse_args()

    print()
    print("┌─────────────────────────────────────────────┐")
    print("│       Aureon RAG Benchmark — 统一测试        │")
    print("└─────────────────────────────────────────────┘")

    start = time.time()
    raw_path = None
    summary_path = None
    eval_out_path = None

    if args.phase is None or args.phase == 1:
        raw_path, summary_path = asyncio.run(phase1_collect())

    if args.phase is None or args.phase == 2:
        eval_out_path = phase2_evaluate(raw_path)

    if args.phase is None or args.phase == 3:
        phase3_report(summary_path, eval_out_path)

    elapsed = time.time() - start
    _print_header(f"全部完成 (耗时 {elapsed:.0f}s)")


if __name__ == "__main__":
    main()
