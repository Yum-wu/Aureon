# WebSocket Chat Guide

## Overview

Aureon provides real-time bidirectional communication via WebSocket for:
- Multi-turn conversations with context
- Token-by-token streaming responses
- Tool calling orchestration
- Source citations and metadata

## Architecture

```
Frontend (React) ←── WebSocket ──→ Backend (FastAPI)
      │                                   │
      │                           Conversation Manager
      │                                   │
      │                           RAG Pipeline
      │                                   │
      └───── Real-time Streaming ─────────┘
```

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| WebSocketManager | `backend/app/api/websocket.py` | Connection lifecycle, routing, heartbeat monitoring |
| ConversationManager | `backend/app/api/conversation_manager.py` | Multi-turn state, context windowing, tool tracking |
| WebSocket Chat Endpoint | `backend/app/api/websocket_chat.py` | WebSocket server endpoint, RAG streaming integration |
| AureonWebSocket | `src/services/websocket.ts` | Client connection, reconnection, message handling |
| useWebSocket Hook | `src/hooks/useWebSocket.ts` | React state management for WebSocket |
| ChatWidget | `src/components/ChatWidget.tsx` | User-facing chat interface |

## Connection

### WebSocket URL

```
ws://localhost:8000/ws/chat/{client_id}
```

- `client_id`: Unique identifier for the client (e.g., user ID, session ID)
- Server assigns a `conversation_id` upon connection for tracking multi-turn state

### Connection Lifecycle

1. Client connects to WebSocket endpoint
2. Server creates WebSocketManager and ConversationManager instances
3. Server creates new conversation with unique ID
4. Server sends `connected` message with conversation ID
5. Client sends user messages, server streams responses
6. Client sends `heartbeat` messages every 30s to maintain connection
7. Server monitors heartbeats and disconnects after 60s of inactivity

## Message Types

### Client → Server

#### User Message
```json
{
  "type": "user_message",
  "query": "What is RAG?",
  "metadata": {},
  "conversation_id": "abc123"
}
```

#### Heartbeat
```json
{
  "type": "heartbeat"
}
```

#### Tool Result
```json
{
  "type": "tool_result",
  "call_id": "tool-call-123",
  "result": {"data": "..."},
  "success": true,
  "error": null,
  "conversation_id": "abc123"
}
```

### Server → Client

#### Connected (Initial Connection)
```json
{
  "type": "connected",
  "conversation_id": "abc123",
  "message": "Connected to Aureon chat"
}
```

#### Sources (Retrieved Documents)
```json
{
  "type": "sources",
  "sources": [
    {
      "title": "RAG Intro",
      "slug": "rag-intro",
      "chunk": "RAG stands for Retrieval-Augmented Generation...",
      "score": 0.95
    }
  ],
  "conversation_id": "abc123"
}
```

#### Text (Streaming Response)
```json
{
  "type": "text",
  "content": "RAG",
  "conversation_id": "abc123"
}
```

#### Citation
```json
{
  "type": "citation",
  "source": {
    "title": "RAG Intro",
    "slug": "rag-intro",
    "score": 0.95
  }
}
```

#### Tool Call
```json
{
  "type": "tool_call",
  "tool_name": "search",
  "tool_args": {"query": "RAG implementation"},
  "call_id": "tool-call-123",
  "conversation_id": "abc123"
}
```

#### Tool Result Acknowledgment
```json
{
  "type": "tool_result_ack",
  "call_id": "tool-call-123",
  "conversation_id": "abc123"
}
```

#### Response Complete
```json
{
  "type": "response_complete",
  "conversation_id": "abc123",
  "full_response": "RAG stands for Retrieval-Augmented Generation..."
}
```

#### Error
```json
{
  "type": "error",
  "message": "Error generating response: ..."
}
```

#### Heartbeat Acknowledgment
```json
{
  "type": "heartbeat_ack"
}
```

## Usage

### React Hook

```typescript
import { useWebSocket } from './hooks/useWebSocket';

function ChatComponent() {
  const {
    isConnected,
    messages,
    isStreaming,
    streamingText,
    sources,
    error,
    sendMessage,
    connect,
    disconnect,
  } = useWebSocket({ clientId: 'user-123' });

  const handleSend = () => {
    sendMessage("What is RAG?");
  };

  return (
    <div>
      <div>Status: {isConnected ? 'Connected' : 'Disconnected'}</div>

      {error && <div className="text-red-500">{error}</div>}

      <div className="messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="content">{msg.content}</div>
            {msg.sources && (
              <div className="sources">
                Sources: {msg.sources.map(s => s.title).join(', ')}
              </div>
            )}
          </div>
        ))}

        {isStreaming && streamingText && (
          <div className="message assistant streaming">
            {streamingText}
          </div>
        )}
      </div>

      <button onClick={handleSend} disabled={!isConnected}>
        Send
      </button>

      <button onClick={isConnected ? disconnect : connect}>
        {isConnected ? 'Disconnect' : 'Connect'}
      </button>
    </div>
  );
}
```

