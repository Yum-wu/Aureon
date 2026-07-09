#!/usr/bin/env python3
"""NVIDIA vs DashScope embedding/reranker standalone benchmark.

Tests just the embedding and reranker quality directly, without Qdrant.
Outputs a comparison table.

Usage: cd backend && python tests/benchmark_nvidia_vs_dashscope.py
"""

import sys, os, time, statistics, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from app.config import settings
from app.rag.embedding import embed_texts_llm, _embed_api, _get_embedding_dim
from app.rag.reranker import rerank

# ── Test data ──────────────────────────────────────────────────────
TEST_SET = [
    # (query, relevant_doc, distractors...)
    {
        "query": "如何使用Python实现多线程爬虫？",
        "relevant": "Python多线程爬虫使用concurrent.futures.ThreadPoolExecutor实现并发请求，需要注意线程安全和GIL限制。",
        "distractors": [
            "Python异步编程使用asyncio库实现协程并发，适合IO密集型任务。",
            "Java爬虫框架WebMagic支持多线程抓取，内置了URL管理和去重功能。",
            "Node.js的事件循环机制使其天然适合高并发IO场景。",
        ],
    },
    {
        "query": "AI如何提升机器人智能？",
        "relevant": "AI enables robots to perceive, plan, and act autonomously through computer vision, reinforcement learning, and natural language processing.",
        "distractors": [
            "A biological foundation model designed to analyze and generate DNA, RNA, and protein sequences.",
            "Quantum computing leverages superposition and entanglement to solve certain problems exponentially faster.",
            "Cloud computing provides on-demand access to computing resources over the internet.",
        ],
    },
    {
        "query": "Transformer模型self-attention机制的原理是什么？",
        "relevant": "Transformer的self-attention通过QKV矩阵计算注意力权重，使用softmax归一化后加权求和，实现序列中各位置的信息交互。",
        "distractors": [
            "CNN通过卷积核在空间上滑动提取局部特征，参数共享降低了模型复杂度。",
            "LSTM通过门控机制（输入门、遗忘门、输出门）控制信息在时间维度的流动。",
            "RNN按时间步迭代处理序列，但在长序列中容易出现梯度消失问题。",
        ],
    },
    {
        "query": "What is the difference between REST and GraphQL?",
        "relevant": "REST uses fixed endpoints with HTTP methods for CRUD, while GraphQL uses a single endpoint with client-defined queries for flexible data fetching.",
        "distractors": [
            "gRPC is a high-performance RPC framework using Protocol Buffers for serialization.",
            "WebSocket provides full-duplex communication channels over a single TCP connection.",
            "SOAP is an XML-based messaging protocol for exchanging structured information.",
        ],
    },
    {
        "query": "Docker和Kubernetes的区别是什么？",
        "relevant": "Docker是容器化引擎，负责构建、运行和管理单个容器；Kubernetes是容器编排平台，负责集群中容器的部署、扩缩容和服务发现。",
        "distractors": [
            "Docker Compose用于定义和运行多容器Docker应用，适合单机编排场景。",
            "Kubernetes的Pod是调度的最小单元，包含一个或多个共享存储网络的容器。",
            "Helm是Kubernetes的包管理器，使用Chart简化应用部署和管理。",
        ],
    },
    {
        "query": "How does vector database indexing work?",
        "relevant": "Vector databases use approximate nearest neighbor search algorithms like HNSW, IVF, or PQ to index and search high-dimensional vectors efficiently.",
        "distractors": [
            "Relational databases use B-tree indexes for exact lookups on structured data.",
            "Graph databases use adjacency lists and graph traversal algorithms for connected data.",
            "Time-series databases optimize for append-heavy workloads with downsampling and retention policies.",
        ],
    },
    {
        "query": "机器学习中过拟合的解决方法",
        "relevant": "过拟合可通过正则化（L1/L2）、Dropout、早停、数据增强、交叉验证和降低模型复杂度等方法缓解。",
        "distractors": [
            "欠拟合是由于模型过于简单无法捕捉数据规律，可通过增加模型复杂度或特征工程解决。",
            "集成学习方法通过组合多个弱学习器来提升泛化能力，如Bagging和Boosting。",
            "迁移学习将预训练模型的知识迁移到新任务，可以显著减少训练数据需求。",
        ],
    },
    {
        "query": "Explain the CAP theorem in distributed systems",
        "relevant": "CAP theorem states that a distributed system can only guarantee two of three properties: Consistency (all nodes see the same data), Availability (every request gets a response), and Partition Tolerance (system continues despite network failures).",
        "distractors": [
            "The BASE model prioritizes availability over consistency in distributed databases.",
            "Two-phase commit (2PC) is a distributed transaction protocol ensuring atomicity across nodes.",
            "RAFT consensus algorithm ensures data consistency across distributed system nodes through leader election.",
        ],
    },
    {
        "query": "什么是边缘计算？",
        "relevant": "边缘计算将计算和数据存储靠近数据源（如IoT设备），减少延迟和带宽消耗，适合实时处理和隐私敏感场景。",
        "distractors": [
            "雾计算是介于云计算和边缘计算之间的中间层，提供本地化的计算和存储资源。",
            "云计算通过集中式数据中心提供弹性可扩展的计算资源，按需付费。",
            "Serverless计算让开发者专注于代码而不需管理服务器基础设施。",
        ],
    },
    {
        "query": "RAG系统中embedding模型的作用是什么？",
        "relevant": "Embedding模型将文本转换为稠密向量，使语义相似的文本在向量空间中距离更近，是RAG系统检索阶段的核心组件。",
        "distractors": [
            "Reranker模型在检索后对候选文档进行精排，通过cross-attention深度理解查询和文档的相关性。",
            "向量数据库使用ANN索引加速大规模向量检索，支持近实时的相似度搜索。",
            "HyDE技术通过让LLM生成假想的回答文本来提升查询的检索质量。",
        ],
    },
]

