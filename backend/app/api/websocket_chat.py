"""WebSocket chat endpoint for real-time streaming responses."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional
import asyncio
import structlog

logger = structlog.get_logger()

router = APIRouter()

# ── Connection-level concurrency limiter ──
_ws_semaphore: Optional[asyncio.Semaphore] = None


def _get_ws_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore based on WEBSOCKET_MAX_CONNECTIONS config."""
    global _ws_semaphore
    if _ws_semaphore is None:
        from app.config import settings
        _ws_semaphore = asyncio.Semaphore(settings.websocket_max_connections)
    return _ws_semaphore


@router.websocket("/ws/chat/{client_id}")
async def websocket_chat(
    websocket: WebSocket,
    client_id: str,
):
    """WebSocket endpoint for real-time chat.

    Handles:
    - Connection lifecycle
    - Multi-turn conversations
    - Streaming RAG responses
    - Tool calling

    Authentication:
    - Header ``X-API-Key`` (preferred, not logged in access logs)
    - First message ``type=auth`` with ``api_key`` field
    - Skipped when ``API_AUTH_KEY`` is not configured

    Message Types:
    - user_message: User input
    - assistant_message: Assistant response (streamed)
    - sources: Retrieved document sources
    - tool_call: Tool invocation request
    - tool_result: Tool execution result
    - error: Error message
    - heartbeat: Connection keepalive
    """
    from app.config import settings
    from app.api.websocket import WebSocketManager
    from app.api.conversation_manager import ConversationManager

    # ── 1. Connection limit check ──
    semaphore = _get_ws_semaphore()
    if semaphore.locked():
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": "Server connection limit reached. Please try again later.",
        })
        await websocket.close(code=1013, reason="Too many connections")
        logger.warning("WS connection rejected: limit reached", client_id=client_id)
        return

    async with semaphore:
        # ── 2. API key authentication (before accepting connection) ──
        authenticated = False
        if settings.api_auth_key:
            # Try header first (preferred — not logged in access logs)
            header_key = websocket.headers.get("x-api-key")
            if header_key:
                if header_key == settings.api_auth_key:
                    authenticated = True
                else:
                    # Reject before accept — no connection established
                    await websocket.close(code=4001, reason="Unauthorized")
                    logger.warning("WS auth failed: bad X-API-Key header", client_id=client_id)
                    return
        else:
            # No auth configured — skip
            authenticated = True

        # Create manager instances (per-connection scope for isolation)
        manager = WebSocketManager()
        conv_manager = ConversationManager()

        # Connect (only after auth check passed)
        await manager.connect(websocket, client_id)

        # Create conversation
        conversation_id = conv_manager.create_conversation(client_id)
        manager.set_conversation_id(client_id, conversation_id)

        try:
            # Send welcome message with conversation ID
            await manager.send_json(client_id, {
                "type": "connected",
                "conversation_id": conversation_id,
                "message": "Connected to Aureon chat",
            })

            while True:
                # Receive message from client
                data = await websocket.receive_json()

                # Handle message type
                message_type = data.get("type", "user_message")

                # ── Auth via first message (if not yet authenticated) ──
                if not authenticated and settings.api_auth_key:
                    msg_api_key = data.get("api_key", "")
                    if msg_api_key == settings.api_auth_key:
                        authenticated = True
                    else:
                        await manager.send_json(client_id, {
                            "type": "error",
                            "message": "Authentication required. Send {\"type\": \"auth\", \"api_key\": \"<key>\"} as first message.",
                        })
                        await manager.disconnect(client_id)
                        return

                if message_type == "auth":
                    # Explicit auth message
                    msg_api_key = data.get("api_key", "")
                    if settings.api_auth_key and msg_api_key == settings.api_auth_key:
                        authenticated = True
                        await manager.send_json(client_id, {
                            "type": "auth_success",
                            "message": "Authenticated successfully.",
                        })
                    else:
                        await manager.send_json(client_id, {
                            "type": "error",
                            "message": "Invalid API key.",
                        })
                        await manager.disconnect(client_id)
                        return
                elif message_type == "user_message":
                    await _handle_user_message(
                        manager, conv_manager, client_id, conversation_id, data
                    )
                elif message_type == "heartbeat":
                    manager.update_heartbeat(client_id)
                    await manager.send_json(client_id, {"type": "heartbeat_ack"})
                elif message_type == "tool_result":
                    await _handle_tool_result(
                        manager, conv_manager, client_id, conversation_id, data
                    )
                else:
                    logger.warning("Unknown message type: %s", message_type)

        except WebSocketDisconnect:
            logger.info("Client disconnected: %s", client_id)
        except Exception as e:
            logger.error("WebSocket error: %s", e, exc_info=True)
            try:
                await manager.send_json(client_id, {
                    "type": "error",
                    "message": "An internal error occurred.",
                })
            except Exception:
                logger.warning("Failed to send error message to client %s", client_id)
        finally:
            await manager.disconnect(client_id)