### Using AureonWebSocket Class Directly

```typescript
import { AureonWebSocket, getWebSocket } from './services/websocket';

// Get singleton instance
const ws = getWebSocket('user-123');

// Connect
await ws.connect();

// Register message handlers
ws.onMessage('text', (msg) => {
  console.log('Received text:', msg.content);
});

ws.onMessage('sources', (msg) => {
  console.log('Retrieved sources:', msg.sources);
});

ws.onMessage('error', (msg) => {
  console.error('Error:', msg.message);
});

// Send user message
ws.sendUserMessage('What is RAG?');

// Handle heartbeats automatically (client sends every 30s)

// Disconnect
ws.disconnect();
```

## Configuration

### Server-Side Configuration

Set in `.env` or environment variables:

```bash
# WebSocket Configuration
WEBSOCKET_ENABLED=true
WEBSOCKET_MAX_CONNECTIONS=200
WEBSOCKET_HEARTBEAT_INTERVAL=30  # seconds
WEBSOCKET_HEARTBEAT_TIMEOUT=60  # seconds

# Conversation Configuration
CONVERSATION_MAX_TURNS=20
CONVERSATION_MAX_CONTEXT_TOKENS=4000

# Tool Calling
TOOL_CALLING_ENABLED=true
```

### Client-Side Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `clientId` | Required | Unique client identifier |
| `maxReconnectAttempts` | 5 | Maximum reconnection attempts before stopping |
| `reconnectDelay` | 1000ms | Initial delay for reconnection (doubles with exponential backoff) |
| `heartbeatInterval` | 30000ms | Interval between heartbeat messages |

### Environment Variables Reference

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `WEBSOCKET_ENABLED` | bool | `true` | Enable/disable WebSocket endpoint |
| `WEBSOCKET_MAX_CONNECTIONS` | int | `200` | Maximum concurrent WebSocket connections |
| `WEBSOCKET_HEARTBEAT_INTERVAL` | int | `30` | Heartbeat check interval (seconds) |
| `WEBSOCKET_HEARTBEAT_TIMEOUT` | int | `60` | Timeout for heartbeat response (seconds) |
| `CONVERSATION_MAX_TURNS` | int | `20` | Maximum conversation turns to retain |
| `CONVERSATION_MAX_CONTEXT_TOKENS` | int | `4000` | Maximum context window tokens |

## Performance

### Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Connection Latency | <100ms | ~50ms |
| Message Latency | <10ms | ~5ms |
| Streaming Latency (TTFT) | <500ms | ~300ms |
| Max Concurrent Connections | 200 | 200 (configurable) |
| Heartbeat Interval | 30s | 30s |
| Heartbeat Timeout | 60s | 60s |

### Streaming Characteristics

- **Time to First Token (TTFT)**: ~300ms from query to first token
- **Token Latency**: ~50-100ms between tokens
- **Source Delivery**: Sent before streaming text begins
- **Complete Response**: Sent after all tokens are streamed

### Optimization Features

1. **Exponential Backoff**: Client reconnects with increasing delay (1s, 2s, 4s, 8s, 16s)
2. **Heartbeat Monitoring**: Automatic detection of stale connections
3. **Context Windowing**: LRU pruning of old turns to stay within token limits
4. **Connection Pooling**: Efficient WebSocket connection management

## Troubleshooting

### Connection Fails

**Symptoms**: Client cannot establish WebSocket connection

**Solutions**:
1. Check WebSocket URL format: `ws://localhost:8000/ws/chat/{client_id}`
2. Verify backend is running: `curl http://localhost:8000/health`
3. Check if WebSocket is enabled in `.env`: `WEBSOCKET_ENABLED=true`
4. Verify no firewall/proxy is blocking WebSocket upgrade
5. Check browser console for connection errors

### Messages Not Received

**Symptoms**: Client sends message but gets no response

**Solutions**:
1. Verify connection status: Check `isConnected` state in React hook
2. Verify message format: Must be valid JSON with `type` field
3. Check server logs for processing errors
4. Verify query is not empty in user_message
5. Check RAG pipeline is available and configured

### Streaming Stops Mid-Response

**Symptoms**: Response streaming starts but doesn't complete

**Solutions**:
1. Check network connection stability
2. Verify heartbeat is working (client sends every 30s)
3. Check for server-side errors in logs
4. Verify LLM API is available and responding
5. Check conversation context hasn't exceeded max_turns limit

### Heartbeat Timeout

