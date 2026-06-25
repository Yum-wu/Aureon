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
import { SourceCard } from './shared/SourceCard';
import type { Source } from './shared/SourceCard';
import { MessageActions } from './shared/MessageActions';
import { useSupportMessages } from '../hooks/useSupportMessages';
import { useSupportGreeting } from '../hooks/useSupportGreeting';
import { getRouteQuickReplies } from '../support/quickReplyRoutes';

// Generate stable client ID for support widget (persisted in sessionStorage)
const getSupportClientId = () => {
  const key = 'aureon_support_client_id';
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = 'support-' + crypto.randomUUID().slice(0, 8);
    sessionStorage.setItem(key, id);
  }
  return id;
};
const SUPPORT_CLIENT_ID = getSupportClientId();

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
}

export function SupportWidget() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [wsError, setWsError] = useState<string | null>(null);
  const [offlineMode, setOfflineMode] = useState(false);
  const [offlineStatus, setOfflineStatus] = useState<'idle' | 'sending' | 'success' | 'error'>('idle');
  const offlineNameRef = useRef<HTMLInputElement>(null);
  const [streamingSources, setStreamingSources] = useState<Source[]>([]);
  useSupportMessages(messages, setMessages, isStreaming);
  const { showGreeting, dismissGreeting } = useSupportGreeting(isOpen);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Deferred mount: delay WebSocket connection by 3s to reduce initial load pressure
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 3000);
    return () => clearTimeout(timer);
  }, []);

  const wsPath = mounted ? `/ws/chat/${SUPPORT_CLIENT_ID}` : '';

  const {
    isConnected,
    send,
  } = useWebSocket(wsPath, {
    autoReconnect: true,
    onOpen: () => {
      // 连接成功时清除之前的错误信息
      setWsError(null);
    },
    onMessage: (data) => {
      if (data && typeof data === 'object' && 'type' in data) {
        const msg = data as { type: string; content?: string; text?: string; message?: string; full_response?: string };
        if (msg.type === 'text' || msg.type === 'session') {
          // 后端发送 type=text, content 字段
          const text = msg.content || msg.text || '';
          if (text) {
            setStreamingText((prev) => prev + text);
          }
        } else if (msg.type === 'response_complete' || msg.type === 'done') {
          // 流式结束 — 后端用 response_complete，兼容 done
          setIsStreaming(false);
          setStreamingText((prev) => {
            if (prev) {
              setMessages((msgs) => [...msgs, { role: 'assistant', content: prev, sources: streamingSources }]);
            }
            return '';
          });
          setStreamingSources([]);
        } else if (msg.type === 'error') {
          // 后端用 message 字段 — 同时结束流式状态避免永久卡住
          setWsError(msg.message || msg.content || msg.text || '连接出错');
          setIsStreaming(false);
          setStreamingText((prev) => {
            // 如果已有部分流式内容，保留为助手消息
            if (prev) {
              setMessages((msgs) => [...msgs, { role: 'assistant', content: prev }]);
            }
            return '';
          });
        } else if (msg.type === 'connected') {
          // 连接确认，清除错误
          setWsError(null);
        } else if (msg.type === 'sources' && Array.isArray(msg.sources)) {
          setStreamingSources(msg.sources);
        } else if (msg.type === 'citation') {
          setStreamingSources(prev => [...prev, msg.source]);
        }
      }
    },
    onError: () => {
      setWsError('连接失败，请稍后重试');
    },
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
    if (!messageText) return;
    if (!isConnected) {
      setOfflineMode(true);
      return;
    }

    // Add user message to local state
    setMessages((prev) => [...prev, { role: 'user', content: messageText }]);

    // Send via WebSocket — 后端期望 type=user_message, query 字段, metadata.mode=support
    send(JSON.stringify({
      type: 'user_message',
      query: messageText,
      metadata: { mode: 'support' },
    }));

    // Simulate streaming state
    setIsStreaming(true);
    setStreamingText('');
    setInput('');
  }, [input, isConnected, send]);

  const handleRegenerate = useCallback((assistantIdx: number) => {
    let lastUserIdx = -1;
    for (let i = assistantIdx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx === -1) return;
    const userMessage = messages[lastUserIdx].content;
    setMessages(messages.slice(0, lastUserIdx));
    handleSend(userMessage);
  }, [messages, handleSend]);

  const handleOfflineSubmit = useCallback(async () => {
    const nameEl = document.querySelector<HTMLInputElement>('[data-testid="offline-name"]');
    const emailEl = document.querySelector<HTMLInputElement>('[data-testid="offline-email"]');
    const msgEl = document.querySelector<HTMLTextAreaElement>('[data-testid="offline-message"]');
    if (!nameEl || !emailEl || !msgEl) return;
    const name = nameEl.value.trim();
    const email = emailEl.value.trim();
    const message = msgEl.value.trim();
    if (!name || !email || !message) return;
    setOfflineStatus('sending');
    try {
      const res = await fetch('/api/v1/support/offline-message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, message, page_url: window.location.href }),
      });
      if (res.ok) {
        setOfflineStatus('success');
        setTimeout(() => setOfflineStatus('idle'), 5000);
      } else {
        setOfflineStatus('error');
      }
    } catch {
      setOfflineStatus('error');
    }
  }, []);

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

  // Get quick replies from i18n + page route
  const staticReplies = t('support.quickReplies', { returnObjects: true }) as string[];
  const routeReplies = getRouteQuickReplies(t);
  const allReplies = [...new Set([...routeReplies, ...staticReplies])];
  const hasQuickReplies = Array.isArray(allReplies) && allReplies.length > 0;

  return (
    <>
      {/* FAB Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-300 hover:scale-110 focus:outline-none focus:ring-4 focus:ring-[var(--accent)]/30"
          style={{ background: 'var(--accent)' }}
          aria-label="Open support chat"
          aria-expanded={isOpen}
          data-testid="support-fab"
          data-onboarding="support-fab"
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
          <span className="absolute inset-0 rounded-full opacity-0" style={{ background: 'var(--accent)' }} />
        </button>
        {showGreeting && !isOpen && (
          <div className="fixed bottom-24 right-6 z-50 animate-fade-in" onClick={dismissGreeting}>
            <div className="relative bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl px-4 py-3 shadow-lg max-w-[200px]">
              <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{t('support.greeting')}</p>
              <div className="absolute bottom-[-6px] right-6 w-3 h-3 bg-[var(--bg-secondary)] border-r border-b border-[var(--border)] rotate-45" />
            </div>
          </div>
        )}
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
          role="dialog"
          aria-modal="true"
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
                    {allReplies.map((reply: string, idx: number) => (
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
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} group`}
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
                  <MessageActions role={msg.role} content={msg.content} onRegenerate={msg.role === 'assistant' ? () => handleRegenerate(idx) : undefined} t={t} />
                  {msg.sources && msg.sources.length > 0 && (
                    <SourceCard sources={msg.sources} t={t} />
                  )}
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
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>AI {t('support.typing')}...</span>
                    <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '300ms' }} />
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
            {offlineMode || !isConnected ? (
              <div>
                <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-primary)' }}>{t('support.offline_title')}</p>
                {offlineStatus === 'idle' ? (
                  <>
                    <input
                      ref={offlineNameRef}
                      className="w-full rounded-lg border px-3 py-2 text-sm mb-2"
                      style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                      placeholder={t('support.offline_name')}
                      data-testid="offline-name"
                    />
                    <input
                      className="w-full rounded-lg border px-3 py-2 text-sm mb-2"
                      style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                      placeholder={t('support.offline_email')}
                      type="email"
                      data-testid="offline-email"
                    />
                    <textarea
                      className="w-full rounded-lg border px-3 py-2 text-sm mb-2 resize-none"
                      style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)', minHeight: '60px' }}
                      placeholder={t('support.offline_message')}
                      data-testid="offline-message"
                    />
                    <button
                      onClick={handleOfflineSubmit}
                      className="px-4 py-2 rounded-lg text-sm font-medium text-white"
                      style={{ background: 'var(--accent)' }}
                      data-testid="offline-submit"
                    >
                      {t('support.offline_submit')}
                    </button>
                  </>
                ) : offlineStatus === 'success' ? (
                  <p className="text-sm text-green-400">{t('support.offline_success')}</p>
                ) : (
                  <div>
                    <p className="text-sm text-red-400 mb-2">{t('support.offline_error')}</p>
                    <button onClick={() => setOfflineStatus('idle')} className="text-xs text-[var(--accent)] underline">{t('cost.retry')}</button>
                  </div>
                )}
              </div>
            ) : (
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
            )}
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
              {isConnected ? t('support.connected') : t('support.connecting')}
            </p>
          </div>
        </div>
      )}
      <style>{`
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-fade-in {
  animation: fadeIn 0.4s ease-out;
}
`}</style>
    </>
  );
}

export default SupportWidget;
