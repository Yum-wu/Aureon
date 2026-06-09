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

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { clientId = 'default', autoConnect = true } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<AureonWebSocket | null>(null);
  const streamingTextRef = useRef('');
  const handlersRegisteredRef = useRef(false);

  // Initialize WebSocket
  useEffect(() => {
    if (!autoConnect) return;

    const ws = getWebSocket(clientId);
    wsRef.current = ws;

    // Only register handlers once to prevent duplicates
    if (handlersRegisteredRef.current) {
      // Still connect if not already connected
      if (!ws.isConnected()) {
        ws.connect().catch((err) => {
          console.error('Failed to connect:', err);
          setError('Failed to connect to server');
        });
      }
      return;
    }
    handlersRegisteredRef.current = true;

    // Register message handlers
    ws.onMessage('connected', (msg) => {
      console.log('Connected to chat:', msg.conversation_id);
    });

    ws.onMessage('sources', (msg) => {
      setSources(msg.sources || []);
    });

    ws.onMessage('text', (msg) => {
      setIsStreaming(true);
      streamingTextRef.current += msg.content || '';
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
          content: msg.full_response || '',
          sources: [],
          timestamp: new Date(),
        },
      ]);
    });

    ws.onMessage('error', (msg) => {
      setError(msg.message || 'Unknown error');
      setIsStreaming(false);
    });

    ws.onMessage('heartbeat_ack', () => {
      // Heartbeat acknowledged
    });

    // Register connection handler
    ws.onConnection((connected) => {
      setIsConnected(connected);
      if (connected) {
        // Clear any previous disconnect error on reconnect
        setError(null);
      } else {
        setError('Disconnected from server');
      }
    });

    // Connect
    ws.connect().catch((err) => {
      console.error('Failed to connect:', err);
      setError('Failed to connect to server');
    });

    // Cleanup
    return () => {
      ws.disconnect();
      handlersRegisteredRef.current = false;
    };
  }, [clientId, autoConnect]);

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
    if (wsRef.current) {
      wsRef.current.disconnect();
    }
  }, []);

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
