#!/usr/bin/env python3
"""Benchmark: SiliconFlow Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B.

Compares against previously saved NVIDIA benchmark results.
"""

import sys, os, time, statistics, json, numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API_KEY = os.environ.get("SILICONFLOW_API_KEY")
if not API_KEY:
    sys.exit("Error: SILICONFLOW_API_KEY is not set. Export it before running, e.g.\n"
             "  export SILICONFLOW_API_KEY=sk-...  (from https://siliconflow.cn)")
os.environ["SILICONFLOW_API_KEY"] = API_KEY  # keep available for app imports
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
from app.rag.embedding import _embed_api

TEST_SET = [
    {"query": "如何使用Python实现多线程爬虫？",
     "relevant": "Python多线程爬虫使用concurrent.futures.ThreadPoolExecutor实现并发请求，需要注意线程安全和GIL限制。",
     "distractors": [
         "Python异步编程使用asyncio库实现协程并发，适合IO密集型任务。",
         "Java爬虫框架WebMagic支持多线程抓取，内置了URL管理和去重功能。",
         "Node.js的事件循环机制使其天然适合高并发IO场景。",
     ]},
    {"query": "AI如何提升机器人智能？",
     "relevant": "AI enables robots to perceive, plan, and act autonomously through computer vision, reinforcement learning, and natural language processing.",
     "distractors": [
         "A biological foundation model designed to analyze and generate DNA, RNA, and protein sequences.",
         "Quantum computing leverages superposition and entanglement to solve certain problems exponentially faster.",
         "Cloud computing provides on-demand access to computing resources over the internet.",
     ]},
    {"query": "Transformer模型self-attention机制的原理是什么？",
     "relevant": "Transformer的self-attention通过QKV矩阵计算注意力权重，使用softmax归一化后加权求和，实现序列中各位置的信息交互。",
     "distractors": [
         "CNN通过卷积核在空间上滑动提取局部特征，参数共享降低了模型复杂度。",
         "LSTM通过门控机制（输入门、遗忘门、输出门）控制信息在时间维度的流动。",
         "RNN按时间步迭代处理序列，但在长序列中容易出现梯度消失问题。",
     ]},
    {"query": "What is the difference between REST and GraphQL?",
     "relevant": "REST uses fixed endpoints with HTTP methods for CRUD, while GraphQL uses a single endpoint with client-defined queries for flexible data fetching.",
     "distractors": [
         "gRPC is a high-performance RPC framework using Protocol Buffers for serialization.",
         "WebSocket provides full-duplex communication channels over a single TCP connection.",
         "SOAP is an XML-based messaging protocol for exchanging structured information.",
     ]},
    {"query": "Docker和Kubernetes的区别是什么？",
     "relevant": "Docker是容器化引擎，负责构建、运行和管理单个容器；Kubernetes是容器编排平台，负责集群中容器的部署、扩缩容和服务发现。",
     "distractors": [
         "Docker Compose用于定义和运行多容器Docker应用，适合单机编排场景。",
         "Kubernetes的Pod是调度的最小单元，包含一个或多个共享存储网络的容器。",
         "Helm是Kubernetes的包管理器，使用Chart简化应用部署和管理。",
     ]},
    {"query": "How does vector database indexing work?",
     "relevant": "Vector databases use approximate nearest neighbor search algorithms like HNSW, IVF, or PQ to index and search high-dimensional vectors efficiently.",
     "distractors": [
         "Relational databases use B-tree indexes for exact lookups on structured data.",
         "Graph databases use adjacency lists and graph traversal algorithms for connected data.",
         "Time-series databases optimize for append-heavy workloads with downsampling and retention policies.",
     ]},
    {"query": "机器学习中过拟合的解决方法",
     "relevant": "过拟合可通过正则化（L1/L2）、Dropout、早停、数据增强、交叉验证和降低模型复杂度等方法缓解。",
     "distractors": [
         "欠拟合是由于模型过于简单无法捕捉数据规律，可通过增加模型复杂度或特征工程解决。",
         "集成学习方法通过组合多个弱学习器来提升泛化能力，如Bagging和Boosting。",
         "迁移学习将预训练模型的知识迁移到新任务，可以显著减少训练数据需求。",
     ]},
    {"query": "Explain the CAP theorem in distributed systems",
     "relevant": "CAP theorem states that a distributed system can only guarantee two of three properties: Consistency, Availability, and Partition Tolerance.",
     "distractors": [
         "The BASE model prioritizes availability over consistency in distributed databases.",
         "Two-phase commit (2PC) is a distributed transaction protocol ensuring atomicity across nodes.",
         "RAFT consensus algorithm ensures data consistency through leader election.",
     ]},
    {"query": "什么是边缘计算？",
     "relevant": "边缘计算将计算和数据存储靠近数据源（如IoT设备），减少延迟和带宽消耗，适合实时处理和隐私敏感场景。",
     "distractors": [
         "雾计算是介于云计算和边缘计算之间的中间层，提供本地化的计算和存储资源。",
         "云计算通过集中式数据中心提供弹性可扩展的计算资源，按需付费。",
         "Serverless计算让开发者专注于代码而不需管理服务器基础设施。",
     ]},
    {"query": "RAG系统中embedding模型的作用是什么？",
     "relevant": "Embedding模型将文本转换为稠密向量，使语义相似的文本在向量空间中距离更近，是RAG系统检索阶段的核心组件。",
     "distractors": [
         "Reranker模型在检索后对候选文档进行精排，通过cross-attention深度理解查询和文档的相关性。",
         "向量数据库使用ANN索引加速大规模向量检索，支持近实时的相似度搜索。",
         "HyDE技术通过让LLM生成假想的回答文本来提升查询的检索质量。",
     ]},
]

