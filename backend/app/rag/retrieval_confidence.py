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
