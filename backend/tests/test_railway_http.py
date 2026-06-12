#!/usr/bin/env python3
"""HTTP-based RAG test against Railway deployment.

Tests the live API endpoints to measure real-world performance.
注意：不对生产环境进行并发负载测试，并发测试仅在本地进行。
"""
import json
import statistics
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

RAILWAY_URL = "https://aureon-production-1247.up.railway.app"

# Test queries covering different types
TEST_QUERIES = [
    # factual
    "什么是 RAG？",
    "LangChain 是什么？",
    "Embedding 模型有哪些？",
    # reasoning
    "混合检索为什么比纯向量检索效果好？",
    "BM25 和向量搜索各自擅长什么？",
    # cross-article
    "RAG 和 Agent 有什么区别？",
    "LangChain 和 LlamaIndex 哪个更适合 RAG？",
    # how-to
    "如何优化 DeepSeek 的缓存命中率？",
    "怎么部署一个 chatbot 到 Railway？",
    # synthesis
    "总结一下构建 RAG 系统需要考虑哪些方面？",
    # negative (unanswerable)
    "Aureon 的 SaaS 定价方案是什么？",
    "作者毕业于哪所大学？",
]


def http_get(path, timeout=30):
    """GET request, returns (status, body, timing_ms)."""
    url = f"{RAILWAY_URL}{path}"
    start = time.perf_counter()
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            elapsed = (time.perf_counter() - start) * 1000
            return resp.status, json.loads(body) if body else {}, elapsed
    except HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return e.code, {}, elapsed
    except (URLError, Exception) as e:
        elapsed = (time.perf_counter() - start) * 1000
        return 0, {"error": str(e)}, elapsed


def http_post_json(path, data, timeout=60):
    """POST JSON request, returns (status, body, timing_ms)."""
    url = f"{RAILWAY_URL}{path}"
    payload = json.dumps(data).encode()
    start = time.perf_counter()
    try:
        req = Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            elapsed = (time.perf_counter() - start) * 1000
            return resp.status, json.loads(body) if body else {}, elapsed
    except HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000
        body = e.read().decode() if e.fp else ""
        try:
            body = json.loads(body)
        except Exception:
            body = {"raw": body[:500]}
        return e.code, body, elapsed
    except (URLError, Exception) as e:
        elapsed = (time.perf_counter() - start) * 1000
        return 0, {"error": str(e)}, elapsed


def http_post_sse(path, data, timeout=120):
    """POST and parse SSE stream. Returns (status, events_list, timing_ms, ttft_ms)."""
    url = f"{RAILWAY_URL}{path}"
    payload = json.dumps(data).encode()
    start = time.perf_counter()
    ttft = None
    events = []
    try:
        req = Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        })
        with urlopen(req, timeout=timeout) as resp:
            status = resp.status
            buffer = ""
            for chunk in iter(lambda: resp.read(1024), b""):
                if ttft is None and chunk:
                    ttft = (time.perf_counter() - start) * 1000
                buffer += chunk.decode(errors="replace")
                while "\n\n" in buffer:
                    raw_event, buffer = buffer.split("\n\n", 1)
                    event = {}
                    for line in raw_event.strip().split("\n"):
                        if line.startswith("data: "):
                            event["data"] = line[6:]
                        elif line.startswith("event: "):
                            event["event"] = line[7:]
                    if event:
                        events.append(event)
            # flush remaining
            if buffer.strip():
                event = {}
                for line in buffer.strip().split("\n"):
                    if line.startswith("data: "):
                        event["data"] = line[6:]
                    elif line.startswith("event: "):
                        event["event"] = line[7:]
                if event:
                    events.append(event)
            elapsed = (time.perf_counter() - start) * 1000
            return status, events, elapsed, ttft or elapsed
    except (URLError, Exception) as e:
        elapsed = (time.perf_counter() - start) * 1000
        return 0, [{"error": str(e)}], elapsed, elapsed


def percentile(data, p):
    if not data:
        return 0
    sorted_d = sorted(data)
    k = (len(sorted_d) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_d):
        return sorted_d[-1]
    return sorted_d[f] + (k - f) * (sorted_d[c] - sorted_d[f])