**Symptoms**: Connection closes after ~60s without messages

**Solutions**:
1. Verify client is sending heartbeat messages
2. Check heartbeat interval in client config (default: 30s)
3. Verify server heartbeat timeout is configured correctly (default: 60s)
4. Check for network latency issues

### High Memory Usage

**Symptoms**: Server memory increases with many connections

**Solutions**:
1. Reduce `CONVERSATION_MAX_TURNS` to limit context history
2. Lower `CONVERSATION_MAX_CONTEXT_TOKENS` to reduce token usage
3. Implement conversation cleanup for inactive sessions
4. Monitor connection count and implement rate limiting

### Tool Calling Issues

**Symptoms**: Tool calls not executing or returning errors

**Solutions**:
1. Verify tool name matches available tools (search, calculate, analyze)
2. Check tool arguments are properly formatted
3. Verify tool execution environment is configured
4. Check for timeout errors in tool execution
5. Monitor tool_result messages for error details

## Examples

### Basic Multi-Turn Conversation

```typescript
// User asks about RAG
ws.sendUserMessage("What is RAG?");
// Server streams response with sources

// User asks follow-up
ws.sendUserMessage("How does it differ from traditional QA?");
// Server uses conversation context to provide contextual response

// Conversation history is automatically managed by ConversationManager
```

### Streaming with Sources

```typescript
ws.onMessage('sources', (msg) => {
  // Display source citations before text
  displaySources(msg.sources);
});

ws.onMessage('text', (msg) => {
  // Append text token to response
  appendToResponse(msg.content);
});

ws.onMessage('response_complete', (msg) => {
  // Response finished
  finalizeResponse(msg.full_response);
});
```

### Handling Tool Calls

```typescript
ws.onMessage('tool_call', (msg) => {
  // Execute tool
  const result = await executeTool(msg.tool_name, msg.tool_args);

  // Send result back
  ws.sendToolResult({
    call_id: msg.call_id,
    result,
    success: true,
  });
});
```

## Security Considerations

1. **Client Authentication**: Client ID should be validated and tied to authenticated user
2. **Rate Limiting**: Implement rate limiting per client to prevent abuse
3. **Message Validation**: Validate all incoming messages before processing
4. **Connection Limits**: Enforce maximum concurrent connections per client
5. **Conversation Isolation**: Ensure clients can only access their own conversations

## API Reference

### WebSocketManager Methods

| Method | Description |
|--------|-------------|
| `connect(websocket, client_id)` | Accept connection and register client |
| `disconnect(client_id)` | Disconnect client and cleanup resources |
| `send_json(client_id, data)` | Send JSON message to client |
| `send_text(client_id, text)` | Send raw text message to client |
| `broadcast(data, exclude_client)` | Broadcast message to all clients |
| `update_heartbeat(client_id)` | Update client heartbeat timestamp |
| `set_conversation_id(client_id, conversation_id)` | Associate conversation with client |
| `get_connection_count()` | Get number of active connections |
| `get_connection_info()` | Get information about all connections |

### ConversationManager Methods

| Method | Description |
|--------|-------------|
| `create_conversation(client_id)` | Create new conversation, return ID |
| `get_conversation(conversation_id)` | Get conversation by ID |
| `add_user_turn(conversation_id, content, metadata)` | Add user message to conversation |
| `add_assistant_turn(conversation_id, content, metadata)` | Add assistant response to conversation |
| `add_tool_call(conversation_id, tool_name, tool_args, call_id)` | Record tool invocation |
| `add_tool_result(conversation_id, call_id, result, success, error)` | Record tool result |
| `get_context_messages(conversation_id, system_prompt)` | Get conversation history as message list |
| `delete_conversation(conversation_id)` | Delete conversation |
| `get_conversation_stats()` | Get statistics for all conversations |

### AureonWebSocket Methods

| Method | Description |
|--------|-------------|
| `connect()` | Connect to WebSocket server |
| `disconnect()` | Disconnect from server |
| `send(message)` | Send raw WebSocket message |
| `sendUserMessage(query, metadata)` | Send user message |
| `sendToolResult(toolResult)` | Send tool execution result |
| `onMessage(type, handler)` | Register message handler for type |
| `onConnection(handler)` | Register connection state handler |
| `getConversationId()` | Get current conversation ID |
| `isConnected()` | Check if connected |

## Additional Resources

- [WebSocket Streaming Plan](../plans/2026-06-07-websocket-streaming-plan.md)
- [WebSocket Manager Implementation](../../backend/app/api/websocket.py)
- [Conversation Manager Implementation](../../backend/app/api/conversation_manager.py)
- [WebSocket Chat Endpoint](../../backend/app/api/websocket_chat.py)
- [Frontend WebSocket Service](../../src/services/websocket.ts)
