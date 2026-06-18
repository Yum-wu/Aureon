"""检查 actual_sources 结构"""
import json
from pathlib import Path

raw_path = Path("data/benchmark_raw_20260617_215535.json")
with open(raw_path, encoding="utf-8") as f:
    raw = json.load(f)

# 找第一个正例
for r in raw:
    if r.get("is_negative"):
        continue
    print(f"ID: {r['id']}")
    print(f"Query: {r['query'][:80]}")
    print(f"actual_sources type: {type(r.get('actual_sources'))}")
    sources = r.get("actual_sources", [])
    print(f"actual_sources length: {len(sources)}")
    if sources:
        print(f"First source keys: {list(sources[0].keys())}")
        print(f"First source: {json.dumps(sources[0], ensure_ascii=False)[:300]}")
    break
