#!/usr/bin/env python3
"""触发全量索引（含 Contextual Retrieval）"""
import sys
sys.path.insert(0, "/app")

from app.rag.indexer import run_index_pipeline
from app.agent.llm import create_llm

llm = create_llm(temperature=0.0, streaming=False)

def llm_call_fn(msgs):
    return llm.invoke(msgs).content

result = run_index_pipeline("/app/data/articles", llm_call_fn=llm_call_fn, enable_contextual=True)
print(f"索引结果: {result}")
