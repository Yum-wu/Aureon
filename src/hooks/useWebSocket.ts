/**
 * WebSocket React Hook
 * 封装 createWebSocket，提供声明式 API 和自动清理
 *
 * 关键设计：回调通过 ref 持有，不进入 Effect 依赖，
 * 避免内联回调每次 render 都触发 Effect 清理/重建连接。
 * Effect 仅依赖 [path, autoReconnect]。
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
  /** 最后一条消息（保留向后兼容） */
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
  const { autoReconnect = true } = options;

  // 回调通过 ref 持有，不触发 Effect 重建
  const onMessageRef = useRef(options.onMessage);
  const onOpenRef = useRef(options.onOpen);
  const onCloseRef = useRef(options.onClose);
  const onErrorRef = useRef(options.onError);

  // 每次 render 更新 ref（不影响 Effect）
  useEffect(() => { onMessageRef.current = options.onMessage; }, [options.onMessage]);
  useEffect(() => { onOpenRef.current = options.onOpen; }, [options.onOpen]);
  useEffect(() => { onCloseRef.current = options.onClose; }, [options.onClose]);
  useEffect(() => { onErrorRef.current = options.onError; }, [options.onError]);

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<unknown>(null);
  const [connectionState, setConnectionState] = useState<WSConnectionState>('disconnected');
  const clientRef = useRef<ReturnType<typeof createWebSocket> | null>(null);

  // Effect 仅依赖 path 和 autoReconnect — 路径和重连策略不变时不重建连接
  useEffect(() => {
    if (!path) return;  // 空路径 = 延迟挂载，跳过连接

    const client = createWebSocket(path, {
      maxReconnectAttempts: autoReconnect ? 10 : 0,
      reconnectJitter: true,
      fatalCloseCodes: [4001, 1013],
    });

    clientRef.current = client;

    // 回调通过 ref 间接调用 — 不进入 Effect 依赖
    client.onMessage = (data) => {
      setLastMessage(data);
      onMessageRef.current?.(data);
    };

    client.onOpen = () => {
      onOpenRef.current?.();
    };

    client.onClose = () => {
      onCloseRef.current?.();
    };

    client.onStateChange = (state) => {
      setConnectionState(state);
      setIsConnected(state === 'connected');
    };

    client.connect();

    return () => {
      client.disconnect();
      clientRef.current = null;
    };
  }, [path, autoReconnect]);

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
