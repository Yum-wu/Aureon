from langchain.agents import create_agent
from app.tools import ALL_TOOLS
from app.utils.lang_detect import lang_instruction
from app.observability.prompt_manager import register_prompt, get_prompt
from app.prompts import get_system_prompt
from app.prompts.agent import SYSTEM_PROMPT_ZH, SYSTEM_PROMPT_EN


# 注册到 Prompt Manager（LangFuse 可用时会覆盖）
register_prompt("agent_system_prompt_zh", SYSTEM_PROMPT_ZH, "Agent 中文系统提示词")
register_prompt("agent_system_prompt_en", SYSTEM_PROMPT_EN, "Agent 英文系统提示词")


def create_chat_agent(llm, tools=None, system_prompt=None, lang="zh"):
    """Factory: create a LangChain agent graph (v1.x API).

    Args:
        llm: Language model instance.
        tools: List of tools (defaults to ALL_TOOLS).
        system_prompt: Custom prompt (falls back to language-appropriate default).
        lang: Language code ``"en"`` or ``"zh"`` — appends language instruction.
    """
    tools = tools or ALL_TOOLS
    if system_prompt is None:
        if lang == "en":
            system_prompt = get_prompt("agent_system_prompt_en", SYSTEM_PROMPT_EN)
        else:
            system_prompt = get_prompt("agent_system_prompt_zh", SYSTEM_PROMPT_ZH)
    prompt_text = system_prompt
    prompt_text += lang_instruction(lang)

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=prompt_text,
    )
