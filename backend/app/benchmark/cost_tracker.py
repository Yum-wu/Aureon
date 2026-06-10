"""Cost tracking for API usage."""

from dataclasses import dataclass
from typing import Dict, List
from .config import PRICING


@dataclass
class TokenUsage:
    """Token usage for a single request."""
    embedding: int = 0
    rerank: int = 0
    llm: int = 0
    total: int = 0


class CostTracker:
    """Track API usage and estimate costs."""

    def __init__(self):
        self.usages: List[TokenUsage] = []

    def record(self, usage: TokenUsage):
        """Record token usage for a request."""
        self.usages.append(usage)

    def summary(self) -> Dict:
        """Calculate cost summary across all recorded usages."""
        total = TokenUsage()
        for u in self.usages:
            total.embedding += u.embedding
            total.rerank += u.rerank
            total.llm += u.llm
            total.total += u.total

        # Calculate costs using pricing table
        embedding_cost = total.embedding * PRICING["dashscope_embedding"] / 1000
        rerank_cost = total.rerank * PRICING["dashscope_rerank"] / 1000
        total_cost = embedding_cost + rerank_cost

        num_queries = len(self.usages)
        avg_tokens = total.total // max(num_queries, 1)

        return {
            "total_tokens": total.total,
            "embedding_tokens": total.embedding,
            "rerank_tokens": total.rerank,
            "llm_tokens": total.llm,
            "estimated_cost_usd": round(total_cost, 4),
            "queries": num_queries,
            "avg_tokens_per_query": avg_tokens,
            "cost_per_query_usd": round(total_cost / max(num_queries, 1), 6),
        }

    def reset(self):
        """Clear all recorded usages."""
        self.usages.clear()