# ============================================================
# Phase 1: Health & System Status
# ============================================================
def test_health():
    print("=" * 60)
    print("PHASE 1: Health & System Status")
    print("=" * 60)

    # /api/health
    status, body, ms = http_get("/api/health")
    print("\n  GET /api/health")
    print(f"    Status: {status} | Latency: {ms:.0f}ms")
    print(f"    Model: {body.get('model', 'N/A')}")
    print(f"    Index ready: {body.get('index_ready', 'N/A')}")
    print(f"    Tools: {body.get('tools', [])}")

    # /api/rag/health
    status, body, ms = http_get("/api/rag/health")
    print("\n  GET /api/rag/health")
    print(f"    Status: {status} | Latency: {ms:.0f}ms")
    if status == 200:
        print(f"    Body: {json.dumps(body, ensure_ascii=False, indent=6)}")

    # /metrics (prometheus)
    status, _, ms = http_get("/metrics", timeout=10)
    print("\n  GET /metrics (Prometheus)")
    print(f"    Status: {status} | Latency: {ms:.0f}ms")
    print(f"    Available: {'Yes' if status == 200 else 'No'}")

    return body if status == 200 else {}


# ============================================================
# Phase 2: Analytics Endpoints
# ============================================================
def test_analytics():
    print("\n" + "=" * 60)
    print("PHASE 2: Analytics Endpoints")
    print("=" * 60)

    endpoints = [
        "/api/rag/analytics/usage",
        "/api/rag/analytics/latency",
        "/api/rag/analytics/tokens",
        "/api/rag/analytics/cache",
        "/api/observability/stats",
    ]

    results = {}
    for ep in endpoints:
        status, body, ms = http_get(ep)
        print(f"\n  GET {ep}")
        print(f"    Status: {status} | Latency: {ms:.0f}ms")
        if status == 200 and body:
            # Show key metrics compactly
            for k, v in body.items():
                if isinstance(v, (int, float, str, bool)):
                    print(f"    {k}: {v}")
                elif isinstance(v, dict) and len(v) <= 5:
                    print(f"    {k}: {json.dumps(v, ensure_ascii=False)}")
            results[ep] = body
        elif status != 200:
            print(f"    Body: {json.dumps(body, ensure_ascii=False)[:200]}")

    return results


# ============================================================
# Phase 3: RAG Query Latency (sync)
# ============================================================
def test_rag_sync():
    print("\n" + "=" * 60)
    print("PHASE 3: RAG Sync Query Latency")
    print("=" * 60)

    latencies = []
    results_detail = []

    for i, q in enumerate(TEST_QUERIES):
        data = {"query": q, "top_k": 3}
        status, body, ms = http_post_json("/api/rag/query", data, timeout=60)
        latencies.append(ms)

        has_answer = bool(body.get("answer"))
        sources = body.get("sources", [])
        cache_hit = body.get("cache_hit", False)

        result = {
            "query": q[:30],
            "status": status,
            "latency_ms": round(ms, 1),
            "has_answer": has_answer,
            "num_sources": len(sources),
            "cache_hit": cache_hit,
        }
        results_detail.append(result)

        hit_tag = " [CACHE]" if cache_hit else ""
        print(f"  [{i+1:2d}/{len(TEST_QUERIES)}] {ms:7.0f}ms | sources={len(sources)} | answer={'Y' if has_answer else 'N'}{hit_tag} | {q[:40]}")

    if latencies:
        print("\n  --- Sync Query Summary ---")
        print(f"  Total queries: {len(latencies)}")
        print(f"  Mean:   {statistics.mean(latencies):7.0f}ms")
        print(f"  Median: {statistics.median(latencies):7.0f}ms")
        print(f"  P90:    {percentile(latencies, 90):7.0f}ms")
        print(f"  P99:    {percentile(latencies, 99):7.0f}ms")
        print(f"  Min:    {min(latencies):7.0f}ms")
        print(f"  Max:    {max(latencies):7.0f}ms")
        print(f"  Std:    {statistics.stdev(latencies):7.0f}ms" if len(latencies) > 1 else "")

        cache_hits = sum(1 for r in results_detail if r["cache_hit"])
        print(f"  Cache hits: {cache_hits}/{len(latencies)} ({cache_hits/len(latencies)*100:.0f}%)")

    return latencies, results_detail