def cosine_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

def test_embedding_quality(label: str, embed_fn) -> dict:
    """Test embedding quality: positive doc should rank above distractors."""
    results = {"correct@1": 0, "correct@3": 0, "total": 0,
               "pos_sims": [], "neg_sims": [], "latencies_ms": []}
    failures = []

    for item in TEST_SET:
        q = item["query"]
        docs = [item["relevant"]] + item["distractors"]

        t0 = time.perf_counter()
        embs = embed_fn([q] + docs)
        t1 = time.perf_counter()
        results["latencies_ms"].append((t1 - t0) * 1000)

        if len(embs) < len(docs) + 1:
            failures.append({"q": q[:40], "err": "not enough embeddings"})
            continue

        q_emb = embs[0]
        doc_embs = embs[1:]
        sims = [cosine_sim(q_emb, d_emb) for d_emb in doc_embs]

        results["pos_sims"].append(sims[0])  # relevant doc similarity
        results["neg_sims"].extend(sims[1:])  # distractors

        # Rank: higher similarity = better match
        ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)
        correct = ranked[0] == 0  # relevant doc at rank 1?
        results["total"] += 1
        if correct:
            results["correct@1"] += 1
        if 0 in ranked[:3]:
            results["correct@3"] += 1

        if not correct:
            failures.append({
                "q": q[:40],
                "pos_sim": round(sims[0], 4),
                "top_neg_sim": round(sims[ranked[0]], 4),
            })

    pos_avg = statistics.mean(results["pos_sims"]) if results["pos_sims"] else 0
    neg_avg = statistics.mean(results["neg_sims"]) if results["neg_sims"] else 0
    lat_avg = statistics.mean(results["latencies_ms"]) if results["latencies_ms"] else 0
    actual_dim = len(embs[0]) if len(embs) > 0 else 0

    return {
        "label": label,
        "dim": actual_dim,
        "correct@1": f"{results['correct@1']}/{results['total']}",
        "correct@1_pct": round(results['correct@1'] / results['total'] * 100, 1) if results['total'] else 0,
        "correct@3_pct": round(results['correct@3'] / results['total'] * 100, 1) if results['total'] else 0,
        "pos_sim_avg": round(pos_avg, 4),
        "neg_sim_avg": round(neg_avg, 4),
        "sep_margin": round(pos_avg - neg_avg, 4),
        "pos_sims": results["pos_sims"],
        "neg_sims": results["neg_sims"],
        "latency_ms": round(lat_avg, 1),
        "failures": len(failures),
        "failure_detail": failures[:3],
    }