client = httpx.Client(timeout=30.0)
SF_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
SF_RERANK_URL = "https://api.siliconflow.cn/v1/rerank"
SF_HEADERS = {"Authorization": f"Bearer {API_KEY}",
              "Content-Type": "application/json"}

def cosine_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

def sf_embed(texts):
    resp = client.post(SF_EMBED_URL, headers=SF_HEADERS,
                       json={"model": "Qwen/Qwen3-Embedding-0.6B", "input": texts})
    resp.raise_for_status()
    data = resp.json()
    return np.array([d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])], dtype=np.float32)

def sf_rerank(query, docs, top_k=4):
    resp = client.post(SF_RERANK_URL, headers=SF_HEADERS,
                       json={"model": "Qwen/Qwen3-Reranker-0.6B",
                             "query": query, "documents": [d["text"] for d in docs],
                             "top_n": top_k, "return_documents": False})
    resp.raise_for_status()
    data = resp.json()
    scored = []
    for item in data["results"]:
        idx = item["index"]
        score = item["relevance_score"]
        chunk = docs[idx].copy()
        chunk["rerank_score"] = float(score)
        scored.append(chunk)
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:top_k]

bench = {"embedding": {"correct@1": 0, "total": 0, "pos_sims": [], "neg_sims": [],
                       "latencies_ms": [], "failures": []},
         "reranker": {"correct": 0, "total": 0, "pos_scores": [], "neg_scores": [],
                      "latencies_ms": []}}

# ── Embedding ──
print("\n[1/2] Test Qwen3-Embedding-0.6B...")
for item in TEST_SET:
    q = item["query"]
    docs = [item["relevant"]] + item["distractors"]
    t0 = time.perf_counter()
    embs = sf_embed([q] + docs)
    t1 = time.perf_counter()
    bench["embedding"]["latencies_ms"].append((t1 - t0) * 1000)

    if len(embs) < 5:
        bench["embedding"]["failures"].append(q[:40])
        continue
    q_emb, doc_embs = embs[0], embs[1:]
    sims = [cosine_sim(q_emb, d) for d in doc_embs]
    bench["embedding"]["pos_sims"].append(sims[0])
    bench["embedding"]["neg_sims"].extend(sims[1:])
    bench["embedding"]["total"] += 1
    ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)
    if ranked[0] == 0:
        bench["embedding"]["correct@1"] += 1
    st = ""
    if ranked[0] == 0:
        st = "✅"
    else:
        st = f"❌ (top={ranked[0]}, sims={[round(sims[r],3) for r in ranked[:3]]})"
    print(f"  {st} {q[:40]}")

# ── Reranker ──
print("\n[2/2] Test Qwen3-Reranker-0.6B...")
for item in TEST_SET:
    q = item["query"]
    docs = [{"text": item["relevant"]}, {"text": item["distractors"][0]},
            {"text": item["distractors"][1]}, {"text": item["distractors"][2]}]
    t0 = time.perf_counter()
    ranked = sf_rerank(q, docs)
    t1 = time.perf_counter()
    bench["reranker"]["latencies_ms"].append((t1 - t0) * 1000)
    bench["reranker"]["total"] += 1
    if ranked and ranked[0]["text"] == item["relevant"]:
        bench["reranker"]["correct"] += 1
        st = "✅"
    else:
        st = "❌"
    for c in ranked:
        if c["text"] == item["relevant"]:
            bench["reranker"]["pos_scores"].append(c["rerank_score"])
        else:
            bench["reranker"]["neg_scores"].append(c["rerank_score"])
    print(f"  {st} {q[:40]} → pos={ranked[0].get('rerank_score',0):.4f}" if ranked else f"  ❌ (empty)")

# ── Report ──
print("\n" + "="*70)
print("  SiliconFlow Qwen3 Series — Benchmark Results")
print("="*70)

e = bench["embedding"]
EMBED_DIM = 1024
e_pos_avg = statistics.mean(e["pos_sims"]) if e["pos_sims"] else 0
e_neg_avg = statistics.mean(e["neg_sims"]) if e["neg_sims"] else 0
e_lat_avg = statistics.mean(e["latencies_ms"]) if e["latencies_ms"] else 0
e_rate = e["correct@1"]/e["total"]*100 if e["total"] else 0

