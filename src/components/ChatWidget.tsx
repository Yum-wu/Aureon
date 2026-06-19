/**
 * Chat Widget Component.
 *
 * Provides a complete chat interface with:
 * - Message history
 * - Streaming text display
 * - Source citations
 * - Connection status
 */

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../stores/useChatStore';
import { useDocumentsStore } from '../stores/useDocumentsStore';
import { VoiceButton } from './VoiceButton';
import { BookOpen, AlertTriangle } from 'lucide-react';

interface ChatWidgetProps {
  clientId?: string;
  className?: string;
}

export function ChatWidget({ className = '' }: ChatWidgetProps) {
  const { t } = useTranslation();
  const {
    messages,
    isLoading,
    error,
    sendMessage,
  } = useChatStore();
  const { documents } = useDocumentsStore();

  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 构建快捷提问卡片：2 条静态 + 2 条动态（基于最近文档）
  const suggestions = useMemo(() => {
    const staticSuggestions: string[] = [
      t('chat.suggestions.summarize_latest'),
      t('chat.suggestions.key_risks'),
    ];

    if (documents.length >= 2) {
      // 取最近 2 个文档生成动态提示
      const recent = documents.slice(0, 2);
      return [
        ...staticSuggestions,
        t('chat.suggestions.summarize_doc', { title: recent[0].title }),
        t('chat.suggestions.about_doc', { title: recent[1].title }),
      ];
    }
    if (documents.length === 1) {
      return [
        ...staticSuggestions,
        t('chat.suggestions.summarize_doc', { title: documents[0].title }),
        t('chat.suggestions.about_doc', { title: documents[0].title }),
      ];
    }
    // 无文档时 fallback：额外 2 条通用提示
    return [
      ...staticSuggestions,
      t('chat.emptyTitle'),
      t('chat.emptyHint'),
    ];
  }, [documents, t]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle send
  const handleSend = useCallback(() => {
    if (!input.trim() || isLoading) return;

    sendMessage(input.trim());
    setInput('');
  }, [input, isLoading, sendMessage]);

  // Handle key down
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
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
      className={`chat-widget bg-[var(--bg-secondary)] rounded-lg shadow-lg border border-[var(--border)] flex flex-col h-full ${className}`}
      data-testid="chat-widget"
    >
      {/* Header */}
      <div className="chat-header bg-[var(--bg-secondary)] border-b border-[var(--border)] text-[var(--text-primary)] px-4 py-3 rounded-t-lg flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-lg">{t('chat.title')}</h3>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`status-indicator text-sm px-2 py-1 rounded-full ${
              !isLoading
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-yellow-500/20 text-yellow-400'
            }`}
            data-testid="connection-status"
          >
            {isLoading ? `● ${t('chat.streaming')}` : `● ${t('chat.ready')}`}
          </span>
        </div>
      </div>

      {/* Messages Area */}
      <div
        className="chat-messages flex-1 overflow-y-auto p-4 space-y-4 bg-[var(--bg-primary)]"
        data-testid="chat-messages"
        role="log"
        aria-live="polite"
      >
        {/* Welcome message if no messages */}
        {messages.length === 0 && !isLoading && (
          <div className="text-center text-[var(--text-tertiary)] py-8">
            <p className="text-lg font-medium mb-2">{t('chat.welcome')}</p>
            <p className="text-sm">{t('chat.welcome_subtitle')}</p>
            <div className="grid grid-cols-2 gap-3 max-w-md mx-auto mt-4">
              {suggestions.map((text, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(text)}
                  className="text-left p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors text-sm text-[var(--text-secondary)]"
                >
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message history */}
        {messages.map((msg, idx) => (
          <div
            key={msg.id || idx}
            className={`message ${msg.role} flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            data-testid={`message-${msg.role}-${idx}`}
          >
            <div
              className={`message-content max-w-[75%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-[var(--accent)] text-white rounded-br-none'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] rounded-bl-none'
              }`}
            >
              <div className="whitespace-pre-wrap break-words">{msg.content}</div>

              {/* Source citations for assistant messages */}
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <div className="mt-3 pt-2 border-t border-[var(--border)]">
                  <p className="text-xs font-medium text-[var(--text-tertiary)] mb-1 inline-flex items-center gap-1"><BookOpen size={14} /> {t('chat.sources')}:</p>
                  <div className="space-y-1">
                    {msg.sources.map((source, sourceIdx) => (
                      <div key={sourceIdx} className="flex items-center gap-2 text-xs">
                        <span className="text-[var(--accent)] font-medium">{source.title}</span>
                        {source.score !== undefined && (
                          <span className="text-[var(--text-tertiary)]">
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

        {/* Loading indicator */}
        {isLoading && (
          <div className="message assistant flex justify-start" data-testid="streaming-message">
            <div className="message-content max-w-[75%] rounded-2xl px-4 py-3 bg-[var(--bg-tertiary)] text-[var(--text-primary)] rounded-bl-none">
              <div className="mt-2 flex items-center gap-1 text-xs text-[var(--text-tertiary)]">
                <span className="animate-pulse">●</span> {t('chat.streaming')}
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error Display */}
      {error && (
        <div
          className="chat-error bg-red-500/10 text-red-400 border-t border-red-500/20 px-4 py-3 text-sm"
          data-testid="chat-error"
        >
          <span className="inline-flex items-center gap-1"><AlertTriangle size={14} /> {error}</span>
        </div>
      )}

      {/* Input Area */}
      <div className="chat-input bg-[var(--bg-secondary)] border-t border-[var(--border)] p-4 rounded-b-lg">
        <div className="flex items-end gap-3">
          {/* Voice Button */}
          <VoiceButton
            onTranscript={(text) => {
              setInput((prev) => (prev ? prev + ' ' + text : text));
              inputRef.current?.focus();
            }}
            disabled={isLoading}
          />
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={t('chat.placeholder')}
            disabled={isLoading}
            className="flex-1 resize-none rounded-lg border border-[var(--border)] px-4 py-3 text-[var(--text-primary)] bg-[var(--bg-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent disabled:bg-[var(--bg-tertiary)] disabled:cursor-not-allowed transition-all duration-200 placeholder:text-[var(--text-tertiary)]"
            data-testid="chat-input"
            rows={1}
            style={{ minHeight: '48px', maxHeight: '150px' }}
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:bg-[var(--bg-tertiary)] disabled:cursor-not-allowed text-white font-semibold px-6 py-3 rounded-lg transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2"
            data-testid="send-button"
            aria-label={t('chat.send')}
          >
            {t('chat.send')}
          </button>
        </div>
        <p className="text-xs text-[var(--text-tertiary)] mt-2">
          {isLoading ? t('chat.processing') : t('chat.ready')}
        </p>
      </div>
    </div>
  );
}

export default ChatWidget;
