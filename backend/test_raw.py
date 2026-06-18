"""检查 raw 数据结构"""
import sys
sys.path.insert(0, '.')
import os
os.environ['JUDGE_MODEL'] = 'mimo-v2.5'
os.environ['JUDGE_API_KEY'] = 'tp-cu4ccyd1cpx695g1dox14rgednfqrjgx32oy69ki3j9w3p3x'
os.environ['JUDGE_BASE_URL'] = 'https://token-plan-cn.xiaomimimo.com/v1'

import json
from tests.run_full_benchmark import DATA_DIR

raw_path = DATA_DIR / "benchmark_raw_20260617_215535.json"
with open(raw_path, encoding="utf-8") as f:
    raw = json.load(f)

print("Type:", type(raw))
if isinstance(raw, list):
    print("Length:", len(raw))
    print("First item keys:", list(raw[0].keys()) if raw else "empty")
    print("First item:", json.dumps(raw[0], ensure_ascii=False, indent=2)[:500])
elif isinstance(raw, dict):
    print("Keys:", list(raw.keys()))
    if "results" in raw:
        print("Results length:", len(raw["results"]))
        print("First result keys:", list(raw["results"][0].keys()))
        print("First result:", json.dumps(raw["results"][0], ensure_ascii=False, indent=2)[:500])
