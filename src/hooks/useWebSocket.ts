/**
 * WebSocket React Hook
 * 封装 createWebSocket，提供声明式 API 和自动清理
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { createWebSocket, type WSConnectionState } from '../services/ws';

interface UseWebSocketOptions {
  /** 消息回调 */
  onMessage?: (data: unknown) => void;
  /** 连接打开回调 */
  onOpen?: () => void;
  /** 连接关闭回调 */
  onClose?: () => void;
  /** 错误回调 */
  onError?: (error: Event) => void;
  /** 是否自动重连，默认 true */
  autoReconnect?: boolean;
}

interface UseWebSocketReturn {
  /** 是否已连接 */
  isConnected: boolean;
  /** 发送消息 */
  send: (data: string | object) => void;
  /** 最后一条消息 */
  lastMessage: unknown;
  /** 手动连接 */
  connect: () => void;
  /** 手动断开 */
  disconnect: () => void;
  /** 连接状态 */
  connectionState: WSConnectionState;
}

export function useWebSocket(
  path: string,
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const { onMessage, onOpen, onClose, onError, autoReconnect = true } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<unknown>(null);
  const [connectionState, setConnectionState] = useState<WSConnectionState>('disconnected');
  const clientRef = useRef<ReturnType<typeof createWebSocket> | null>(null);

  useEffect(() => {
    const client = createWebSocket(path, {
      maxReconnectAttempts: autoReconnect ? Infinity : 0,
    });

    clientRef.current = client;

    // 状态变更监听
    client.onStateChange = (state) => {
      setConnectionState(state);
      setIsConnected(state === 'connected');
    };

    // 消息监听
    const originalOnMessage = client.ws?.onmessage;
    const patchMessageHandler = () => {
      if (client.ws) {
        const wsRef = client.ws;
        wsRef.onmessage = (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data);
            // 忽略 pong 心跳响应
            if (data.type === 'pong') return;
            setLastMessage(data);
            onMessage?.(data);
          } catch {
            // 非 JSON 消息直接传递
            setLastMessage(event.data);
            onMessage?.(event.data);
          }
        };
      }
    };

    // 连接打开时绑定消息处理器和回调
    const originalOnOpen = client.ws?.onopen;
    if (client.ws) {
      const wsRef = client.ws;
      wsRef.onopen = (event) => {
        patchMessageHandler();
        originalOnOpen?.call(wsRef, event);
        onOpen?.();
      };
    }

    // 连接关闭回调
    const originalOnClose = client.ws?.onclose;
    if (client.ws) {
      const wsRef = client.ws;
      wsRef.onclose = (event) => {
        originalOnClose?.call(wsRef, event);
        onClose?.();
      };
    }

    // 错误回调
    if (client.ws) {
      const wsRef = client.ws;
      wsRef.onerror = (event) => {
        onError?.(event);
      };
    }

    // 自动连接
    client.connect();

    // 定期检查并重新绑定消息处理器（重连后 ws 实例会变化）
    const intervalId = setInterval(() => {
      if (client.ws && client.ws.readyState === WebSocket.OPEN) {
        patchMessageHandler();
      }
    }, 2000);

    return () => {
      clearInterval(intervalId);
      client.disconnect();
      clientRef.current = null;
    };
  }, [path, autoReconnect, onMessage, onOpen, onClose, onError]);

  const send = useCallback((data: string | object) => {
    clientRef.current?.send(data);
  }, []);

  const connect = useCallback(() => {
    clientRef.current?.connect();
  }, []);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
  }, []);

  return { isConnected, send, lastMessage, connect, disconnect, connectionState };
}
