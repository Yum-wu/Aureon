"""
Language detection utility for dynamic prompt selection.

Detects whether user input is primarily English or Chinese,
so the system can respond in the matching language.
"""

import re

# Unicode ranges
_CJK_RANGE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")
_ASCII_RANGE = re.compile(r"[a-zA-Z0-9\s.,!?;:\'\"\-_/@#$%^&*()+=<>\[\]{}|`~]")


def detect_language(text: str) -> str:
    """Detect if input is English or Chinese.

    Returns ``"en"`` when the text is primarily ASCII (English),
    ``"zh"`` when it contains significant CJK characters or Chinese
    question patterns (even when mixed with English technical terms).

    Empty or very short strings default to ``"en"``.
    """
    if not text or not text.strip():
        return "en"

    cjk_count = len(_CJK_RANGE.findall(text))
    ascii_count = len(_ASCII_RANGE.findall(text))
    total = cjk_count + ascii_count

    if total == 0:
        return "en"

    cjk_ratio = cjk_count / total

    # 中文疑问句式检测：即使英文术语多，只要含中文疑问词就判为中文
    _zh_question_patterns = re.compile(
        r"[什么|怎么|如何|为什么|哪些|哪个|是否|能否|可以|请问|区别|差异|对比|比较|解释|说明]"
        r"|[？]"  # 中文问号
    )
    if _zh_question_patterns.search(text):
        return "zh"

    return "zh" if cjk_ratio > 0.3 else "en"


def lang_label(lang: str) -> str:
    """Return human-friendly label for the given language code."""
    return "中文" if lang == "zh" else "English"


def lang_instruction(lang: str) -> str:
    """Return a prompt fragment instructing the model which language to use."""
    return f"\n请用{lang_label(lang)}回复。"
