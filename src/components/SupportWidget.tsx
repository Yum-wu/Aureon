/**
 * Support Widget Component
 *
 * Floating customer service widget with:
 * - FAB button (bottom-right corner)
 * - Expandable chat panel
 * - Quick replies for common questions
 * - WebSocket streaming responses
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '../hooks/useWebSocket';

// Generate unique client ID for support widget
const SUPPORT_CLIENT_ID = 'support-widget-' + Math.random().toString(36).slice(2, 9);

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export function SupportWidget() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [wsError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    isConnected,
    send,
  } = useWebSocket(`/ws/chat/${SUPPORT_CLIENT_ID}`, {
    autoReconnect: true,
  });

  // Auto-scroll to bottom on new messages or streaming text
  useEffect(() => {
    if (isOpen && messagesEndRef.current?.scrollIntoView) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streamingText, isOpen]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen && isConnected) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen, isConnected]);

  // Handle send message
  const handleSend = useCallback((text?: string) => {
    const messageText = text || input.trim();
    if (!messageText || !isConnected) return;

    // Add user message to local state
    setMessages((prev) => [...prev, { role: 'user', content: messageText }]);

    // Send via WebSocket
    send(JSON.stringify({ type: 'chat', content: messageText, mode: 'support' }));

    // Simulate streaming state
    setIsStreaming(true);
    setStreamingText('');
    setInput('');
  }, [input, isConnected, send]);

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
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 100)}px`;
  }, []);

  // Get quick replies from i18n
  const quickReplies = t('support.quickReplies', { returnObjects: true }) as string[];
  const hasQuickReplies = Array.isArray(quickReplies) && quickReplies.length > 0;

  return (
    <>
      {/* FAB Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-300 hover:scale-110 focus:outline-none focus:ring-4 focus:ring-[var(--accent)]/30"
          style={{ background: 'var(--accent)' }}
          aria-label="Open support chat"
          data-testid="support-fab"
        >
          {/* Chat bubble icon */}
          <svg
            className="w-7 h-7 text-white"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z" />
            <circle cx="8" cy="10" r="1" />
            <circle cx="12" cy="10" r="1" />
            <circle cx="16" cy="10" r="1" />
          </svg>
          {/* Pulse animation */}
          <span className="absolute inset-0 rounded-full animate-ping opacity-20" style={{ background: 'var(--accent)' }} />
        </button>
      )}

      {/* Expanded Panel */}
      {isOpen && (
        <div
          className="fixed bottom-6 right-6 z-50 flex flex-col shadow-2xl border overflow-hidden"
          style={{
            width: 'min(400px, calc(100vw - 2rem))',
            height: 'min(600px, calc(100vh - 6rem))',
            background: 'var(--bg-secondary)',
            borderColor: 'var(--border)',
            borderRadius: '1rem',
          }}
          data-testid="support-panel"
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3 border-b shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                {t('support.title')}
              </h3>
            </div>
            <div className="flex items-center gap-3">
              {/* Connection status */}
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  isConnected
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
                data-testid="support-status"
              >
                {isConnected ? `\u25CF ${t('support.online')}` : `\u25CB ${t('support.offline')}`}
              </span>
              {/* Close button */}
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-md hover:bg-[var(--bg-tertiary)] transition-colors"
                style={{ color: 'var(--text-secondary)' }}
                aria-label={t('support.close')}
                data-testid="support-close"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4" data-testid="support-messages">
            {/* Welcome message + Quick Replies (when no messages) */}
            {messages.length === 0 && !isStreaming && (
              <div className="space-y-4">
                {/* Welcome */}
                <div className="flex justify-start">
                  <div
                    className="max-w-[85%] rounded-2xl rounded-bl-none px-4 py-3"
                    style={{ background: 'var(--bg-tertiary)' }}
                  >
                    <p className="text-sm whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>
                      {t('support.welcome')}
                    </p>
                  </div>
                </div>

                {/* Quick Replies */}
                {hasQuickReplies && (
                  <div className="flex flex-wrap gap-2 pt-2">
                    {quickReplies.map((reply: string, idx: number) => (
                      <button
                        key={idx}
                        onClick={() => handleSend(reply)}
                        disabled={!isConnected}
                        className="text-xs px-3 py-2 rounded-full border transition-colors disabled:opacity-50 disabled:cursor-not-allowed hover:border-[var(--accent)] hover:bg-[var(--accent-soft)]"
                        style={{
                          borderColor: 'var(--border)',
                          color: 'var(--text-secondary)',
                        }}
                        data-testid={`quick-reply-${idx}`}
                      >
                        {reply}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Message history */}
            {messages.map((msg: ChatMessage, idx: number) => (
              <div
                key={idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                data-testid={`support-message-${msg.role}-${idx}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    msg.role === 'user'
                      ? 'rounded-br-none'
                      : 'rounded-bl-none'
                  }`}
                  style={{
                    background: msg.role === 'user' ? 'var(--accent)' : 'var(--bg-tertiary)',
                    color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                  }}
                >
                  <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
                </div>
              </div>
            ))}

            {/* Streaming text */}
            {isStreaming && streamingText && (
              <div className="flex justify-start" data-testid="support-streaming">
                <div
                  className="max-w-[80%] rounded-2xl rounded-bl-none px-4 py-3"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <p className="text-sm whitespace-pre-wrap break-words" style={{ color: 'var(--text-primary)' }}>
                    {streamingText}
                  </p>
                  <div className="mt-2 flex items-center gap-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    <span className="animate-pulse">{'\u25CF'}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Loading indicator when streaming but no text yet */}
            {isStreaming && !streamingText && (
              <div className="flex justify-start" data-testid="support-loading">
                <div
                  className="rounded-2xl rounded-bl-none px-4 py-3"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <div className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '0ms' }} />
                    <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '150ms' }} />
                    <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Error Display */}
          {wsError && (
            <div
              className="px-4 py-2 text-xs border-t"
              style={{
                background: 'rgba(239, 68, 68, 0.1)',
                borderColor: 'var(--border)',
                color: '#ef4444',
              }}
              data-testid="support-error"
            >
              {wsError}
            </div>
          )}

          {/* Input Area */}
          <div className="border-t p-3 shrink-0" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyPress}
                placeholder={isConnected ? t('support.placeholder') : t('support.connecting')}
                disabled={!isConnected}
                className="flex-1 resize-none rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
                style={{
                  background: 'var(--bg-primary)',
                  borderColor: 'var(--border)',
                  color: 'var(--text-primary)',
                  minHeight: '40px',
                  maxHeight: '100px',
                }}
                data-testid="support-input"
                rows={1}
              />
              <button
                onClick={() => handleSend()}
                disabled={!isConnected || !input.trim()}
                className="px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  background: input.trim() && isConnected ? 'var(--accent)' : 'var(--bg-tertiary)',
                  color: input.trim() && isConnected ? 'white' : 'var(--text-tertiary)',
                }}
                data-testid="support-send"
              >
                {t('chat.send')}
              </button>
            </div>
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
              {isConnected ? t('support.connected') : t('support.connecting')}
            </p>
          </div>
        </div>
      )}
    </>
  );
}

export default SupportWidget;
