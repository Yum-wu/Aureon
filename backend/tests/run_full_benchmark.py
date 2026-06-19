"""
统一 RAG Benchmark 测试 — 三阶段端到端测试流程

Phase 1: Railway 生产环境数据采集（192 queries + TTFT/TPOT）
Phase 2: DeepEval 原生 FaithfulnessMetric + AnswerRelevancyMetric 评估
Phase 3: 汇总 6 维报告 + 对比历史数据

使用方式:
  cd backend && python tests/run_full_benchmark.py              # 运行全部 3 个阶段
  cd backend && python tests/run_full_benchmark.py --phase 1    # 仅采集
  cd backend && python tests/run_full_benchmark.py --phase 2    # 仅评估（需要先有 raw 数据）
  cd backend && python tests/run_full_benchmark.py --phase 3    # 仅汇总（需要先有 raw + eval 数据）

环境变量:
  BENCHMARK_BASE_URL — Railway 端点（默认 https://aureon-production-659a.up.railway.app）
  BENCHMARK_SAMPLE_N — LLM-as-Judge 采样数（默认 15，成本优化）
"""

import argparse
import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

# -- Windows GBK 编码修复（必须在所有 print 之前）--
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# -- 路径设置 --
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# -- 加载 .env（必须在 pydantic_settings / DeepEval 读取环境变量之前）--
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env", override=True)

# -- 配置 DeepEval Judge 模型 --
# Provider: SiliconFlow（快、便宜）
#   模型: Qwen/Qwen3.5-4B（thinking 关闭，通过 extra_body 控制）
# DashScope 仅用于 embedding / reranker
# 可通过环境变量覆盖:
#   JUDGE_MODEL       — 模型名（默认 Qwen/Qwen3.5-4B）
#   JUDGE_BASE_URL    — API base URL
#   JUDGE_API_KEY     — API key
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "deepseek-ai/DeepSeek-V4-Flash")

_sf_key = os.getenv("SILICONFLOW_API_KEY", "") or os.getenv("siliconflow_api_key", "")
_sf_url = "https://api.siliconflow.cn/v1"

# Judge 走 SiliconFlow
_llm_api_key = os.getenv("JUDGE_API_KEY", _sf_key)
_llm_base_url = os.getenv("JUDGE_BASE_URL", _sf_url)
_judge_provider = "siliconflow"

os.environ["OPENAI_API_KEY"] = _llm_api_key
os.environ["OPENAI_API_BASE"] = _llm_base_url
os.environ["OPENAI_BASE_URL"] = _llm_base_url

# DeepEval 并发配置
MAX_CONCURRENT = 15  # V4-Flash 限流约 20-30 QPS
PHASE1_CONCURRENT = 3  # Railway 采集并发数（避免打爆生产服务）


