"""CRAG-style retrieval quality confidence gating.

After retrieval, evaluates the top RRF score to determine retrieval quality:
- 'correct': high confidence, proceed to generation
- 'ambiguous': medium confidence, generate with uncertainty marker
- 'incorrect': low confidence, refuse to answer

Based on CRAG (arXiv:2401.15884) three-way branching.
Reference: docs/RAG_OPTIMIZATION_PROMPT.md section 2.2
"""

from typing import List, Dict, Any
import structlog
from app.config import settings

logger = structlog.get_logger()

CRAG_HIGH_CONFIDENCE = settings.crag_high_confidence
CRAG_LOW_CONFIDENCE = settings.crag_low_confidence


def evaluate_retrieval_confidence(chunks: List[Dict[str, Any]]) -> str:
    """Evaluate retrieval quality based on top RRF score.

    Args:
        chunks: Retrieved chunks with 'score' field (RRF or reranker score)
    Returns:
        'correct' | 'ambiguous' | 'incorrect'
    """
    if not chunks:
        return "incorrect"
    top_score = chunks[0].get("score", 0)
    if top_score >= CRAG_HIGH_CONFIDENCE:
        return "correct"
    elif top_score >= CRAG_LOW_CONFIDENCE:
        return "ambiguous"
    else:
        return "incorrect"


def lightweight_crag_assess(
    chunks: list,
    high_threshold: float = 0.80,
    low_threshold: float = 0.50,
) -> str:
    """基于检索分数的轻量 CRAG 评估器。

    使用检索结果的相关性分数（score 字段）判断检索质量，
    无需额外 LLM 调用，延迟仅 +50-100ms。

    Args:
        chunks: 检索结果列表，每个包含 score 字段
        high_threshold: 高置信度阈值（默认 0.80）
        low_threshold: 低置信度阈值（默认 0.50）

    Returns:
        "correct" — 检索结果高质量，直接使用
        "ambiguous" — 检索结果中等，可补充但不过滤
        "incorrect" — 检索结果低质量，建议返回无结果
    """
    if not chunks:
        return "incorrect"

    # 使用检索结果中的 score 字段（已是相似度分数）
    similarities = []
    for chunk in chunks[:3]:  # 只看 top 3
        score = chunk.get("score", 0)
        if score is not None:
            similarities.append(score)

    if not similarities:
        return "ambiguous"

    max_sim = max(similarities)

    if max_sim >= high_threshold:
        return "correct"
    elif max_sim >= low_threshold:
        return "ambiguous"
    else:
        return "incorrect"


def build_answer_with_confidence(answer: str, confidence: str, lang: str = "en") -> str:
    """Wrap answer with confidence marker based on retrieval quality.

    Args:
        answer: Generated answer text
        confidence: One of 'correct', 'ambiguous', 'incorrect'
        lang: Language code ('en' or 'zh')
    Returns:
        Answer with optional confidence warning prepended
    """
    if confidence == "correct":
        return answer
    if confidence == "ambiguous":
        if lang == "zh":
            return f"⚠️ 以下回答基于有限的参考信息，可能不完整：\n\n{answer}"
        return f"⚠️ The following answer is based on limited reference information and may be incomplete:\n\n{answer}"
    # incorrect
    if lang == "zh":
        return "抱歉，知识库中没有找到与您问题相关的信息。请尝试换个问法，或联系管理员确认知识库是否已覆盖该主题。"
    return "Sorry, no relevant information was found in the knowledge base. Please try rephrasing your question or contact the administrator to confirm coverage."
