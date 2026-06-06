"""
Production guardrails: hallucination detection, citation verification.
"""
import json
import structlog
import re
from typing import Dict, List, Optional, Tuple

logger = structlog.get_logger()


HALLUCINATION_CHECK_PROMPT = """你是一个事实核查助手。判断以下 AI 回答是否基于提供的参考文档。

判断标准（0-10）：
- 10：完全基于参考文档，无任何编造
- 7-9：大部分基于参考文档，少量合理推断
- 4-6：部分内容不在参考文档中
- 1-3：大量内容不在参考文档中或与文档矛盾
- 0：完全无关或编造

只输出 JSON 格式：{{"score": <int>, "flagged": <bool>, "reason": "<一句话>"}}

参考文档：
{context}

AI 回答：{answer}
"""


def check_hallucination(answer: str, context: str, llm, threshold: int = 5) -> Dict:
    """
    Runtime hallucination check using a fast LLM call.
    Returns dict with: score, flagged (bool), reason.
    """
    prompt = HALLUCINATION_CHECK_PROMPT.format(context=context[:3000], answer=answer[:2000])
    try:
        resp = llm.invoke([{"role": "user", "content": prompt}])
        text = resp.content.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(text)
        score = int(data.get("score", 0))
        flagged = score < threshold
        return {"score": score, "flagged": flagged, "reason": data.get("reason", "")}
    except Exception as e:
        logger.warning("Hallucination check failed: %s", e)
        return {"score": -1, "flagged": False, "reason": str(e)}


def extract_citations(answer: str) -> List[str]:
    """Extract citation text from answer, e.g. [来源: xxx] or [Source: xxx]."""
    pattern = r'\[(?:来源|Source|引用自|引用)\s*[:：]\s*([^\]]+)\]'
    matches = re.findall(pattern, answer, re.IGNORECASE)
    return [m.strip() for m in matches]


def verify_citations(citations: List[str], sources: List[Dict]) -> Dict:
    """
    Check if cited sources exist in the retrieved sources.
    Returns dict with: valid (list), missing (list), all_verified (bool).
    """
    source_titles = {s.get("title", "") for s in sources}
    valid = []
    missing = []
    for cite in citations:
        found = any(cite in title or title in cite for title in source_titles)
        if found:
            valid.append(cite)
        else:
            missing.append(cite)
    return {"valid": valid, "missing": missing, "all_verified": len(missing) == 0}


# -- Prompt Injection Detection --
# OWASP LLM Top 10 #1 risk. Regex-based first line of defense (<1ms).

_INJECTION_PATTERNS = [
    # English patterns
    r"(?i)ignore\s+(all\s+)?previous\s+instructions",
    r"(?i)forget\s+(everything|all)\s+(above|before)",
    r"(?i)you\s+are\s+now\s+(a|an|DAN)",
    r"(?i)new\s+instructions?\s*:",
    r"(?i)system\s*prompt\s*:",
    r"(?i)disregard\s+(all\s+)?(previous|prior)",
    r"(?i)override\s+(your|the)\s+(rules|instructions|system)",
    r"(?i)act\s+as\s+(if\s+)?(you\s+are|a)",
    r"(?i)pretend\s+(to\s+be|you\s+are)",
    r"(?i)roleplay\s+as",
    # Model-specific injection tokens
    r"(?i)\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>",
    r"(?i)<\|im_start\|>|<\|im_end\|>",
    r"(?i)###\s*(System|Instruction)",
    # Chinese patterns
    r"(?i)忽略.*(之前|以上|所有).*(指令|规则|设定)",
    r"(?i)忘记.*(之前|以上).*(一切|内容)",
    r"(?i)你现在是(一个)?",
    r"(?i)扮演(一个)?",
    r"(?i)新(的)?(指令|规则)\s*[:：]",
    r"(?i)系统(提示|指令)\s*[:：]",
]

# Pre-compile for performance
_INJECTION_RE = [re.compile(p) for p in _INJECTION_PATTERNS]


def detect_prompt_injection(text: str) -> Dict:
    """Detect potential prompt injection attempts using regex patterns.

    Fast (<1ms) first-line defense. Returns dict with:
    - detected (bool): whether injection was detected
    - pattern (str): the matched pattern (for logging)
    - risk_level (str): 'high', 'medium', or 'none'

    Based on OWASP LLM Top 10 Prompt Injection Prevention Cheat Sheet.
    """
    if not text or len(text) < 3:
        return {"detected": False, "pattern": "", "risk_level": "none"}

    for pattern in _INJECTION_RE:
        match = pattern.search(text)
        if match:
            return {
                "detected": True,
                "pattern": match.group(),
                "risk_level": "high" if "system" in match.group().lower() or "INST" in match.group() else "medium",
            }

    return {"detected": False, "pattern": "", "risk_level": "none"}


def sanitize_input(text: str, max_length: int = 4000) -> str:
    """Sanitize user input to reduce injection risk.

    - Truncate to max_length
    - Remove angle brackets (prevent XML/HTML injection)
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""
    text = text[:max_length]
    text = re.sub(r'[<>]', '', text)
    return text.strip()