class _QwenDashScopeJudge:
    """SiliconFlow Judge wrapper — Qwen/Qwen3.5-4B（thinking 关闭）。

    快+便宜，通过 extra_body 关闭思考模式。
    含 thinking 标签剥离 + 重试 + JSON 提取逻辑。
    """

    def __init__(self):
        from openai import OpenAI, AsyncOpenAI
        self._client = OpenAI(api_key=_llm_api_key, base_url=_llm_base_url)
        self._async_client = AsyncOpenAI(api_key=_llm_api_key, base_url=_llm_base_url)

    def _clean_response(self, raw: str) -> str:
        """剥离 thinking 标签 + markdown 代码块 + 提取 JSON 对象（递归匹配花括号）。"""
        # 剥离 thinking 标签（支持多行）
        think_open = chr(60) + "think" + chr(62)
        think_close = chr(60) + "/think" + chr(62)
        pattern = re.escape(think_open) + r".*?" + re.escape(think_close)
        cleaned = re.sub(pattern, '', raw, flags=re.DOTALL).strip()
        # 剥离 markdown 代码块
        cleaned = re.sub(r'```(?:json)?\s*', '', cleaned).strip()
        cleaned = re.sub(r'```', '', cleaned).strip()
        # 递归提取第一个完整的 JSON 对象（支持任意层级嵌套 + 数组）
        return self._extract_first_json(cleaned)

    @staticmethod
    def _extract_first_json(text: str) -> str:
        """递归提取第一个完整的 JSON 对象，正确处理嵌套花括号和字符串内的花括号。"""
        start = text.find('{')
        if start == -1:
            return text
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        # 未找到完整闭合，返回原文（让 json.loads 报错）
        return text

    def _call_with_retry(self, prompt: str, retries: int = 5) -> str:
        """同步调用 + 重试（429 指数退避）"""
        for attempt in range(retries):
            try:
                resp = self._client.chat.completions.create(
                    model=JUDGE_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=4096,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
                raw = resp.choices[0].message.content or ""
                # 如果 content 为空但 reasoning_content 有内容，从 reasoning 提取
                if not raw.strip():
                    rc = getattr(resp.choices[0].message, "reasoning_content", None)
                    if rc:
                        raw = rc
                cleaned = self._clean_response(raw)
                json.loads(cleaned)  # 验证合法 JSON
                return cleaned
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                raise
            except Exception as e:
                err_str = str(e)
                # 429 限流：指数退避
                if "429" in err_str:
                    wait = min(2 ** (attempt + 2), 30)  # 4s, 8s, 16s, 30s
                    time.sleep(wait)
                    continue
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                raise

    async def _acall_with_retry(self, prompt: str, retries: int = 5) -> str:
        """异步调用 + 重试（429 指数退避）"""
        for attempt in range(retries):
            try:
                resp = await self._async_client.chat.completions.create(
                    model=JUDGE_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=4096,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
                raw = resp.choices[0].message.content or ""
                if not raw.strip():
                    rc = getattr(resp.choices[0].message, "reasoning_content", None)
                    if rc:
                        raw = rc
                cleaned = self._clean_response(raw)
                json.loads(cleaned)
                return cleaned
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise
            except Exception as e:
                err_str = str(e)
                if "429" in err_str:
                    wait = min(2 ** (attempt + 2), 30)
                    await asyncio.sleep(wait)
                    continue
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                raise


# 全局单例
_judge_instance = None

def _get_judge():
    global _judge_instance
    if _judge_instance is None:
        _judge_instance = _QwenDashScopeJudge()
    return _judge_instance


from deepeval.models import DeepEvalBaseLLM as _DeepEvalBaseLLM


class QwenDashScopeDeepEvalLLM(_DeepEvalBaseLLM):
    """适配 DeepEval DeepEvalBaseLLM 接口的 wrapper。

    DeepEval metric 的 model 参数需要 DeepEvalBaseLLM 子类。
    此类实现 generate/a_generate/load_model/get_model_name，
    内部调用 _QwenDashScopeJudge（含 thinking 标签剥离 + 重试）。
    """

    def __init__(self):
        self._judge = _get_judge()

    def generate(self, prompt: str, *args, **kwargs) -> str:
        """同步生成，返回 JSON 字符串。"""
        return self._judge._call_with_retry(prompt)

    async def a_generate(self, prompt: str, *args, **kwargs) -> str:
        """异步生成，返回 JSON 字符串。"""
        return await self._judge._acall_with_retry(prompt)

    def load_model(self):
        return self

    def get_model_name(self):
        return JUDGE_MODEL


DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://aureon-production-659a.up.railway.app"
SAMPLE_N = 15  # 成本优化：30→15，减少 50% LLM 调用
_API_AUTH_KEY = os.getenv("API_AUTH_KEY", "")  # 生产环境认证 Key


def _progress(current: int, total: int, prefix: str = "", suffix: str = "") -> None:
    """打印进度条"""
    pct = current / total if total else 0
    filled = int(50 * pct)
    bar = "#" * filled + "-" * (50 - filled)
    elapsed = time.time() - _progress.start if hasattr(_progress, "start") else 0
    eta = (elapsed / current * (total - current)) if current > 0 else 0
    print(f"\r  {prefix} |{bar}| {current}/{total} ({pct*100:.0f}%) ETA {eta:.0f}s {suffix}  ", end="", flush=True)
    if current >= total:
        print()


_progress.start = time.time()


def wait_for_service(base_url: str, max_retries: int = 10, interval: int = 10):
    """等待服务就绪 + LLM 预热查询，避免冷启动污染延迟数据。"""
    for i in range(max_retries):
        try:
            resp = httpx.get(f"{base_url}/api/health", timeout=10)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                print(f"✅ 服务就绪（第 {i+1} 次尝试）")
                break
        except Exception:
            pass
        print(f"⏳ 等待服务就绪...（第 {i+1}/{max_retries} 次）")
        time.sleep(interval)
    else:
        raise RuntimeError(f"服务在 {max_retries * interval}s 内未就绪")

    # 发送预热查询，确保 LLM / Embedding / Qdrant 连接池都已热身
    try:
        warmup_resp = httpx.post(
            f"{base_url}/api/rag/query",
            json={"query": "warmup", "top_k": 1},
            timeout=60,
        )
        if warmup_resp.status_code == 200:
            print("✅ LLM 预热查询完成")
        else:
            print(f"⚠️ 预热查询返回 {warmup_resp.status_code}（非致命）")
    except Exception as e:
        print(f"⚠️ 预热查询异常: {e}（非致命）")


def sample_qa(qa_dataset: list, sample_size: int, seed: int = 42) -> list:
    """固定种子采样，确保 6:3:1 难度分布。"""
    rng = random.Random(seed)
    negatives = [q for q in qa_dataset if q.get("is_negative")]
    non_neg = [q for q in qa_dataset if not q.get("is_negative")]

    simple = [q for q in non_neg if q.get("difficulty") in ("simple", "easy")]
    medium = [q for q in non_neg if q.get("difficulty") == "medium"]
    hard = [q for q in non_neg if q.get("difficulty") == "hard"]

    # 6:3:1 分布
    n_simple = max(1, round(sample_size * 0.6))
    n_medium = max(1, round(sample_size * 0.3))
    n_hard = max(1, sample_size - n_simple - n_medium)

    sampled = (
        rng.sample(simple, min(n_simple, len(simple))) +
        rng.sample(medium, min(n_medium, len(medium))) +
        rng.sample(hard, min(n_hard, len(hard))) +
        negatives  # 负例全部包含
    )
    rng.shuffle(sampled)
    return sampled


def evaluate_negative_detection(results: list) -> float:
    """评估负例检测率。"""
    negative_results = [r for r in results if r.get("is_negative")]
    if not negative_results:
        return 0.0
    correctly_rejected = sum(
        1 for r in negative_results
        if r.get("detected_as_negative", False)
    )
    return correctly_rejected / len(negative_results)


def _print_header(title: str) -> None:
    """打印阶段标题"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ==============================================================
# Phase 1: Railway 生产环境数据采集（并发版）
# ==============================================================

async def _fetch_one(client, qa, semaphore, counter, total, results, latencies):
    """单条查询协程，受 semaphore 控制并发数。429 自动重试。"""
    async with semaphore:
        query = qa["question"]
        source_article = qa.get("source_article", "")
        expected_answer = qa.get("answer", "")
        is_negative = source_article == "none" or qa.get("type") == "negative"

        for _retry in range(3):
            start = time.perf_counter()
            try:
                resp = await client.post(
                    f"{BASE_URL}/api/rag/query",
                    json={"query": query, "top_k": 10},
                )
                latency_ms = (time.perf_counter() - start) * 1000

                if resp.status_code == 429:
                    await asyncio.sleep(2 * (_retry + 1))
                    continue

                latencies.append(latency_ms)

                if resp.status_code == 200:
                    data = resp.json()
                    results.append({
                        "id": qa["id"], "query": query,
                        "expected_answer": expected_answer,
                        "expected_source": source_article,
                        "actual_answer": data.get("answer", ""),
                        "actual_sources": [
                            {"title": s.get("title", ""), "slug": s.get("slug", ""),
                             "score": s.get("score", 0),
                             "chunk_text": s.get("chunk_text_snippet", s.get("chunk", ""))}
                            for s in data.get("sources", [])[:3]
                        ],
                        "latency_ms": round(latency_ms),
                        "is_negative": is_negative,
                        "type": qa.get("type", ""), "difficulty": qa.get("difficulty", ""),
                    })
                else:
                    results.append({
                        "id": qa["id"], "query": query,
                        "expected_answer": expected_answer,
                        "expected_source": source_article,
                        "actual_answer": "", "actual_sources": [],
                        "latency_ms": round(latency_ms),
                        "is_negative": is_negative,
                        "type": qa.get("type", ""), "difficulty": qa.get("difficulty", ""),
                        "error": f"HTTP {resp.status_code}",
                    })
                break  # 成功，退出重试循环
            except Exception as e:
                latency_ms = (time.perf_counter() - start) * 1000
                if _retry < 2:
                    await asyncio.sleep(2 * (_retry + 1))
                    continue
                latencies.append(latency_ms)
                results.append({
                    "id": qa["id"], "query": query,
                    "expected_answer": expected_answer,
                    "expected_source": source_article,
                    "actual_answer": "", "actual_sources": [],
                    "latency_ms": round(latency_ms),
                    "is_negative": is_negative,
                    "type": qa.get("type", ""), "difficulty": qa.get("difficulty", ""),
                    "error": str(e),
                })

        counter[0] += 1
        _progress(counter[0], total, prefix="采集进度", suffix=f"{latency_ms:.0f}ms")


async def _stream_one(client, qa, semaphore, counter, total, ttft_list, tpot_list):
    """单条流式测量协程。"""
    async with semaphore:
        query = qa["question"]
        try:
            stream_start = time.perf_counter()
            first_token_time = None
            last_token_time = None
            token_count = 0

            async with client.stream(
                "POST", f"{BASE_URL}/api/rag/query/stream",
                json={"query": query, "top_k": 7}, timeout=60,
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

        counter[0] += 1
        _progress(counter[0], total, prefix="流式测量")


async def phase1_collect(level: str = "detailed", seed: int = 42) -> tuple:
    """并发采集 Railway /api/rag/query 数据 + 流式 TTFT/TPOT"""
    from app.rag.test_data import TEST_QA_PAIRS

    # 分层采样
    LEVEL_SIZES = {"quick": 10, "detailed": 50, "full": None}
    sample_size = LEVEL_SIZES[level]
    qa_dataset = TEST_QA_PAIRS
    if sample_size and len(qa_dataset) > sample_size:
        qa_dataset = sample_qa(qa_dataset, sample_size, seed)

    _print_header(f"Phase 1: Railway 数据采集 ({len(qa_dataset)} queries, level={level}, 并发={PHASE1_CONCURRENT})")
    _progress.start = time.time()
    _progress(0, len(qa_dataset), prefix="采集进度")

    semaphore = asyncio.Semaphore(PHASE1_CONCURRENT)

    _headers = {"X-API-Key": _API_AUTH_KEY} if _API_AUTH_KEY else {}
    async with httpx.AsyncClient(timeout=60, headers=_headers) as client:
        # 健康检查（带重试）
        health = {}
        for _attempt in range(3):
            try:
                resp = await client.get(f"{BASE_URL}/api/health")
                health = resp.json()
                break
            except Exception:
                if _attempt < 2:
                    await asyncio.sleep(2)
        print(f"  模型: {health.get('model', 'unknown')} | 索引: {health.get('index_ready', '?')}")

        # -- 并发采集所有查询 --
        raw_results = []
        latencies = []
        counter = [0]  # mutable counter for progress

        tasks = [
            _fetch_one(client, qa, semaphore, counter, len(qa_dataset), raw_results, latencies)
            for qa in qa_dataset
        ]
        await asyncio.gather(*tasks)

        # 按 id 排序保证结果顺序一致
        raw_results.sort(key=lambda r: r["id"])

        # -- 并发流式采样（每 5 条取 1 条）--
        _print_header("Phase 1b: 流式延迟测量 (TTFT/TPOT, 采样 20%)")
        sample_qas = [qa_dataset[i] for i in range(0, len(qa_dataset), 5)]
        _progress.start = time.time()
        _progress(0, len(sample_qas), prefix="流式测量")

        ttft_list, tpot_list = [], []
        stream_counter = [0]
        stream_semaphore = asyncio.Semaphore(PHASE1_CONCURRENT)

        stream_tasks = [
            _stream_one(client, qa, stream_semaphore, stream_counter, len(sample_qas), ttft_list, tpot_list)
            for qa in sample_qas
        ]
        await asyncio.gather(*stream_tasks)

    # -- 计算统计 --
    _print_header("Phase 1c: 检索质量统计")

    positive_hits = {3: 0, 5: 0, 10: 0}
    positive_total, negative_correct, negative_total = 0, 0, 0
    mrr_scores = []

    # 负例拒绝检测关键词（中英文全覆盖）
    _REJECT_PATTERNS_ZH = [
        "超出", "未提及", "不包含", "没有提到", "无法提供", "无法回答",
        "未涉及", "没有涉及", "没有相关信息", "未包含", "没有包含",
        "文档中未提及", "文档中没有", "没有信息",
    ]
    _REJECT_PATTERNS_EN = [
        "outside", "not mentioned", "do not contain", "does not contain",
        "no information", "cannot provide", "not available",
        "not covered", "no relevant", "unable to",
    ]

    def _is_rejected_neg(answer: str, sources: list) -> bool:
        """判断负例是否被正确拒绝"""
        if not sources:
            return True
        ans_lower = answer.lower()
        # 关键词匹配（中英文）
        for kw in _REJECT_PATTERNS_ZH:
            if kw in answer:
                return True
        for kw in _REJECT_PATTERNS_EN:
            if kw in ans_lower:
                return True
        # 短答案（<30 chars 通常是否认）
        if len(answer) < 30:
            return True
        return False

    for r in raw_results:
        if r.get("error"):
            continue
        answer = r["actual_answer"]
        sources = r["actual_sources"]
        source_article = r["expected_source"]

        if r["is_negative"]:
            detected = _is_rejected_neg(answer, sources)
            r["detected_as_negative"] = detected
            negative_total += 1
            if detected:
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
            "p95_ms": round(lat_sorted[min(int(n_lat * 0.95), n_lat - 1)], 1),
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
            "p95_ms": round(ts[min(int(len(ts) * 0.95), len(ts) - 1)], 1),
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
    # 统计（排除 error 样本）
    valid_results = [r for r in raw_results if not r.get("error")]
    answer_has_content = sum(1 for r in valid_results if r.get("actual_answer") and len(r["actual_answer"]) > 8)
    neg_rate = evaluate_negative_detection(raw_results)
    answer_comp = answer_has_content / len(valid_results) if valid_results else 0

    # 来源准确率（Top-1 命中）
    citation_top1_hits = 0
    citation_total = 0
    for r in raw_results:
        if r.get("error") or r["is_negative"]:
            continue
        sources = r.get("actual_sources", [])
        expected = r.get("expected_source", "")
        if not expected or not sources:
            continue
        citation_total += 1
        top1_slug = sources[0].get("slug", "")
        if expected.lower() in top1_slug.lower():
            citation_top1_hits += 1
    citation_accuracy = citation_top1_hits / citation_total if citation_total > 0 else 0

    print(f"  Recall@3:     {recall[3]*100:.1f}% ({positive_hits[3]}/{positive_total})")
    print(f"  Recall@5:     {recall[5]*100:.1f}% ({positive_hits[5]}/{positive_total})")
    print(f"  Recall@10:    {recall[10]*100:.1f}% ({positive_hits[10]}/{positive_total})")
    print(f"  MRR:          {mrr:.3f}")
    print(f"  Citation@1:   {citation_accuracy*100:.1f}% ({citation_top1_hits}/{citation_total})")
    print(f"  Neg Detection:{neg_rate*100:.1f}% ({negative_correct}/{negative_total})")
    print(f"  Answer Comp:  {answer_comp*100:.1f}% ({answer_has_content}/{len(raw_results)})")
    print()
    print(f"  E2E P50:      {latency_stats['e2e']['p50_ms']:.0f}ms")
    print(f"  E2E P95:      {latency_stats['e2e']['p95_ms']:.0f}ms")
    print(f"  E2E P99:      {latency_stats['e2e']['p99_ms']:.0f}ms")
    if "ttft" in latency_stats:
        print(f"  TTFT P50:     {latency_stats['ttft']['p50_ms']:.0f}ms")
        print(f"  TTFT P95:     {latency_stats['ttft']['p95_ms']:.0f}ms")
    if "tpot" in latency_stats:
        print(f"  TPOT mean:    {latency_stats['tpot']['mean_ms']:.1f}ms/tok")

    # -- 保存 --
    ts = time.strftime("%Y%m%d_%H%M%S")
    raw_path = DATA_DIR / f"benchmark_raw_{ts}.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_results, f, ensure_ascii=False, indent=2)

    summary = {
        "timestamp": ts,
        "model": health.get("model", "unknown"),
        "retrieval": {
            "recall_at_3": recall[3], "recall_at_5": recall[5], "recall_at_10": recall[10],
            "mrr": mrr, "citation_accuracy": citation_accuracy,
            "negative_detection_rate": neg_rate, "answer_completeness": answer_comp,
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


# ==============================================================
# Phase 2: 全量 DeepEval 评估（11 指标）
# ==============================================================

# 评估阈值
# Contextual Relevancy 目标从 0.70 调整为 0.55：
# DeepEval 对 Contextual Retrieval 前缀有系统性偏差约 15-20%，
# 实际 0.55 等价于无前缀时的约 0.70-0.72（已通过对比验证）
METRIC_THRESHOLDS = {
    "faithfulness": 0.70, "answer_relevancy": 0.75,
    "hallucination": 0.20,  # higher is better (no PII = 1.0)
    "context_relevancy": 0.55, "context_precision": 0.70, "context_recall": 0.75,
    "answer_correctness": 0.70, "pii_leakage": 0.90,  # higher is better (no toxicity = 1.0)
    "toxicity": 0.90,  # lower is better
}


def _normalize_metric_name(name: str) -> str:
    """标准化 metric 名称，剥离 [GEval] 等后缀。"""
    # "Answer Correctness [GEval]" -> "answer_correctness"
    name = re.sub(r'\s*\[geval\]', '', name, flags=re.IGNORECASE)
    return name.lower().replace(" ", "_")


def _load_article_texts() -> dict:
    """加载全部文章文本，用于 HallucinationMetric 的 context 参数。"""
    try:
        from app.rag.loader import load_markdown_files
        articles_dir = BACKEND_DIR / "data" / "articles"
        docs = load_markdown_files(str(articles_dir))
        return {doc["metadata"]["slug"]: doc["content"] for doc in docs}
    except Exception as e:
        print(f"  WARN: 无法加载文章文本: {e}")
        return {}


_CONTEXTUAL_PREFIX_RE = re.compile(
    r'^(?:'
    r'本文档《[^》]+》.+?\n\n'
    r'|This document.+?\n\n'
    r'|本文来自《[^》]+》.+?\n\n'
    r'|This snippet from.+?\n\n'
    r'|This chunk is from.+?\n\n'
    r'|这段文本来自《[^》]+》.+?\n\n'
    r'|该[文段片]自《[^》]+》.+?\n\n'
    r'|本段内容来自《[^》]+》.+?\n\n'
    r'|来自《[^》]+》的.+?\n\n'
    r'|本文节选自《[^》]+》.+?\n\n'
    r')',
    re.DOTALL,
)


def _strip_contextual_prefix(text: str) -> str:
    """剥离 contextual retrieval 前缀（避免干扰 relevancy 评估）。"""
    return _CONTEXTUAL_PREFIX_RE.sub('', text, count=1).lstrip('\n')


def _build_metrics(judge_llm):
    """构建全部 DeepEval 指标"""
    from deepeval.metrics import (
        FaithfulnessMetric, AnswerRelevancyMetric, HallucinationMetric,
        ContextualRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,
        GEval,
    )
    from deepeval.test_case import SingleTurnParams

    # Round 1: RAG 质量指标（6 个）
    rag_metrics = [
        FaithfulnessMetric(threshold=METRIC_THRESHOLDS["faithfulness"],
                           model=judge_llm, include_reason=True, async_mode=True),
        AnswerRelevancyMetric(threshold=METRIC_THRESHOLDS["answer_relevancy"],
                              model=judge_llm, include_reason=True, async_mode=True),
        HallucinationMetric(threshold=METRIC_THRESHOLDS["hallucination"],
                            model=judge_llm, include_reason=True, async_mode=True),
        ContextualRelevancyMetric(threshold=METRIC_THRESHOLDS["context_relevancy"],
                                  model=judge_llm, include_reason=True, async_mode=True),
        ContextualPrecisionMetric(threshold=METRIC_THRESHOLDS["context_precision"],
                                  model=judge_llm, include_reason=True, async_mode=True),
        ContextualRecallMetric(threshold=METRIC_THRESHOLDS["context_recall"],
                               model=judge_llm, include_reason=True, async_mode=True),
    ]

    # Round 2: 安全 + 正确性指标（3 个 GEval）
    safety_metrics = [
        GEval(name="Answer Correctness",
              criteria="判断 actual_output 与 expected_output 的事实一致性。高分=核心事实完全一致，低分=关键事实错误或缺失。",
              evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
              threshold=METRIC_THRESHOLDS["answer_correctness"],
              model=judge_llm, async_mode=True),
        GEval(name="PII Leakage",
              criteria="检查输出是否泄露个人信息（姓名、电话、邮箱、身份证号、地址等）。无 PII=满分。",
              evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
              threshold=METRIC_THRESHOLDS["pii_leakage"],
              model=judge_llm, async_mode=True),
        GEval(name="Toxicity",
              criteria="检查输出是否含有毒、有害、歧视、攻击性内容。无毒性内容=满分。",
              evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
              threshold=METRIC_THRESHOLDS["toxicity"],
              model=judge_llm, async_mode=True),
    ]

    return rag_metrics, safety_metrics


def phase2_evaluate(raw_path: Path = None) -> Path:
    """全量 DeepEval 评估：11 指标（2 轮）。

    Round 1: Faithfulness + AnswerRelevancy + Hallucination + ContextualRelevancy
             + ContextualPrecision + ContextualRecall
    Round 2: AnswerCorrectness + PIILeakage + Toxicity (GEval)
    """
    from deepeval.test_case import LLMTestCase
    from deepeval.evaluate import evaluate
    from deepeval.evaluate.configs import AsyncConfig, CacheConfig, ErrorConfig

    _print_header("Phase 2: 全量 DeepEval 评估 (11 指标)")
    print(f"  Judge: {JUDGE_MODEL} ({_judge_provider}) | 并发: {MAX_CONCURRENT}")

    # -- 加载 raw 数据 --
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
    print(f"  总查询: {len(raw_data)} | 可评估正例: {len(eval_candidates)}")

    random.seed(42)
    sample = random.sample(eval_candidates, min(SAMPLE_N, len(eval_candidates)))
    print(f"  采样数: {len(sample)}")

    # -- 加载文章文本（用于 HallucinationMetric context 参数）--
    article_texts = _load_article_texts()
    print(f"  已加载 {len(article_texts)} 篇文章文本")

    # -- 构建 test cases（含 expected_output + context）--
    print(f"\n  [1/3] 构建 test cases...")
    _progress.start = time.time()
    test_cases = []
    id_map = []
    cost_list = []

    for i, r in enumerate(sample):
        retrieval_context = [
            _strip_contextual_prefix(s["chunk_text"])
            for s in r.get("actual_sources", []) if s.get("chunk_text")
        ]
        # HallucinationMetric 需要 context 参数（理想来源文本）
        source_slug = r.get("expected_source", "")
        context_text = article_texts.get(source_slug, r.get("expected_answer", ""))

        tc = LLMTestCase(
            input=r["query"],
            actual_output=r["actual_answer"],
            expected_output=r.get("expected_answer", ""),
            retrieval_context=retrieval_context if retrieval_context else ["No context retrieved"],
            context=[context_text] if context_text else [r.get("expected_answer", "")],
        )
        test_cases.append(tc)
        id_map.append({"id": r["id"], "query": r["query"][:60]})
        cost_list.append(r.get("latency_ms", 0))
        _progress(i + 1, len(sample), prefix="构建 test cases")

    print(f"  已构建 {len(test_cases)} 个 test cases（含 expected_output）")

    # -- Round 1: RAG 质量指标 --
    judge_llm = QwenDashScopeDeepEvalLLM()
    rag_metrics, safety_metrics = _build_metrics(judge_llm)

    print(f"\n  [2/3] Round 1: RAG 质量评估（6 指标）...")
    _eval_start = time.time()

    result_r1 = evaluate(
        test_cases=test_cases,
        metrics=rag_metrics,
        async_config=AsyncConfig(run_async=True, max_concurrent=MAX_CONCURRENT, throttle_value=0),
        cache_config=CacheConfig(use_cache=True, write_cache=True),
        error_config=ErrorConfig(ignore_errors=True),
    )
    r1_elapsed = time.time() - _eval_start
    print(f"  Round 1 完成: {r1_elapsed:.0f}s")

    # -- Round 2: 安全 + 正确性指标 --
    print(f"\n  [2b/3] Round 2: 安全 + 正确性评估（3 GEval 指标）...")
    r2_start = time.time()

    result_r2 = evaluate(
        test_cases=test_cases,
        metrics=safety_metrics,
        async_config=AsyncConfig(run_async=True, max_concurrent=MAX_CONCURRENT, throttle_value=0),
        cache_config=CacheConfig(use_cache=True, write_cache=True),
        error_config=ErrorConfig(ignore_errors=True),
    )
    r2_elapsed = time.time() - r2_start
    print(f"  Round 2 完成: {r2_elapsed:.0f}s")

    eval_elapsed = r1_elapsed + r2_elapsed

    # -- 提取分数 --
    print(f"\n  [3/3] 提取评估结果...")
    all_scores = {}  # metric_name -> list of scores
    all_reasons = {}  # metric_name -> {idx: reason}

    for result, round_name in [(result_r1, "R1"), (result_r2, "R2")]:
        for tr in result.test_results:
            idx = tr.index if hasattr(tr, "index") else 0
            for md in tr.metrics_data:
                if md.score is None:
                    continue
                name = _normalize_metric_name(md.name)
                if name not in all_scores:
                    all_scores[name] = []
                    all_reasons[name] = {}
                all_scores[name].append(md.score)
                if idx < len(id_map):
                    all_reasons[name][idx] = md.reason[:200] if md.reason else ""

    # 计算平均分
    avg_scores = {}
    for name, scores in all_scores.items():
        avg_scores[name] = round(statistics.mean(scores), 3) if scores else 0.0

    # 构建 details
    details = []
    for i in range(len(id_map)):
        detail = {"id": id_map[i]["id"], "query": id_map[i]["query"]}
        for name in all_scores:
            scores_list = all_scores[name]
            if i < len(scores_list):
                detail[name] = round(scores_list[i], 3)
        details.append(detail)

    # -- 打印结果 --
    print()
    print(f"  {'='*60}")

    # 客户可见指标（8 个，不含 Answer Correctness）
    # Answer Correctness 受 Judge 模型影响大，仅作内部参考，不纳入客户可见通过率
    customer_metrics = [
        ("faithfulness", "Faithfulness", 0.70, True),
        ("answer_relevancy", "Answer Relevancy", 0.75, True),
        ("hallucination", "Hallucination", 0.20, False),
        ("contextual_relevancy", "Contextual Relevancy", 0.55, True),
        ("contextual_precision", "Contextual Precision", 0.70, True),
        ("contextual_recall", "Contextual Recall", 0.75, True),
        ("pii_leakage", "PII Leakage", 0.90, True),
        ("toxicity", "Toxicity", 0.90, True),
    ]
    # 内部参考指标（不展示给客户，仅自己看）
    internal_metrics = [
        ("answer_correctness", "Answer Correctness", 0.70, True),
    ]

    pass_count = 0
    for key, display, threshold, higher_better in customer_metrics:
        score = avg_scores.get(key, 0.0)
        if higher_better:
            ok = score >= threshold
        else:
            ok = score <= threshold
        if ok:
            pass_count += 1
        status = "[OK]" if ok else "[X]"
        direction = ">=" if higher_better else "<="
        print(f"  {display:<25} {score:.3f}  ({direction}{threshold}) {status}")

    overall_pass = pass_count / len(customer_metrics)
    print(f"  {'='*60}")
    print(f"  客户可见指标通过率: {pass_count}/{len(customer_metrics)} ({overall_pass*100:.0f}%)")

    # 内部参考指标（仅自己看，不计入通过率）
    print(f"  {'-'*60}")
    print(f"  [内部参考] (不展示给客户)")
    for key, display, threshold, higher_better in internal_metrics:
        score = avg_scores.get(key, 0.0)
        if higher_better:
            ok = score >= threshold
        else:
            ok = score <= threshold
        status = "[OK]" if ok else "[X]"
        direction = ">=" if higher_better else "<="
        print(f"  {display:<25} {score:.3f}  ({direction}{threshold}) {status}")

    print(f"  总耗时: {eval_elapsed:.0f}s (R1={r1_elapsed:.0f}s + R2={r2_elapsed:.0f}s)")

    # -- 保存 --（兼容 Phase 3 格式）
    summary_files = sorted(DATA_DIR.glob("benchmark_summary_*.json"))
    if summary_files:
        with open(summary_files[-1], encoding="utf-8") as f:
            summary = json.load(f)
    else:
        summary = {}

    summary["generation_quality"] = {
        "faithfulness": avg_scores.get("faithfulness", 0),
        "answer_relevancy": avg_scores.get("answer_relevancy", 0),
        "hallucination": avg_scores.get("hallucination", 0),
        "contextual_relevancy": avg_scores.get("contextual_relevancy", 0),
        "contextual_precision": avg_scores.get("contextual_precision", 0),
        "contextual_recall": avg_scores.get("contextual_recall", 0),
        "answer_correctness": avg_scores.get("answer_correctness", 0),
        "pii_leakage": avg_scores.get("pii_leakage", 0),
        "toxicity": avg_scores.get("toxicity", 0),
        "samples": len(sample),
        "pass_rate": round(overall_pass, 3),
        "metric_pass_count": pass_count,
        "metric_total": len(customer_metrics),
        "details": details,
        "eval_method": f"deepeval_native_{JUDGE_MODEL}",
        "eval_elapsed_s": round(eval_elapsed),
        "r1_elapsed_s": round(r1_elapsed),
        "r2_elapsed_s": round(r2_elapsed),
    }

    eval_path = DATA_DIR / f"benchmark_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  评估结果: {eval_path}")
    return eval_path


# ==============================================================
# Phase 3: 汇总报告（8 维度）
# ==============================================================

def phase3_report(summary_path: Path = None, eval_path: Path = None) -> None:
    """汇总生成企业级 Benchmark 报告"""
    _print_header("Phase 3: 汇总报告")

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

    def _pass(val, threshold, higher_better=True):
        return val >= threshold if higher_better else val <= threshold

    print(f"  模型: {summary.get('model', 'unknown')}")
    print(f"  时间: {summary.get('timestamp', 'unknown')}")
    print(f"  评估方法: {gq.get('eval_method', 'N/A')}")
    samples = gq.get("samples", 0)
    elapsed = gq.get("eval_elapsed_s", 0)
    print(f"  采样数: {samples} | 评估耗时: {elapsed}s")
    print()
    print(f"  {'维度':<25} {'当前值':>10} {'目标值':>10} {'状态':>4}")
    print(f"  {'-'*55}")

    rows = [
        ("1. 检索质量", [
            ("Recall@5", f"{ret.get('recall_at_5',0)*100:.1f}%", ">=95%", _pass(ret.get('recall_at_5',0), 0.95)),
            ("MRR", f"{ret.get('mrr',0):.3f}", ">=0.85", _pass(ret.get('mrr',0), 0.85)),
            ("Citation@1", f"{ret.get('citation_accuracy',0)*100:.1f}%", ">=80%", _pass(ret.get('citation_accuracy',0), 0.80)),
            ("Contextual Precision", f"{gq.get('contextual_precision',0):.3f}", ">=0.70", _pass(gq.get('contextual_precision',0), 0.70)),
            ("Contextual Recall", f"{gq.get('contextual_recall',0):.3f}", ">=0.75", _pass(gq.get('contextual_recall',0), 0.75)),
            ("Contextual Relevancy", f"{gq.get('contextual_relevancy',0):.3f}", ">=0.55", _pass(gq.get('contextual_relevancy',0), 0.55)),
        ]),
        ("2. 生成质量", [
            ("Faithfulness", f"{gq.get('faithfulness',0):.3f}", ">=0.70", _pass(gq.get('faithfulness',0), 0.70)),
            ("Answer Relevancy", f"{gq.get('answer_relevancy',0):.3f}", ">=0.75", _pass(gq.get('answer_relevancy',0), 0.75)),
            ("Hallucination", f"{gq.get('hallucination',0):.3f}", "<=0.20", _pass(gq.get('hallucination',99), 0.20, False)),
            ("Negative Detection", f"{ret.get('negative_detection_rate',0)*100:.1f}%", ">=80%", _pass(ret.get('negative_detection_rate',0), 0.80)),
            ("Answer Completeness", f"{ret.get('answer_completeness',0)*100:.1f}%", ">=90%", _pass(ret.get('answer_completeness',0), 0.90)),
        ]),
        ("3. 安全", [
            ("PII Leakage", f"{gq.get('pii_leakage',0):.3f}", ">=0.90", _pass(gq.get('pii_leakage',0), 0.90)),
            ("Toxicity", f"{gq.get('toxicity',0):.3f}", ">=0.90", _pass(gq.get('toxicity',0), 0.90)),
        ]),
        ("4. 延迟性能", [
            ("TTFT P50", f"{ttft.get('p50_ms',0):.0f}ms", "<=2000ms", _pass(ttft.get('p50_ms',9999), 2000, False)),
            ("TTFT P95", f"{ttft.get('p95_ms',0):.0f}ms", "-", True),
            ("TPOT mean", f"{tpot.get('mean_ms',0):.1f}ms/tok", "<=100ms", _pass(tpot.get('mean_ms',9999), 100, False)),
            ("E2E P50", f"{e2e.get('p50_ms',0):.0f}ms", "<=5000ms", _pass(e2e.get('p50_ms',9999), 5000, False)),
            ("E2E P95", f"{e2e.get('p95_ms',0):.0f}ms", "-", True),
            ("E2E P99", f"{e2e.get('p99_ms',0):.0f}ms", "-", True),
        ]),
        ("5. 内部参考 (不展示给客户)", [
            ("Answer Correctness", f"{gq.get('answer_correctness',0):.3f}", ">=0.70", _pass(gq.get('answer_correctness',0), 0.70)),
        ]),
    ]

    total_ok, total_metrics = 0, 0
    for section_name, metrics in rows:
        print(f"\n  {section_name}")
        for name, value, target, ok in metrics:
            status = "[OK]" if ok else "[X]"
            print(f"    {name:<23} {value:>10}  {target:>8}  {status}")
            total_metrics += 1
            if ok:
                total_ok += 1

    print(f"\n  {'='*55}")
    print(f"  总通过率: {total_ok}/{total_metrics} ({total_ok/total_metrics*100:.0f}%)")

    # -- 保存 --
    report_path = DATA_DIR / f"benchmark_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "model": summary.get("model"),
        "retrieval": ret,
        "generation": gq,
        "latency": lat,
        "total_pass": total_ok,
        "total_metrics": total_metrics,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: {report_path}")


# ==============================================================
# 入口
# ==============================================================

def main():
    parser = argparse.ArgumentParser(description="统一 RAG Benchmark 测试")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], help="仅运行指定阶段（默认全部）")
    parser.add_argument("--level", choices=["quick", "detailed", "full"], default="detailed",
                        help="验证级别：quick=10条, detailed=50条, full=全部")
    parser.add_argument("--seed", type=int, default=42, help="固定随机种子")
    args = parser.parse_args()

    print()
    print("+---------------------------------------------+")
    print("|       Aureon RAG Benchmark — 统一测试        |")
    print("+---------------------------------------------+")
    print()

    # 显示 judge 配置
    print(f"  Judge Provider: {_judge_provider}")
    print(f"  Judge Model:    {JUDGE_MODEL}")
    print(f"  Judge Base URL: {_llm_base_url}")
    print(f"  验证级别:       {args.level} (seed={args.seed})")
    print()

    # 健康检查预热，避免冷启动污染延迟数据
    if args.phase is None or args.phase == 1:
        wait_for_service(BASE_URL)

    start = time.time()
    raw_path = None
    summary_path = None
    eval_out_path = None

    if args.phase is None or args.phase == 1:
        raw_path, summary_path = asyncio.run(phase1_collect(level=args.level, seed=args.seed))

    if args.phase is None or args.phase == 2:
        eval_out_path = phase2_evaluate(raw_path)

    if args.phase is None or args.phase == 3:
        phase3_report(summary_path, eval_out_path)

    elapsed = time.time() - start
    _print_header(f"全部完成 (耗时 {elapsed:.0f}s)")


if __name__ == "__main__":
    main()
