#!/usr/bin/env python3
"""Quick 10-query RAG benchmark against Railway production.

Usage:
  python tests/benchmark_railway.py                     # 测当前生产
  python tests/benchmark_railway.py --label qwen3       # 带标签输出
"""

import sys, os, time, statistics, json, asyncio, httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RAILWAY_URL = "https://aureon-production-659a.up.railway.app"
# Auth token: pass an admin JWT (or any token with >=VIEWER role for /api/rag/query).
# Generate from Railway JWT_SECRET, or fetch a short-lived support_ws token via
# POST /api/v1/support/session. Never hardcode tokens in source.
JWT_TOKEN = os.environ.get("AUREON_RAILWAY_JWT")
if not JWT_TOKEN:
    sys.exit("Error: AUREON_RAILWAY_JWT not set. Export an admin/VIEWER JWT, e.g.\n"
             "  export AUREON_RAILWAY_JWT=eyJ...  (from Railway JWT_SECRET)")
HEADERS = {"Authorization": f"Bearer {JWT_TOKEN}", "Content-Type": "application/json"}

TEST_QUERIES = [
    "如何使用Python实现多线程爬虫？",
    "AI如何提升机器人智能？",
    "Transformer模型self-attention机制的原理是什么？",
    "What is the difference between REST and GraphQL?",
    "Docker和Kubernetes的区别是什么？",
    "How does vector database indexing work?",
    "机器学习中过拟合的解决方法",
    "Explain the CAP theorem in distributed systems",
    "什么是边缘计算？",
    "RAG系统中embedding模型的作用是什么？",
]

async def test_one(client, query, idx):
    t0 = time.perf_counter()
    try:
        resp = await client.post(f"{RAILWAY_URL}/api/rag/query", json={"query": query, "top_k": 3}, headers=HEADERS, timeout=30.0)
        t1 = time.perf_counter()
        elapsed = t1 - t0
        data = resp.json() if resp.is_success else {"error": resp.status_code, "text": resp.text[:200]}
        return {"idx": idx, "query": query[:40], "success": resp.is_success, "elapsed": elapsed, "data": data}
    except Exception as e:
        return {"idx": idx, "query": query[:40], "success": False, "elapsed": time.perf_counter() - t0, "error": str(e)}

async def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "current"
    print(f"\n  🚄 Railway Benchmark — {label}")
    print(f"  Target: {RAILWAY_URL}")
    print(f"  Queries: {len(TEST_QUERIES)}")

    # First warmup
    async with httpx.AsyncClient() as c:
        try:
            await c.post(f"{RAILWAY_URL}/api/rag/query", json={"query": "warmup", "top_k": 1}, headers=HEADERS, timeout=30.0)
        except:
            pass

    async with httpx.AsyncClient() as c:
        tasks = [test_one(c, q, i) for i, q in enumerate(TEST_QUERIES)]
        results = await asyncio.gather(*tasks)

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    elapsed = [r["elapsed"] for r in successes]

    print(f"\n  {'='*55}")
    print(f"  Results — {label}")
    print(f"  {'='*55}")
    print(f"  {'#':<4} {'Query':<35} {'Time':<8} {'Result'}")
    print(f"  {'─'*55}")
    for r in results:
        status = "✅" if r["success"] else "❌"
        q_short = r["query"] if len(r["query"]) <= 34 else r["query"][:31]+"..."
        if r["success"]:
            data = r["data"]
            sources = data.get("sources", data.get("metadata", data.get("results", [])))
            src_count = len(sources) if isinstance(sources, (list, tuple)) else 1
            print(f"  {r['idx']:<4} {q_short:<35} {r['elapsed']:<8.2f}s {status} ({src_count} src)")
        else:
            err = r.get("error", r.get("data", ""))
            print(f"  {r['idx']:<4} {q_short:<35} {r['elapsed']:<8.2f}s ❌ {str(err)[:40]}")

    if elapsed:
        p50 = statistics.median(elapsed)
        p95 = sorted(elapsed)[int(len(elapsed)*0.95)]
        avg = statistics.mean(elapsed)
        print(f"\n  {'─'*55}")
        print(f"  Summary ({len(successes)}/{len(results)} success)")
        print(f"    Avg:  {avg:.2f}s")
        print(f"    P50:  {p50:.2f}s")
        print(f"    P95:  {p95:.2f}s")
        print(f"    Min:  {min(elapsed):.2f}s")
        print(f"    Max:  {max(elapsed):.2f}s")

    if failures:
        print(f"\n  ⚠️  Failures: {len(failures)}")
        for f in failures:
            print(f"    #{f['idx']} {f['query']}: {f.get('error','')}")

    # Save
    report = {
        "label": label,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results), "success": len(successes), "fail": len(failures),
        "avg_s": round(statistics.mean(elapsed), 3) if elapsed else 0,
        "p50_s": round(statistics.median(elapsed), 3) if elapsed else 0,
        "p95_s": round(sorted(elapsed)[int(len(elapsed)*0.95)], 3) if len(elapsed) >= 5 else 0,
        "min_s": round(min(elapsed), 3) if elapsed else 0,
        "max_s": round(max(elapsed), 3) if elapsed else 0,
        "queries": [{"idx": r["idx"], "query": r["query"], "elapsed": round(r["elapsed"], 3), "success": r["success"]} for r in results],
    }
    out = Path(__file__).parent / f"benchmark_railway_{label}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📁 Saved: {out}")

if __name__ == "__main__":
    asyncio.run(main())
