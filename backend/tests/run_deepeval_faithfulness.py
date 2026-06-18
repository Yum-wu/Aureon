"""Quick DeepEval Faithfulness test with qwen3.6-flash as Judge.

Uses DeepEval's native claim-level NLI algorithm instead of custom whole-answer scoring.
"""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# -- Windows GBK 编码修复（必须在所有 print / DeepEval import 之前）--
# DeepEval evaluate() 内部使用 rich 库打印 emoji（如 ✨ \u2728），
# Windows 控制台默认 GBK 编码无法处理，导致 UnicodeEncodeError
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Load .env FIRST before any other imports that read env vars
load_dotenv(BACKEND_DIR / ".env", override=True)

# Set DashScope as OpenAI-compatible endpoint for DeepEval Judge
os.environ["OPENAI_API_KEY"] = os.getenv("LLM_API_KEY", "")
os.environ["OPENAI_API_BASE"] = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
os.environ["OPENAI_BASE_URL"] = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

JUDGE_MODEL = "qwen3.6-flash"


def main():
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("ERROR: No API key found in .env")
        sys.exit(1)

    print(f"Judge model: {JUDGE_MODEL}")
    print(f"Algorithm: DeepEval native FaithfulnessMetric (claim-level NLI)")
    print()

    # Load golden dataset
    from tests.test_data_golden import load_dataset
    qa_pairs = load_dataset("core_regression_40qa")
    print(f"Dataset: {len(qa_pairs)} QA pairs")

    # Run rag_query
    from app.rag.qa_chain import rag_query
    from app.agent.llm import create_llm
    llm = create_llm()

    def rag_query_fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    # Build test cases with full pipeline
    from tests.deepeval_eval import build_test_cases, _load_article_texts
    article_texts = _load_article_texts()
    print(f"Loaded {len(article_texts)} article texts")

    t0 = time.time()
    test_cases, used_qa_indices = build_test_cases(
        qa_pairs, rag_query_fn, article_texts, max_concurrent=10
    )
    print(f"Built {len(test_cases)} test cases in {time.time()-t0:.0f}s")

    # Run DeepEval Faithfulness only
    from deepeval.metrics import FaithfulnessMetric
    from deepeval.test_case import LLMTestCase
    from deepeval.evaluate import evaluate
    from deepeval.evaluate.configs import AsyncConfig, CacheConfig, ErrorConfig

    metric = FaithfulnessMetric(
        threshold=0.7,
        model=JUDGE_MODEL,
        include_reason=True,
        async_mode=True,
    )

    print(f"\nRunning DeepEval FaithfulnessMetric with {JUDGE_MODEL}...")
    t1 = time.time()
    result = evaluate(
        test_cases=test_cases,
        metrics=[metric],
        async_config=AsyncConfig(run_async=True, max_concurrent=10),
        cache_config=CacheConfig(use_cache=True, write_cache=True),
        error_config=ErrorConfig(ignore_errors=True),
    )
    elapsed = time.time() - t1

    # Extract scores
    scores = []
    details = []
    for tr in result.test_results:
        for md in tr.metrics_data:
            if md.name.lower() == "faithfulness" and md.score is not None:
                scores.append(md.score)
                details.append({
                    "index": tr.index,
                    "score": md.score,
                    "reason": md.reason[:200] if md.reason else "",
                })

    avg_score = sum(scores) / len(scores) if scores else 0
    passed = sum(1 for s in scores if s >= 0.7)
    total = len(scores)

    print(f"\n{'='*60}")
    print(f"  DeepEval FaithfulnessMetric Results")
    print(f"  Judge: {JUDGE_MODEL}")
    print(f"  Algorithm: claim-level NLI (2-step)")
    print(f"{'='*60}")
    print(f"  Faithfulness: {avg_score:.3f} (target: >=0.70) {'[OK]' if avg_score >= 0.7 else '[X]'}")
    print(f"  Passed: {passed}/{total} ({passed/total*100:.0f}%)")
    print(f"  Elapsed: {elapsed:.0f}s")
    print(f"{'='*60}")

    # Show score distribution
    from collections import Counter
    dist = Counter()
    for s in scores:
        if s >= 0.9:
            dist["0.9-1.0"] += 1
        elif s >= 0.7:
            dist["0.7-0.9"] += 1
        elif s >= 0.5:
            dist["0.5-0.7"] += 1
        elif s >= 0.3:
            dist["0.3-0.5"] += 1
        else:
            dist["0.0-0.3"] += 1
    print(f"\n  Score distribution:")
    for bucket in ["0.9-1.0", "0.7-0.9", "0.5-0.7", "0.3-0.5", "0.0-0.3"]:
        count = dist.get(bucket, 0)
        print(f"    {bucket}: {count} ({count/total*100:.0f}%)")

    # Show worst 5
    worst = sorted(details, key=lambda d: d["score"])[:5]
    print(f"\n  Worst 5:")
    for d in worst:
        print(f"    [{d['index']}] score={d['score']:.2f} | {d['reason'][:100]}")

    # Save
    import json
    out_path = BACKEND_DIR / "data" / f"deepeval_faithfulness_{JUDGE_MODEL.replace('.', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "judge_model": JUDGE_MODEL,
            "algorithm": "deepeval_native_claim_level_nli",
            "faithfulness": round(avg_score, 4),
            "passed": passed,
            "total": total,
            "elapsed_s": round(elapsed),
            "details": details,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