def test_rerank_quality(label: str) -> dict:
    """Test reranker: relevant doc should score higher than distractors."""
    results = {"correct": 0, "total": 0, "latencies_ms": [],
               "pos_scores": [], "neg_scores": [], "wrong_top": []}

    for item in TEST_SET:
        q = item["query"]
        docs = [
            {"text": item["relevant"]},
            {"text": item["distractors"][0]},
            {"text": item["distractors"][1]},
            {"text": item["distractors"][2]},
        ]

        t0 = time.perf_counter()
        ranked = rerank(q, docs, top_k=len(docs))
        t1 = time.perf_counter()
        results["latencies_ms"].append((t1 - t0) * 1000)

        if not ranked:
            continue

        results["total"] += 1
        pos_score = None
        neg_scores = []
        for c in ranked:
            if c["text"] == item["relevant"]:
                pos_score = c.get("rerank_score", -99)
            else:
                neg_scores.append(c.get("rerank_score", -99))

        if pos_score is not None:
            results["pos_scores"].append(pos_score)
            results["neg_scores"].extend(neg_scores)

        # Check if relevant doc is ranked first
        if ranked and ranked[0]["text"] == item["relevant"]:
            results["correct"] += 1
        else:
            results["wrong_top"].append({
                "q": q[:40],
                "pos_score": pos_score,
                "top_score": ranked[0].get("rerank_score", -99) if ranked else -99,
            })

    pos_avg = statistics.mean(results["pos_scores"]) if results["pos_scores"] else 0
    neg_avg = statistics.mean(results["neg_scores"]) if results["neg_scores"] else 0
    lat_avg = statistics.mean(results["latencies_ms"]) if results["latencies_ms"] else 0

    return {
        "label": label,
        "correct@1": f"{results['correct']}/{results['total']}",
        "correct_pct": round(results['correct'] / results['total'] * 100, 1) if results['total'] else 0,
        "pos_score_avg": round(pos_avg, 4),
        "neg_score_avg": round(neg_avg, 4),
        "sep_margin": round(pos_avg - neg_avg, 4),
        "pos_scores": results["pos_scores"],
        "neg_scores": results["neg_scores"],
        "latency_ms": round(lat_avg, 1),
    }


