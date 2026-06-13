"""Phase 2: Local LLM-as-Judge evaluation on Railway benchmark data.

Loads raw benchmark data, evaluates Faithfulness + Answer Relevancy
using local DashScope API (domestic node).
"""

import json
import sys
import time
import statistics
from pathlib import Path

# Load raw data
DATA_DIR = Path(__file__).parent.parent / "data"
raw_files = sorted(DATA_DIR.glob("benchmark_raw_*.json"))
if not raw_files:
    print("No benchmark raw data found. Run _benchmark_collect.py first.")
    sys.exit(1)

raw_path = raw_files[-1]  # latest
print(f"Loading: {raw_path}")

with open(raw_path, encoding="utf-8") as f:
    raw_data = json.load(f)

print(f"Loaded {len(raw_data)} queries")

# Filter: only queries with answers (not negative, not errors)
eval_candidates = [
    r for r in raw_data
    if r.get("actual_answer") and len(r.get("actual_answer", "")) > 20
    and not r.get("is_negative") and not r.get("error")
]
print(f"Eligible for evaluation: {len(eval_candidates)} queries")

# Sample 30 for cost control
import random
random.seed(42)
sample = random.sample(eval_candidates, min(30, len(eval_candidates)))
print(f"Sampled {len(sample)} queries for LLM-as-Judge evaluation\n")

# LLM-as-Judge using DashScope (local config)
import os
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Read API key from .env or fallback to DashScope
def _load_api_key():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("LLM_API_KEY=") or line.startswith("DASHSCOPE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY")

api_key = _load_api_key()
if not api_key:
    print("ERROR: No API key found. Set LLM_API_KEY or DASHSCOPE_API_KEY in .env")
    sys.exit(1)

from openai import OpenAI

judge_client = OpenAI(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


def judge_faithfulness(query: str, answer: str, context: str) -> float:
    """Judge if answer is faithful to the retrieved context (0-1)."""
    prompt = f"""你是一个RAG系统评估专家。判断以下回答是否忠实于检索到的上下文。

查询：{query}
检索到的上下文（摘要）：{context[:800]}
生成的回答：{answer[:300]}

评分标准：
- 1.0：回答完全基于上下文，没有幻觉
- 0.7：回答基本基于上下文，有少量推测
- 0.5：回答部分基于上下文，有明显推测
- 0.3：回答大部分是幻觉
- 0.0：回答完全是幻觉

只回答一个数字（0-1），不要解释。"""

    try:
        resp = judge_client.chat.completions.create(
            model="qwen3.5-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        score_text = resp.choices[0].message.content.strip()
        return float(score_text)
    except Exception as e:
        print(f"  Judge error: {e}")
        return 0.5


def judge_answer_relevancy(query: str, answer: str) -> float:
    """Judge if answer addresses the question (0-1)."""
    prompt = f"""你是一个RAG系统评估专家。判断以下回答是否切题。

查询：{query}
生成的回答：{answer[:300]}

评分标准：
- 1.0：回答完全切题，直接回答了问题
- 0.7：回答基本切题，但有少量偏题内容
- 0.5：回答部分切题，有明显偏题
- 0.3：回答大部分偏题
- 0.0：回答完全不相关

只回答一个数字（0-1），不要解释。"""

    try:
        resp = judge_client.chat.completions.create(
            model="qwen3.5-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        score_text = resp.choices[0].message.content.strip()
        return float(score_text)
    except Exception as e:
        print(f"  Judge error: {e}")
        return 0.5


# Run evaluation
faithfulness_scores = []
relevancy_scores = []
evaluation_details = []

for i, r in enumerate(sample):
    query = r["query"]
    answer = r["actual_answer"]
    sources = r.get("actual_sources", [])
    context = " ".join(s.get("chunk_text", "") for s in sources[:5])

    print(f"  [{i+1}/{len(sample)}] {query[:50]}...")

    f_score = judge_faithfulness(query, answer, context)
    r_score = judge_answer_relevancy(query, answer)

    faithfulness_scores.append(f_score)
    relevancy_scores.append(r_score)
    evaluation_details.append({
        "id": r["id"],
        "query": query[:60],
        "faithfulness": f_score,
        "relevancy": r_score,
    })

    print(f"    Faithfulness={f_score:.2f} | Relevancy={r_score:.2f}")
    time.sleep(0.5)  # Rate limit

# Summary
avg_faith = statistics.mean(faithfulness_scores) if faithfulness_scores else 0
avg_rel = statistics.mean(relevancy_scores) if relevancy_scores else 0

print("\n" + "=" * 60)
print("  GENERATION QUALITY (LLM-as-Judge)")
print("=" * 60)
print(f"  Faithfulness:     {avg_faith:.3f} (target: >=0.70)")
print(f"  Answer Relevancy: {avg_rel:.3f} (target: >=0.75)")
print(f"  Samples:          {len(sample)}")
print(f"  Pass Rate:        {sum(1 for f, r in zip(faithfulness_scores, relevancy_scores) if f >= 0.7 and r >= 0.7)}/{len(sample)}")
print("=" * 60)

# Load summary and merge
summary_files = sorted(DATA_DIR.glob("benchmark_summary_*.json"))
if summary_files:
    with open(summary_files[-1], encoding="utf-8") as f:
        summary = json.load(f)
else:
    summary = {}

summary["generation_quality"] = {
    "faithfulness": round(avg_faith, 3),
    "answer_relevancy": round(avg_rel, 3),
    "samples": len(sample),
    "pass_rate": round(sum(1 for f, r in zip(faithfulness_scores, relevancy_scores) if f >= 0.7 and r >= 0.7) / max(len(sample), 1), 3),
    "evaluation_details": evaluation_details,
}

# Save updated summary
output_path = DATA_DIR / f"benchmark_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"\nEvaluation saved: {output_path}")
