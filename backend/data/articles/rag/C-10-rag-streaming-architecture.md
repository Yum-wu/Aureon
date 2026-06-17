# RAG 流式架构：SSE 与增量生成

## 流式输出的必要性

传统 RAG 系统等待完整答案生成后一次性返回，用户需要等待 5-10 秒才能看到任何输出。流式输出通过 Server-Sent Events（SSE）逐步推送生成内容，显著改善用户体验——用户在 1 秒内就能看到答案的开头。

## SSE 协议

### 基本格式

SSE 是基于 HTTP 的单向推送协议，格式简单：

```
event: message
data: {"content": "RAG 是"}

event: message
data: {"content": "检索增强"}

event: message
data: {"content": "生成技术"}

event: done
data: {}
```

### FastAPI 实现

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式聊天端点"""
    return StreamingResponse(
        stream_chat(request),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )

async def stream_chat(request: ChatRequest):
    """流式生成聊天响应"""
    session_id = request.session_id or str(uuid.uuid4())

    # 发送 session 事件
    yield sse_event("session", {"session_id": session_id})

    # 检索
    docs = await retriever.aretrieve(request.message, k=5)

    # 流式生成
    full_answer = ""
    async for chunk in llm.astream(generate_prompt(request.message, docs)):
        full_answer += chunk
        yield sse_event("text", {"content": chunk})

    # 发送完成事件
    yield sse_event("done", {"session_id": session_id})
```

### SSE 工具函数

```python
# common.py 中的 SSE 工具

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

def sse_event(event: str, data: dict) -> str:
    """生成 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

## 增量生成架构

### 事件类型设计

```python
# SSE 事件类型
EVENT_TYPES = {
    "session": "会话创建，返回 session_id",
    "text": "文本增量输出",
    "tool_start": "工具调用开始",
    "tool_end": "工具调用结束",
    "retrieval_start": "检索开始",
    "retrieval_end": "检索结束",
    "rerank_start": "Rerank 开始",
    "rerank_end": "Rerank 结束",
    "done": "生成完成",
    "error": "错误信息",
}
```

### 流式 RAG Pipeline

```python
async def stream_rag_pipeline(
    query: str,
    session_id: str,
    embedder,
    vectorstore,
    reranker,
    llm,
):
    """流式 RAG Pipeline"""
    # 1. 发送会话事件
    yield sse_event("session", {"session_id": session_id})

    # 2. 检索阶段
    yield sse_event("retrieval_start", {"query": query})

    query_embedding = await embedder.aembed_query(query)
    docs = await vectorstore.asimilarity_search_by_vector(query_embedding, k=20)

    yield sse_event("retrieval_end", {"doc_count": len(docs)})

    # 3. Rerank 阶段
    yield sse_event("rerank_start", {})
    reranked = await reranker.arerank(query, docs, top_k=5)
    yield sse_event("rerank_end", {"doc_count": len(reranked)})

    # 4. 流式生成阶段
    context = "\n\n".join([doc.page_content for doc in reranked])
    prompt = f"基于以下上下文回答问题：\n\n{context}\n\n问题：{query}\n\n回答："

    full_answer = ""
    async for chunk in llm.astream(prompt):
        full_answer += chunk
        yield sse_event("text", {"content": chunk})

    # 5. 完成事件
    yield sse_event("done", {
        "session_id": session_id,
        "answer_length": len(full_answer),
        "doc_ids": [doc.metadata.get("id") for doc in reranked],
    })
```

### Agent 流式输出

```python
async def stream_agent_response(
    query: str,
    session_id: str,
    agent,
    config: dict,
):
    """Agent 流式输出，包含工具调用事件"""
    yield sse_event("session", {"session_id": session_id})

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=query)]},
        version="v2",
        config=config,
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            # LLM 输出流
            token = event["data"]["chunk"].content
            if token:
                yield sse_event("text", {"content": token})

        elif kind == "on_tool_start":
            # 工具调用开始
            tool_name = event["name"]
            yield sse_event("tool_start", {"tool": tool_name})

        elif kind == "on_tool_end":
            # 工具调用结束
            tool_name = event["name"]
            yield sse_event("tool_end", {"tool": tool_name})

    yield sse_event("done", {"session_id": session_id})
```

## 前端 SSE 消费

### React 实现

```typescript
// services/chatService.ts
export async function streamChat(
  message: string,
  onEvent: (event: SSEEvent) => void,
  sessionId?: string,
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  while (reader) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value);
    const lines = text.split("\n");

    let currentEvent = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7);
      } else if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        onEvent({ event: currentEvent, data });
      }
    }
  }
}
```

### 消息渲染

```typescript
// hooks/useChatStream.ts
export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = async (content: string) => {
    const userMessage = { role: "user", content };
    setMessages(prev => [...prev, userMessage]);
    setIsStreaming(true);

    let assistantContent = "";
    setMessages(prev => [...prev, { role: "assistant", content: "" }]);

    await streamChat(content, (event) => {
      if (event.event === "text") {
        assistantContent += event.data.content;
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: assistantContent,
          };
          return updated;
        });
      } else if (event.event === "done") {
        setIsStreaming(false);
      }
    });
  };

  return { messages, isStreaming, sendMessage };
}
```

## 流式优化

### 首 Token 延迟（TTFT）优化

```python
# TTFT 优化策略
# 1. 检索与 Prompt 构建并行
# 2. 使用流式 LLM API
# 3. 减少检索候选数（Rerank 前少取）
# 4. 跳过不必要的步骤（自适应 Rerank）

async def optimized_stream_rag(query: str, session_id: str):
    """优化 TTFT 的流式 RAG"""
    yield sse_event("session", {"session_id": session_id})

    # 并行：检索 + 查询路由
    retrieve_task = hybrid_search(query)
    route_task = query_router.route(query)
    docs, route = await asyncio.gather(retrieve_task, route_task)

    # 简单查询：跳过 Rerank，直接生成
    if route == "simple":
        context = docs[0].page_content if docs else ""
    else:
        # Rerank
        docs = await reranker.arerank(query, docs, top_k=5)
        context = "\n\n".join([d.page_content for d in docs])

    # 流式生成
    async for chunk in llm.astream(f"基于：{context}\n问题：{query}\n回答："):
        yield sse_event("text", {"content": chunk})

    yield sse_event("done", {"session_id": session_id})
```

## 关键事实

1. **SSE（Server-Sent Events）是 RAG 流式输出的标准协议**，基于 HTTP 单向推送，格式为 `event: type\ndata: json\n\n`
2. **Aureon 的 SSE 事件类型**包括 session、text、tool_start、tool_end、retrieval_start、retrieval_end、done、error
3. **流式生成使用 `llm.astream()` 逐 Token 推送**，用户在 1 秒内即可看到答案开头，TTFT P50 为 610ms
4. **Agent 流式输出通过 `astream_events(version="v2")` 实现**，可以同时推送 LLM 输出和工具调用事件
5. **TTFT 优化的关键是检索与 Prompt 构建并行**，以及通过查询路由跳过不必要的步骤
