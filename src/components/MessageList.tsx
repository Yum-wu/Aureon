import { useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { Message } from "../types/message";
import { MessageItem } from "./MessageItem";

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
}

/** Message list with smart auto-scroll (won't force scroll when user browsed up) */
export function MessageList({ messages, isLoading }: MessageListProps) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 300;
  }, []);

  useEffect(() => {
    if (isAtBottom()) {
      bottomRef.current?.scrollIntoView({ behavior: isLoading ? "instant" : "smooth" });
    }
  }, [messages, isLoading, isAtBottom]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--text-tertiary)]">
        <div className="text-center">
          <div className="text-5xl mb-4">{t("chat.emptyTitle")}</div>
          <p className="text-lg text-[var(--text-secondary)]">{t("chat.emptySubtitle")}</p>
          <p className="text-sm mt-2">{t("chat.emptyHint")}</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-6">
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
      {isLoading &&
        messages[messages.length - 1]?.role === "assistant" &&
        !messages[messages.length - 1]?.content && (
          <div className="flex justify-start mb-4">
            <div className="bg-[var(--bg-secondary)] rounded-2xl px-4 py-3 border border-[var(--border)]">
              <div className="flex space-x-1">
                <span
                  className="w-2 h-2 bg-[var(--text-tertiary)] rounded-full animate-bounce"
                  style={{ animationDelay: "0ms" }}
                />
                <span
                  className="w-2 h-2 bg-[var(--text-tertiary)] rounded-full animate-bounce"
                  style={{ animationDelay: "150ms" }}
                />
                <span
                  className="w-2 h-2 bg-[var(--text-tertiary)] rounded-full animate-bounce"
                  style={{ animationDelay: "300ms" }}
                />
              </div>
            </div>
          </div>
        )}
      <div ref={bottomRef} />
    </div>
  );
}
