// src/hooks/useWebSocket.ts

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  AureonWebSocket,
  getWebSocket,
} from '../services/websocket';
import type {
  ChatMessage,
  SourceItem,
} from '../services/websocket';

interface UseWebSocketOptions {
  clientId?: string;
  autoConnect?: boolean;
  maxReconnectAttempts?: number;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingText: string;
  sources: SourceItem[];
  error: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sendMessage: (query: string, metadata?: Record<string, any>) => void;
  disconnect: () => void;
}

/** Exponential backoff delay in ms: 1s, 2s, 4s, 8s, max 30s */
function getReconnectDelay(attempt: number): number {
  return Math.min(1000 * Math.pow(2, attempt), 30000);
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { clientId = 'default', autoConnect = true, maxReconnectAttempts = 5 } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<AureonWebSocket | null>(null);
  const streamingTextRef = useRef('');
  const handlersRegisteredRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalDisconnectRef = useRef(false);
  const maxReconnectAttemptsRef = useRef(maxReconnectAttempts);

  // Keep ref in sync with prop changes
  useEffect(() => {
    maxReconnectAttemptsRef.current = maxReconnectAttempts;
  }, [maxReconnectAttempts]);

  // Clear any pending reconnect timer
  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  // Reconnect handler kept in a ref to avoid circular dependency
  // (useCallback referencing itself inside its own body).
  const reconnectHandlerRef = useRef<() => void>(() => {});

  // Attempt reconnection with exponential backoff
  const attemptReconnect = useCallback(() => {
    if (intentionalDisconnectRef.current) return;
    if (reconnectAttemptRef.current >= maxReconnectAttemptsRef.current) {
      setError('Connection lost. Please refresh the page to reconnect.');
      return;
    }

    const delay = getReconnectDelay(reconnectAttemptRef.current);
    reconnectAttemptRef.current += 1;

    reconnectTimerRef.current = setTimeout(() => {
      if (!wsRef.current || intentionalDisconnectRef.current) return;
      wsRef.current.connect().catch((err) => {
        console.error('Reconnect attempt failed:', err);
        reconnectHandlerRef.current();
      });
    }, delay);
  }, []);

  // Initialize WebSocket
  useEffect(() => {
    if (!autoConnect) return;

    const ws = getWebSocket(clientId);
    wsRef.current = ws;
    reconnectHandlerRef.current = attemptReconnect;

    // Only register handlers once to prevent duplicates
    if (handlersRegisteredRef.current) {
      // Still connect if not already connected
      if (!ws.isConnected()) {
        ws.connect().catch((err) => {
          console.error('Failed to connect:', err);
          setError('Failed to connect to server');
          attemptReconnect();
        });
      }
      return;
    }
    handlersRegisteredRef.current = true;

    // Register message handlers
    ws.onMessage('connected', () => {
      reconnectAttemptRef.current = 0; // Reset on successful connect
    });

    ws.onMessage('sources', (msg) => {
      setSources((msg.sources as SourceItem[]) || []);
    });

    ws.onMessage('text', (msg) => {
      setIsStreaming(true);
      streamingTextRef.current += (msg.content as string) || '';
      setStreamingText(streamingTextRef.current);
    });

    ws.onMessage('response_complete', (msg) => {
      setIsStreaming(false);
      setStreamingText('');

      // Add assistant message to history
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: (msg.full_response as string) || '',
          sources: [],
          timestamp: new Date(),
        },
      ]);
    });

    ws.onMessage('error', (msg) => {
      setError((msg.message as string) || 'Unknown error');
      setIsStreaming(false);
    });

    ws.onMessage('heartbeat_ack', () => {
      // Heartbeat acknowledged
    });

    // Register connection handler — auto-reconnect on disconnect
    ws.onConnection((connected) => {
      setIsConnected(connected);
      if (connected) {
        setError(null);
        reconnectAttemptRef.current = 0;
        clearReconnectTimer();
      } else {
        if (!intentionalDisconnectRef.current) {
          setError('Disconnected from server');
          attemptReconnect();
        }
      }
    });

    // Connect
    intentionalDisconnectRef.current = false;
    ws.connect().catch((err) => {
      console.error('Failed to connect:', err);
      setError('Failed to connect to server');
      attemptReconnect();
    });

    // Cleanup
    return () => {
      intentionalDisconnectRef.current = true;
      clearReconnectTimer();
      ws.disconnect();
      handlersRegisteredRef.current = false;
    };
  }, [clientId, autoConnect, attemptReconnect, clearReconnectTimer]);

  // Send user message
  const sendMessage = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (query: string, metadata?: Record<string, any>) => {
      if (!wsRef.current || !isConnected) {
        setError('Not connected');
        return;
      }

      // Add user message to history
      setMessages((prev) => [
        ...prev,
        {
          role: 'user',
          content: query,
          timestamp: new Date(),
        },
      ]);

      // Reset streaming state
      streamingTextRef.current = '';
      setStreamingText('');
      setIsStreaming(true);
      setError(null);

      // Send message with optional metadata
      wsRef.current.sendUserMessage(query, metadata);
    },
    [isConnected]
  );

  // Disconnect
  const disconnect = useCallback(() => {
    intentionalDisconnectRef.current = true;
    clearReconnectTimer();
    if (wsRef.current) {
      wsRef.current.disconnect();
    }
  }, [clearReconnectTimer]);

  return {
    isConnected,
    messages,
    isStreaming,
    streamingText,
    sources,
    error,
    sendMessage,
    disconnect,
  };
}