def print_report(embed_results, rerank_results):
    """Pretty-print comparison table."""
    print("\n" + "="*70)
    print("  NVIDIA vs DashScope — Embedding & Reranker Benchmark")
    print("="*70)

    # Config info
    print(f"\n  📋 Active Config:")
    print(f"     Embedding dim: {settings.embedding_dim}")
    providers = []
    if settings.dashscope_api_key: providers.append("DashScope")
    if settings.siliconflow_api_key: providers.append("SiliconFlow")
    if settings.openrouter_api_key: providers.append("OpenRouter")
    print(f"     Available embedding providers: {', '.join(providers) if providers else 'NONE'}")
    print(f"     Rerank provider: {settings.rerank.rerank_provider}")

    # Embedding comparison
    print(f"\n  📊 Embedding Quality Comparison")
    print(f"  {'─'*58}")
    header = f"  {'Metric':<30} {'NVIDIA (OpenRouter)':<20}"
    print(header)
    print(f"  {'─'*58}")
    r = embed_results
    print(f"  {'Vector dimension':<30} {r['dim']:<20}")
    print(f"  {'Correct@1':<30} {r['correct@1']:<20}")
    print(f"  {'Correct@1 rate':<30} {r['correct@1_pct']}%")
    print(f"  {'Relevant doc avg sim':<30} {r['pos_sim_avg']:<20}")
    print(f"  {'Distractor avg sim':<30} {r['neg_sim_avg']:<20}")
    print(f"  {'Separation margin':<30} {r['sep_margin']:<20}")
    print(f"  {'Avg embedding latency':<30} {r['latency_ms']}ms")
    print(f"  {'Failures':<30} {r['failures']}")
    print(f"  {'─'*58}")

    if r["failures"] > 0:
        print(f"\n  ⚠️  Failures:")
        for f in r["failure_detail"]:
            print(f"     - {f['q']}: pos_sim={f.get('pos_sim','?')}, top_neg={f.get('top_neg_sim','?')}")

    # Rerank comparison
    print(f"\n  📊 Rerank Quality Comparison")
    print(f"  {'─'*58}")
    print(f"  {'Metric':<30} {'NVIDIA (OpenRouter)':<20}")
    print(f"  {'─'*58}")
    r2 = rerank_results
    print(f"  {'Correct@1':<30} {r2['correct@1']:<20}")
    print(f"  {'Correct@1 rate':<30} {r2['correct_pct']}%")
    print(f"  {'Relevant doc avg score':<30} {r2['pos_score_avg']:<20}")
    print(f"  {'Distractor avg score':<30} {r2['neg_score_avg']:<20}")
    print(f"  {'Separation margin':<30} {r2['sep_margin']:<20}")
    print(f"  {'Avg rerank latency':<30} {r2['latency_ms']}ms")
    print(f"  {'─'*58}")

    # Summary
    print(f"\n  💡 Summary")
    print(f"  {'─'*58}")
    if r["sep_margin"] > 0:
        print(f"  ✓ Embedding: relevant/irrelevant separation = {r['sep_margin']}")
    if r2["sep_margin"] > 0:
        print(f"  ✓ Reranker: relevant/irrelevant separation = {r2['sep_margin']}")

    # Score distribution
    print(f"\n  📈 Score Distribution")
    print(f"  {'─'*58}")
    print(f"  Embedding — Relevant sims: min={min(r['pos_sims']):.4f} " +
          f"max={max(r['pos_sims']):.4f} mean={r['pos_sim_avg']:.4f}")
    print(f"  Embedding — Distractor sims: min={min(r['neg_sims']):.4f} " +
          f"max={max(r['neg_sims']):.4f} mean={r['neg_sim_avg']:.4f}")
    print(f"  Reranker  — Relevant scores: min={min(r2['pos_scores']):.4f} " +
          f"max={max(r2['pos_scores']):.4f} mean={r2['pos_score_avg']:.4f}")
    print(f"  Reranker  — Distractor scores: min={min(r2['neg_scores']):.4f} " +
          f"max={max(r2['neg_scores']):.4f} mean={r2['neg_score_avg']:.4f}")
    print(f"  {'─'*58}")

    # Raw scores per query
    print(f"\n  📋 Per-Query Detail — Rerank Scores")
    print(f"  {'─'*58}")
    for item in TEST_SET:
        q = item["query"]
        docs = [{"text": item["relevant"]}] + [{"text": d} for d in item["distractors"]]
        ranked = rerank(q, docs, top_k=len(docs))
        if ranked:
            scores = {c["text"][:30]: c.get("rerank_score", -99) for c in ranked}
            relevant_score = scores.get(item["relevant"][:30], -99)
            is_correct = max(scores.values()) == relevant_score if scores else False
            print(f"  {'✅' if is_correct else '❌'} {q[:50]}")
            for txt, score in scores.items():
                marker = " ←" if txt == item["relevant"][:30] else ""
                print(f"     {score:.4f}  {txt}{marker}")


def main():
    print("="*70)
    print("  NVIDIA vs DashScope — Embedding & Reranker Benchmark")
    print("="*70)
    print(f"\n  Config: dim={settings.embedding_dim}")

    # ── Embedding test ──
    print("\n\n  [1/2] Testing NVIDIA embedding quality...")

    def nvidia_embed(texts):
        return embed_texts_llm(texts, batch_size=4)

    embed_results = test_embedding_quality("NVIDIA (OpenRouter)", nvidia_embed)
    print(f"  ✅ Correct@{embed_results['correct@1']} | "
          f"sep={embed_results['sep_margin']:.4f} | "
          f"lat={embed_results['latency_ms']}ms")

    # ── Rerank test ──
    print("\n  [2/2] Testing NVIDIA reranker...")
    rerank_results = test_rerank_quality("NVIDIA (OpenRouter)")
    print(f"  ✅ Correct@{rerank_results['correct@1']} | "
          f"sep={rerank_results['sep_margin']:.4f} | "
          f"lat={rerank_results['latency_ms']}ms")

    # ── Report ──
    print_report(embed_results, rerank_results)

    # Export to JSON
    output = {
        "config": {"dim": settings.embedding_dim},
        "embedding": embed_results,
        "reranker": rerank_results,
    }
    report_path = Path(__file__).parent / "benchmark_nvidia_result.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  📁 Results saved to: {report_path}")


if __name__ == "__main__":
    main()