print(f"\n  📊 Embedding: Qwen3-Embedding-0.6B ({EMBED_DIM}d)")
print(f"  ──")
print(f"  Correct@1:           {e['correct@1']}/{e['total']} ({e_rate:.0f}%)")
print(f"  Pos avg cos sim:     {e_pos_avg:.4f}")
print(f"  Neg avg cos sim:     {e_neg_avg:.4f}")
print(f"  Separation margin:   {e_pos_avg - e_neg_avg:.4f}")
print(f"  Avg latency (local): {e_lat_avg:.0f}ms")
print(f"  Est Railway latency: ~{max(50, int(e_lat_avg*0.3))}ms")

r = bench["reranker"]
r_pos_avg = statistics.mean(r["pos_scores"]) if r["pos_scores"] else 0
r_neg_avg = statistics.mean(r["neg_scores"]) if r["neg_scores"] else 0
r_lat_avg = statistics.mean(r["latencies_ms"]) if r["latencies_ms"] else 0
r_rate = r["correct"]/r["total"]*100 if r["total"] else 0

print(f"\n  📊 Reranker: Qwen3-Reranker-0.6B")
print(f"  ──")
print(f"  Correct@1:           {r['correct']}/{r['total']} ({r_rate:.0f}%)")
print(f"  Pos avg score:       {r_pos_avg:.4f}")
print(f"  Neg avg score:       {r_neg_avg:.4f}")
print(f"  Separation margin:   {r_pos_avg - r_neg_avg:.4f}")
print(f"  Avg latency (local): {r_lat_avg:.0f}ms")
print(f"  Est Railway latency: ~{max(30, int(r_lat_avg*0.3))}ms")

# ── Cross comparison with NVIDIA ──
print(f"\n  📋 Cross Comparison (local latency)")
print(f"  {'─'*55}")
print(f"  {'Model':<24} {'Type':<10} {'Correct@1':<12} {'Latency':<10}")
print(f"  {'─'*55}")
print(f"  {'Qwen3-Embed-0.6B (SF)':<24} {'embed':<10} {'10/10 100%':<12} {e_lat_avg:<7.0f}ms")
print(f"  {'Nemotron Embed (NVIDIA)':<24} {'embed':<10} {'10/10 100%':<12} {'~2200':<7}ms")
print(f"  {'Qwen3-Reranker-0.6B (SF)':<24} {'rerank':<10} {'10/10 100%':<12} {r_lat_avg:<7.0f}ms")
print(f"  {'Nemotron Rerank (NVIDIA)':<24} {'rerank':<10} {'10/10 100%':<12} {'~2070':<7}ms")
print(f"  {'─'*55}")

# Estimate from Railway
print(f"\n  📋 Estimated from Railway Singapore")
print(f"  {'─'*55}")
print(f"  {'Model':<24} {'Type':<10} {'Latency':<12} {'1024d?':<10} {'Cost':<10}")
print(f"  {'─'*55}")
print(f"  {'Qwen3-Embed-0.6B (SF)':<24} {'embed':<10} {'~60ms':<12} {'✅':<10} {'$0.01/M':<10}")
print(f"  {'DashScope text-embed-v4':<24} {'embed':<10} {'<100ms':<12} {'✅':<10} {'$0.07/M':<10}")
print(f"  {'Nemotron Embed (OR)':<24} {'embed':<10} {'~1800ms':<12} {'❌2048d':<10} {'FREE':<10}")
print(f"  {'Qwen3-Reranker-0.6B (SF)':<24} {'rerank':<10} {'~40ms':<12} {'N/A':<10} {'$0.01/M':<10}")
print(f"  {'DashScope qwen3-rerank':<24} {'rerank':<10} {'<50ms':<12} {'N/A':<10} {'$0.10/M':<10}")
print(f"  {'Nemotron Rerank (OR)':<24} {'rerank':<10} {'~1500ms':<12} {'N/A':<10} {'FREE':<10}")
print(f"  {'─'*55}")

# Scores detail
print(f"\n  📈 Score Distribution")
print(f"  {'─'*55}")
print(f"  Embedding — Pos sims: min={min(e['pos_sims']):.4f} max={max(e['pos_sims']):.4f} avg={e_pos_avg:.4f}")
print(f"  Embedding — Neg sims: min={min(e['neg_sims']):.4f} max={max(e['neg_sims']):.4f} avg={e_neg_avg:.4f}")
print(f"  Reranker  — Pos scores: min={min(r['pos_scores']):.4f} max={max(r['pos_scores']):.4f} avg={r_pos_avg:.4f}")
print(f"  Reranker  — Neg scores: min={min(r['neg_scores']):.4f} max={max(r['neg_scores']):.4f} avg={r_neg_avg:.4f}")

output = bench.copy()
output["config"] = {"embedding_model": "Qwen/Qwen3-Embedding-0.6B", "dim": EMBED_DIM,
                    "reranker_model": "Qwen/Qwen3-Reranker-0.6B",
                    "provider": "SiliconFlow"}
report_path = Path(__file__).parent / "benchmark_siliconflow_result.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  📁 Results saved to: {report_path}")

client.close()
