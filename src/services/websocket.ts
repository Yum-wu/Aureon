// src/services/websocket.ts

export interface WebSocketMessage {
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceItem[];
  timestamp: Date;
}

export interface SourceItem {
  title: string;
  slug: string;
  chunk?: string;
  score?: number;
}

export interface ToolCall {
  tool_name: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  tool_args: Record<string, any>;
  call_id: string;
}

export interface ToolResult {
  call_id: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  result: any;
  success: boolean;
  error?: string;
}

type MessageHandler = (message: WebSocketMessage) => void;
type ConnectionHandler = (connected: boolean) => void;

export class AureonWebSocket {
  private ws: WebSocket | null = null;
  private clientId: string;
  private conversationId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;

  private messageHandlers: Map<string, MessageHandler[]> = new Map();
  private connectionHandlers: ConnectionHandler[] = [];

  constructor(clientId: string) {
    this.clientId = clientId;
  }

  /**
   * Connect to WebSocket server.
   */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = `ws://localhost:8000/ws/chat/${this.clientId}`;

      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.notifyConnectionHandlers(true);
        resolve();
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        this.stopHeartbeat();
        this.notifyConnectionHandlers(false);

        if (!event.wasClean) {
          this.attemptReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };
    });
  }

  /**
   * Disconnect from WebSocket server.
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.stopHeartbeat();
  }

  /**
   * Send message to server.
   */
  send(message: WebSocketMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected');
      return;
    }

    this.ws.send(JSON.stringify(message));
  }

  /**
   * Send user message.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sendUserMessage(query: string, metadata?: Record<string, any>): void {
    this.send({
      type: 'user_message',
      query,
      metadata,
      conversation_id: this.conversationId,
    });
  }

  /**
   * Send tool result.
   */
  sendToolResult(toolResult: ToolResult): void {
    this.send({
      type: 'tool_result',
      ...toolResult,
      conversation_id: this.conversationId,
    });
  }

  /**
   * Register message handler.
   */
  onMessage(type: string, handler: MessageHandler): void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, []);
    }
    this.messageHandlers.get(type)!.push(handler);
  }

  /**
   * Register connection handler.
   */
  onConnection(handler: ConnectionHandler): void {
    this.connectionHandlers.push(handler);
  }

  /**
   * Handle incoming message.
   */
  private handleMessage(message: WebSocketMessage): void {
    const { type } = message;

    // Store conversation ID
    if (message.conversation_id) {
      this.conversationId = message.conversation_id;
    }

    // Call registered handlers
    const handlers = this.messageHandlers.get(type) || [];
    handlers.forEach((handler) => handler(message));
  }

  /**
   * Start heartbeat monitoring.
   */
  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      this.send({ type: 'heartbeat' });
    }, 30000); // Every 30 seconds
  }

  /**
   * Stop heartbeat monitoring.
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Attempt to reconnect with exponential backoff.
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect().catch(console.error);
    }, delay);
  }

  /**
   * Notify connection handlers.
   */
  private notifyConnectionHandlers(connected: boolean): void {
    this.connectionHandlers.forEach((handler) => handler(connected));
  }

  /**
   * Get current conversation ID.
   */
  getConversationId(): string | null {
    return this.conversationId;
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton instance
let websocketInstance: AureonWebSocket | null = null;

/**
 * Get or create WebSocket instance.
 */
export function getWebSocket(clientId?: string): AureonWebSocket {
  if (!websocketInstance) {
    websocketInstance = new AureonWebSocket(clientId || 'default');
  }
  return websocketInstance;
}

/**
 * Disconnect and cleanup WebSocket.
 */
export function disconnectWebSocket(): void {
  if (websocketInstance) {
    websocketInstance.disconnect();
    websocketInstance = null;
  }
}
