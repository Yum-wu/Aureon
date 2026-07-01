"""RAG 流水线公共逻辑。避免 rag_query 和 rag_query_astream 之间重复。"""



from app.config import settings
from app.rag.query_classifier import route_retrieval


def should_use_hyde(query_complexity: str) -> bool:
    """HyDE 条件判断：中等和复杂查询启用。"""
    return query_complexity in ("medium", "complex") and settings.hyde_enabled


def determine_query_complexity(query: str) -> str:
    """查询复杂度判断，同步+异步共用。"""
    if settings.query_routing_enabled:
        return route_retrieval(query)
    return "medium"


def should_skip_negative_detection(top_score: float) -> bool:
    """高置信度结果跳过负面检测。"""
    return top_score >= settings.high_score_skip_threshold


def should_run_context_compression(top_score: float) -> bool:
    """上下文压缩条件判断。"""
    return (
        settings.context_compression_enabled
        and top_score < settings.context_compression_threshold
    )
