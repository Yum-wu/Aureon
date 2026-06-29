"""Cost Governance - 成本追踪和 Budget 管理"""
import structlog

logger = structlog.get_logger()


# ── Token 定价 (每 1K tokens) ──
TOKEN_PRICING = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "qwen3.6-flash": {"input": 0.00007, "output": 0.00028},
    "glm-4-flash": {"input": 0.0001, "output": 0.0001},
    "default": {"input": 0.0001, "output": 0.0002},
}


def calculate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    pricing = TOKEN_PRICING.get(model, TOKEN_PRICING["default"])
    cost = (tokens_input / 1000 * pricing["input"]) + (tokens_output / 1000 * pricing["output"])
    return round(cost, 6)