async def _handle_user_message(
    manager,
    conv_manager,
    client_id: str,
    conversation_id: str,
    data: Dict[str, Any],
):
    """Handle incoming user message."""
    query = data.get("query", "")
    if not query:
        await manager.send_json(client_id, {
            "type": "error",
            "message": "Empty query",
        })
        return

    # Add user turn to conversation
    conv_manager.add_user_turn(conversation_id, query, metadata=data.get("metadata"))

    # Extract mode from metadata
    metadata = data.get("metadata", {})
    mode = metadata.get("mode", "general") if metadata else "general"

    # Get conversation context
    messages = conv_manager.get_context_messages(
        conversation_id,
        system_prompt=_get_system_prompt(mode),
    )

    # Stream RAG response
    await _stream_rag_response(
        manager, conv_manager, client_id, conversation_id, query, messages
    )


async def _stream_rag_response(
    manager,
    conv_manager,
    client_id: str,
    conversation_id: str,
    query: str,
    messages: list,
):
    """Stream RAG response token-by-token."""
    from app.rag.qa_chain import rag_query_astream
    from app.agent.llm import create_llm

    # Create LLM instance
    llm = create_llm(temperature=0.0, streaming=True)

    # Track full response for conversation history
    full_response = ""
    sources = []

    try:
        # Stream response
        async for event in rag_query_astream(query, llm, top_k=3):
            event_type = event.get("type", "")

            if event_type == "sources":
                # Send sources to client
                sources = event.get("sources", [])
                await manager.send_json(client_id, {
                    "type": "sources",
                    "sources": sources,
                    "conversation_id": conversation_id,
                })

            elif event_type == "citation":
                # Send citation to client
                await manager.send_json(client_id, {
                    "type": "citation",
                    "source": event.get("source", {}),
                })

            elif event_type == "text":
                # Send text token to client
                content = event.get("content", "")
                full_response += content

                await manager.send_json(client_id, {
                    "type": "text",
                    "content": content,
                    "conversation_id": conversation_id,
                })

        # Add assistant turn to conversation
        conv_manager.add_assistant_turn(
            conversation_id,
            full_response,
            metadata={"sources": sources, "model": "qwen3.6-flash"},
        )

        # Send completion signal
        await manager.send_json(client_id, {
            "type": "response_complete",
            "conversation_id": conversation_id,
            "full_response": full_response,
        })

    except Exception as e:
        logger.error("Error streaming response: %s", e, exc_info=True)
        await manager.send_json(client_id, {
            "type": "error",
            "message": "An error occurred while generating the response.",
        })


async def _handle_tool_result(
    manager,
    conv_manager,
    client_id: str,
    conversation_id: str,
    data: Dict[str, Any],
):
    """Handle tool execution result."""
    call_id = data.get("call_id")
    result = data.get("result")
    success = data.get("success", True)
    error = data.get("error")

    # Add tool result to conversation
    conv_manager.add_tool_result(
        conversation_id,
        call_id=call_id,
        result=result,
        success=success,
        error=error,
    )

    # Send acknowledgment
    await manager.send_json(client_id, {
        "type": "tool_result_ack",
        "call_id": call_id,
        "conversation_id": conversation_id,
    })


def _get_system_prompt(mode: str = "general") -> str:
    """Get system prompt for conversation.

    Args:
        mode: Conversation mode - 'general' or 'support'
    """
    if mode == "support":
        return """你是 Aureon 企业 AI 知识库平台的客服助手。

你的职责：
1. 帮助访客了解 Aureon 平台的功能和特性
2. 解答部署、配置、使用相关问题
3. 引导访客发现平台的核心价值

产品知识：
- 企业 AI 知识库平台（FastAPI + React 19）
- 核心能力：95% Recall@3 混合搜索、92% Context Precision、97% Faithfulness
- 部署方式：Docker + Railway 一键部署，24 小时内完成
- 支持模型：DeepSeek / GPT-4o / Claude
- 特色功能：Semantic Cache、Adaptive Re-ranking、WebSocket 实时流式

回答规则：
1. 基于检索到的文档回答，不编造信息
2. 简洁专业，每次回答不超过 200 字
3. 适当推荐相关功能（如提到搜索时介绍 Hybrid Search）
4. 无法回答时引导至 /search 页面或联系邮箱
"""
    return """你是 Aureon 企业 AI 知识库助手。

规则：
1. 基于提供的参考文档回答用户问题
2. 如果问题与文档无关，说明无法回答
3. 回答简洁准确，直接针对用户问题
4. 引用来源时使用自然方式标注

你可以使用以下工具：
- search: 搜索知识库
- calculate: 执行计算
- analyze: 分析数据

如果需要使用工具，请调用相应的工具。
"""
