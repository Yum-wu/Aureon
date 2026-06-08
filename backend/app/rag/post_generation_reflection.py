"""Post-generation self-reflection for RAG answers.

After generating an answer, verifies that each key claim is supported
by the reference documents. Based on Self-RAG (ICLR 2024) Reflection Tokens.

Reference: docs/RAG_OPTIMIZATION_PROMPT.md section 2.2 Layer 4
"""

from typing import Callable, Awaitable

import structlog

logger = structlog.get_logger()

_SELF_REFLECTION_PROMPT = """判断以下回答是否被参考文档充分支撑。

用户问题：{query}
参考文档：{context}
生成的回答：{answer}

规则：
1. 如果回答中的每个关键论断都能在参考文档中找到依据，回答 SUPPORTED
2. 如果回答包含推测、编造或文档中没有的信息，回答 NOT_SUPPORTED
3. 如果回答虽然正确但遗漏了重要信息，回答 PARTIAL

只回答 SUPPORTED / NOT_SUPPORTED / PARTIAL，不要其他内容。"""


async def reflect_on_answer(
    query: str,
    context: str,
    answer: str,
    llm_call_fn: Callable[..., Awaitable[str]],
) -> str:
    """Verify answer fidelity against reference documents.

    Args:
        query: User query.
        context: Reference document context.
        answer: Generated answer.
        llm_call_fn: Async callable that takes a prompt string and returns LLM response.

    Returns:
        One of 'supported', 'not_supported', 'partial'.
    """
    prompt = _SELF_REFLECTION_PROMPT.format(
        query=query,
        context=context[:2000],
        answer=answer[:500],
    )
    try:
        response = await llm_call_fn(prompt)
        response_upper = str(response).strip().upper()
        if "NOT_SUPPORTED" in response_upper:
            return "not_supported"
        elif "PARTIAL" in response_upper:
            return "partial"
        else:
            return "supported"
    except Exception as e:
        logger.warning("Self-reflection failed, defaulting to supported: %s", e)
        return "supported"


def wrap_answer_with_reflection(answer: str, reflection: str, lang: str = "en") -> str:
    """Wrap answer with a reflection-based confidence marker.

    Args:
        answer: Original generated answer.
        reflection: Reflection result ('supported', 'not_supported', 'partial').
        lang: Language code ('en' or 'zh').

    Returns:
        Answer, optionally prepended with a warning.
    """
    if reflection == "supported":
        return answer

    if reflection == "not_supported":
        if lang == "zh":
            return f"⚠️ 以下回答可能包含参考文档未支撑的信息，请谨慎参考：\n\n{answer}"
        return (
            "⚠️ The following answer may contain information not fully supported "
            "by the reference documents. Please verify independently:\n\n"
            + answer
        )

    # partial
    if lang == "zh":
        return f"⚠️ 以下回答基于参考文档，但可能不完整：\n\n{answer}"
    return (
        "⚠️ The following answer is based on reference documents "
        "but may be incomplete:\n\n"
        + answer
    )
