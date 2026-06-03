import { useState, useMemo, lazy, Suspense, memo } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types/message";

/** Lazy-loaded syntax highlighter wrapper \u2014 760KB chunk only loaded when code block appears */
const Highlighter = lazy(() => import("./SyntaxHighlighterWrapper"));

interface MessageItemProps {
  message: Message;
}

/** Code block rendered with syntax highlighting (lazy loaded) */unction SimpleCode({ language, code }: { language?: string; code: string }) {
  return (
    <div className="relative group rounded-lg overflow-hidden my-2">
      <div className="flex items-center justify-between bg-[#1a1b26] px-4 py-1.5 text-xs text-[var(--text-tertiary)]">
        <span>{language || "code"}</span>
        <button
          onClick={() => navigator.clipboard.writeText(code)}
          className="text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
        >
          \ud83d\udccb
        </button>
      </div>
      <Suspense
        fallback={
          <pre className="bg-[#111118] text-[var(--text-secondary)] p-4 text-sm overflow-x-auto m-0">
            <code>{code}</code>
          </pre>
        }
      >
        <Highlighter
          language={language || "text"}
          code={code}
          showLineNumbers={code.split("\n").length > 3}
        />
      </Suspense>
    </div>
  );
}

/** Single message bubble \u2014 user plain text, AI rendered markdown + copy */
export const MessageItem = memo(function MessageItem({ message }: MessageItemProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const remarkPlugins = useMemo(() => [remarkGfm], []);
  const components = useMemo(
    () => ({
      code({
        className,
        children,
        ...props
      }: React.ClassAttributes<HTMLElement> &
        React.HTMLAttributes<HTMLElement> & {
          className?: string;
          children?: React.ReactNode;
        }) {
        const match = /language-(\w+)/.exec(className || "");
        const codeString = String(children).replace(/\n$/, "");
        if (match) {
          return <SimpleCode language={match[1]} code={codeString} />;
        }
        return (
          <code
            className={`px-1.5 py-0.5 rounded text-sm font-mono ${
              isUser ? "bg-white/20 text-white" : "bg-[var(--accent-soft)] text-[var(--accent)]"
            }`}
            {...props}
          >
            {children}
          </code>
        );
      },
      pre({ children }: { children?: React.ReactNode }) {
        return <div className="my-2">{children}</div>;
      },
    }),
    [isUser],
  );

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`relative max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-[var(--accent)] text-white"
            : "bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)]"
        }`}
      >
        {isUser ? (
          <div className="prose prose-sm max-w-none prose-invert break-words">
            <ReactMarkdown remarkPlugins={remarkPlugins}>
              {message.content}
            </ReactMarkdown>
          </div>
        ) : (
          <div className="prose prose-sm max-w-none break-words" translate="no">
            <ReactMarkdown
              remarkPlugins={remarkPlugins}
              components={components}
            >
              {message.content}
            </ReactMarkdown>

            {/* RAG Sources */}
            {message.sources && message.sources.length > 0 && (
              <div className="mt-3 pt-2 border-t border-[var(--border)]">
                <p className="text-xs text-[var(--text-tertiary)] mb-1.5">\ud83d\udcda \u53c2\u8003\u6765\u6e90</p>
                <div className="space-y-1">
                  {message.sources.map((src, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span className="text-[var(--accent)] truncate">{src.title}</span>
                      {src.score !== undefined && (
                        <span className="text-[var(--text-tertiary)] shrink-0">
                          {(src.score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Intent badge */}
            {message.intent && message.intent !== "chat" && (
              <div className="mt-2">
                <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">
                  {message.intent === "rag" ? "\ud83d\udcda \u77e5\u8bc6\u95ee\u7b54" : message.intent === "mixed" ? "\ud83d\udd17 \u6df7\u5408" : "\ud83e\udd16 \u5de5\u5177"}
                </span>
              </div>
            )}
          </div>
        )}

        {!isUser && message.content && (
          <button
            onClick={handleCopy}
            className="absolute -bottom-6 right-2 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          >
            {copied ? t("chat.copied") : t("chat.copy")}
          </button>
        )}
      </div>
    </div>
  );
});
