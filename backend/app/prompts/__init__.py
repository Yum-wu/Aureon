"""Prompt templates — centralized system prompts with language support."""

from app.prompts.agent import SYSTEM_PROMPT_ZH, SYSTEM_PROMPT_EN

_PROMPTS = {
    "zh": SYSTEM_PROMPT_ZH,
    "en": SYSTEM_PROMPT_EN,
}


def get_system_prompt(lang: str = "zh") -> str:
    """Return the agent system prompt for the given language code."""
    return _PROMPTS.get(lang, _PROMPTS["zh"])