# ============================================================
# Phase 4: RAG Streaming Latency (SSE)
# ============================================================
def test_rag_stream():
    print("\n" + "=" * 60)
    print("PHASE 4: RAG Streaming (SSE) Latency")
    print("=" * 60)

    stream_latencies = []
    ttfts = []
    text_lengths = []

    # Use subset for streaming (it's slower)
    stream_queries = TEST_QUERIES[:6]

    for i, q in enumerate(stream_queries):
        data = {"query": q, "top_k": 3}
        status, events, total_ms, ttft_ms = http_post_sse("/api/rag/query/stream", data, timeout=120)

        # Parse SSE events
        text_content = ""
        for ev in events:
            raw = ev.get("data", "")
            try:
                parsed = json.loads(raw)
                if parsed.get("type") == "text":
                    text_content += parsed.get("content", "")
                elif parsed.get("type") == "sources":
                    len(parsed.get("sources", []))
                elif parsed.get("type") == "done":
                    pass
            except json.JSONDecodeError:
                pass

        stream_latencies.append(total_ms)
        ttfts.append(ttft_ms)
        text_lengths.append(len(text_content))

        print(f"  [{i+1}/{len(stream_queries)}] TTFT={ttft_ms:6.0f}ms | Total={total_ms:7.0f}ms | chars={len(text_content):4d} | {q[:40]}")

    if stream_latencies:
        print("\n  --- Streaming Summary ---")
        print(f"  TTFT Mean:  {statistics.mean(ttfts):7.0f}ms")
        print(f"  TTFT P50:   {percentile(ttfts, 50):7.0f}ms")
        print(f"  TTFT P90:   {percentile(ttfts, 90):7.0f}ms")
        print(f"  Total Mean: {statistics.mean(stream_latencies):7.0f}ms")
        print(f"  Total P50:  {percentile(stream_latencies, 50):7.0f}ms")
        print(f"  Total P90:  {percentile(stream_latencies, 90):7.0f}ms")
        print(f"  Avg output: {statistics.mean(text_lengths):.0f} chars")

    return stream_latencies, ttfts


# ============================================================
# Phase 5: Network Overhead Analysis
# ============================================================
def test_network_overhead():
    print("\n" + "=" * 60)
    print("PHASE 6: Network Overhead Analysis")
    print("=" * 60)

    # Measure raw HTTP overhead with a simple GET
    overheads = []
    for _ in range(10):
        _, _, ms = http_get("/api/health")
        overheads.append(ms)

    print("  /api/health x10:")
    print(f"    Mean: {statistics.mean(overheads):.0f}ms | P50: {percentile(overheads, 50):.0f}ms | P99: {percentile(overheads, 99):.0f}ms")
    print(f"    Min: {min(overheads):.0f}ms | Max: {max(overheads):.0f}ms")

    # POST overhead
    post_overheads = []
    for _ in range(5):
        _, _, ms = http_post_json("/api/rag/query", {"query": "test", "top_k": 1}, timeout=30)
        post_overheads.append(ms)

    print("  /api/rag/query 'test' x5:")
    print(f"    Mean: {statistics.mean(post_overheads):.0f}ms | P50: {percentile(post_overheads, 50):.0f}ms")

    print(f"\n  Estimated network RTT (GET overhead): ~{statistics.mean(overheads):.0f}ms")
    print(f"  Estimated processing overhead (POST - GET): ~{statistics.mean(post_overheads) - statistics.mean(overheads):.0f}ms")


# ============================================================
# Main
# ============================================================
def main():
    print(f"Railway RAG Test - {RAILWAY_URL}")
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_results = {}

    # Phase 1: Health
    health = test_health()
    all_results["health"] = health

    # Phase 2: Analytics
    analytics = test_analytics()
    all_results["analytics"] = analytics

    # Phase 3: Sync queries
    sync_latencies, sync_details = test_rag_sync()
    all_results["sync"] = {
        "latencies": sync_latencies,
        "details": sync_details,
    }

    # Phase 4: Streaming
    stream_latencies, ttfts = test_rag_stream()
    all_results["stream"] = {
        "latencies": stream_latencies,
        "ttfts": ttfts,
    }

    # Phase 5: Network overhead
    test_network_overhead()

    # Save full results
    output_path = "backend/data/railway_test_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n\nResults saved to {output_path}")
    print(f"Finished at: {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
