"""AI Platform API Router"""
from fastapi import APIRouter, Query
from app.ai_platform import (
    LLMProvider,
    ConfidenceScore,
    ConversationSession,
    ConversationMessage,
    create_llm_provider,
    list_llm_providers,
    delete_llm_provider,
    calculate_confidence,
    save_confidence_score,
    create_conversation_session,
    add_conversation_message,
    get_conversation_history,
    get_session_context,
)

router = APIRouter(prefix="/api/ai-platform", tags=["AI Platform"])


# ── LLM Provider Endpoints ──

@router.post("/providers", response_model=LLMProvider, status_code=201)
async def create_provider(provider: LLMProvider):
    """创建 LLM 提供商"""
    return create_llm_provider(provider)


@router.get("/providers", response_model=list[LLMProvider])
async def list_providers():
    """列出所有 LLM 提供商"""
    return list_llm_providers()


@router.delete("/providers/{name}", status_code=204)
async def delete_provider(name: str):
    """删除 LLM 提供商"""
    success = delete_llm_provider(name)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Provider not found")


# ── Confidence Scoring Endpoints ──

@router.post("/confidence/calculate")
async def calculate_confidence_endpoint(
    retrieved_chunks: list[dict],
    cited_chunks: list[dict],
    query: str,
):
    """计算置信度分数"""
    score = calculate_confidence(retrieved_chunks, cited_chunks, query)
    return score


@router.post("/confidence", status_code=201)
async def save_confidence(score: ConfidenceScore):
    """保存置信度分数"""
    score_id = save_confidence_score(score)
    return {"id": score_id, "status": "created"}


# ── Conversation Endpoints ──

@router.post("/sessions", response_model=ConversationSession, status_code=201)
async def create_session(session: ConversationSession):
    """创建对话会话"""
    return create_conversation_session(session)


@router.post("/sessions/{session_id}/messages", status_code=201)
async def add_message(session_id: str, message: ConversationMessage):
    """添加对话消息"""
    message.session_id = session_id
    message_id = add_conversation_message(message)
    return {"id": message_id, "status": "created"}


@router.get("/sessions/{session_id}/history")
async def message_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=500),
):
    """获取对话历史"""
    return {"messages": get_conversation_history(session_id, limit)}


@router.get("/sessions/{session_id}/context")
async def session_context(
    session_id: str,
    max_tokens: int = Query(4000, ge=100, le=16000),
):
    """获取会话上下文"""
    return {"context": get_session_context(session_id, max_tokens)}
