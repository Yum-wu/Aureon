/**
 * Chat Widget Component.
 *
 * Provides a complete chat interface with:
 * - Message history
 * - Streaming text display
 * - Source citations
 * - Connection status
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { VoiceButton } from './VoiceButton';
import type { SourceItem } from '../services/websocket';

interface ChatWidgetProps {
  clientId?: string;
  className?: string;
}

export function ChatWidget({ clientId = 'default', className = '' }: ChatWidgetProps) {
  const {
    isConnected,
    messages,
    isStreaming,
    streamingText,
    sources,
    error,
    sendMessage,
  } = useWebSocket({ clientId });

  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages or streaming text
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  // Focus input on connection
  useEffect(() => {
    if (isConnected) {
      inputRef.current?.focus();
    }
  }, [isConnected]);

  // Handle send
  const handleSend = useCallback(() => {
    if (!input.trim() || !isConnected) return;

    sendMessage(input.trim());
    setInput('');
  }, [input, isConnected, sendMessage]);

  // Handle key press
  const handleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // Handle textarea resize
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);

    // Auto-resize textarea
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`;
  }, []);

  return (
    <div
      className={`chat-widget bg-white rounded-lg shadow-lg border border-gray-200 flex flex-col h-full ${className}`}
      data-testid="chat-widget"
    >
      {/* Header */}
      <div className="chat-header bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4 py-3 rounded-t-lg flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-lg">Aureon Chat</h3>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`status-indicator text-sm px-2 py-1 rounded-full ${
              isConnected
                ? 'bg-green-500/20 text-green-100'
                : 'bg-red-500/20 text-red-100'
            }`}
            data-testid="connection-status"
          >
            {isConnected ? '● Connected' : '○ Disconnected'}
          </span>
        </div>
      </div>

      {/* Messages Area */}
      <div
        className="chat-messages flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50"
        data-testid="chat-messages"
      >
        {/* Welcome message if no messages */}
        {messages.length === 0 && !isStreaming && (
          <div className="text-center text-gray-500 py-8">
            <p className="text-lg font-medium mb-2">Welcome to Aureon</p>
            <p className="text-sm">Start a conversation by typing a message below.</p>
          </div>
        )}

        {/* Message history */}
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`message ${msg.role} flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            data-testid={`message-${msg.role}-${idx}`}
          >
            <div
              className={`message-content max-w-[75%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-none'
                  : 'bg-white text-gray-800 border border-gray-200 rounded-bl-none shadow-sm'
              }`}
            >
              <div className="whitespace-pre-wrap break-words">{msg.content}</div>

              {/* Source citations for assistant messages */}
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <div className="mt-3 pt-2 border-t border-gray-200">
                  <p className="text-xs font-medium text-gray-500 mb-1">📚 Sources:</p>
                  <div className="space-y-1">
                    {msg.sources.map((source, sourceIdx) => (
                      <div key={sourceIdx} className="flex items-center gap-2 text-xs">
                        <span className="text-blue-600 font-medium">{source.title}</span>
                        {source.score !== undefined && (
                          <span className="text-gray-400">
                            ({(source.score * 100).toFixed(0)}%)
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Streaming text display */}
        {isStreaming && streamingText && (
          <div className="message assistant flex justify-start" data-testid="streaming-message">
            <div className="message-content max-w-[75%] rounded-2xl px-4 py-3 bg-white text-gray-800 border border-gray-200 rounded-bl-none shadow-sm">
              <div className="whitespace-pre-wrap break-words">{streamingText}</div>
              <div className="mt-2 flex items-center gap-1 text-xs text-gray-400">
                <span className="animate-pulse">●</span> Streaming...
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Sources Panel */}
      {sources.length > 0 && (
        <div
          className="sources-panel border-t border-gray-200 bg-gray-50 px-4 py-3"
          data-testid="sources-panel"
        >
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Referenced Sources</h4>
          <ul className="space-y-1">
            {sources.map((source, idx) => (
              <li
                key={idx}
                className="flex items-center justify-between text-xs text-gray-600"
              >
                <span className="truncate">{source.title}</span>
                {source.score !== undefined && (
                  <span className="text-gray-400 ml-2 shrink-0">
                    {source.score.toFixed(2)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div
          className="chat-error bg-red-50 text-red-700 border-t border-red-200 px-4 py-3 text-sm"
          data-testid="chat-error"
        >
          ⚠️ {error}
        </div>
      )}

      {/* Input Area */}
      <div className="chat-input bg-white border-t border-gray-200 p-4 rounded-b-lg">
        <div className="flex items-end gap-3">
          {/* Voice Button */}
          <VoiceButton
            onTranscript={(text) => {
              setInput((prev) => (prev ? prev + ' ' + text : text));
              inputRef.current?.focus();
            }}
            disabled={!isConnected}
          />
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
            disabled={!isConnected}
            className="flex-1 resize-none rounded-lg border border-gray-300 px-4 py-3 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-all duration-200"
            data-testid="chat-input"
            rows={1}
            style={{ minHeight: '48px', maxHeight: '150px' }}
          />
          <button
            onClick={handleSend}
            disabled={!isConnected || !input.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold px-6 py-3 rounded-lg transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            data-testid="send-button"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          {isConnected ? 'Connected and ready to chat' : 'Connecting...'}
        </p>
      </div>
    </div>
  );
}

export default ChatWidget;
