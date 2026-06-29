"""
Agent 执行节点。
封装 P0 LangChain Agent，同步调用。
使用实例缓存避免重复创建。
"""

import threading
from typing import Any

from langchain_core.messages import HumanMessage

from app.tools import ALL_TOOLS
from app.agent.llm import create_llm
from app.agent.agent import create_chat_agent


# ── Instance caches ──
_llm_cache: dict[str, Any] = {}
_agent_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _get_cached_llm(model: str = None) -> Any:
    """Get or create a cached LLM instance."""
    cache_key = model or "default"
    if cache_key not in _llm_cache:
        with _cache_lock:
            if cache_key not in _llm_cache:
                _llm_cache[cache_key] = create_llm(model=model)
    return _llm_cache[cache_key]


def _get_cached_agent(model: str = None) -> Any:
    """Get or create a cached Agent instance."""
    cache_key = model or "default"
    if cache_key not in _agent_cache:
        with _cache_lock:
            if cache_key not in _agent_cache:
                llm = _get_cached_llm(model=model)
                _agent_cache[cache_key] = create_chat_agent(llm, tools=ALL_TOOLS)
    return _agent_cache[cache_key]


_AGENT_SYSTEM_PREFIX = """你是知识库问答助手。基于参考上下文回答用户问题。

规则：
1. 直接回答问题，不要以"根据文档"开头
2. 每个句子必须直接回应用户的问题
3. 不要总结文档内容，直接给出答案
4. 引用来源：[来源: 文章标题]

参考上下文：
{context}
"""


def run_agent_node(query: str, context: str = "", model: str = None) -> tuple:
    """
    Execute P0 agent with tools.
    Returns (agent_result, tool_calls).
    """
    agent = _get_cached_agent(model=model)

    # Combine context + query with proper system instructions
    full_query = query
    if context:
        full_query = f"{_AGENT_SYSTEM_PREFIX.format(context=context)}\n\n用户问题：{query}"

    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=full_query)]},
            {"recursion_limit": 50},
        )
        output = result.get("output", str(result)) if isinstance(result, dict) else str(result)
        return output, []
    except Exception as e:
        return f"Agent 执行出错：{e}", []
