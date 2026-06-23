import { useState, useMemo, memo } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import type { Message } from "../types/message";
import { BookOpen, Link, Bot } from "lucide-react";
import { markdownComponents } from "./markdown/markdownConfig";

interface MessageItemProps {
  message: Message;
  onRegenerate?: () => void;
}

/** Hover toolbar button */
function ToolbarBtn({ onClick, title, active, children }: {
  onClick: () => void;
  title: string;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`p-1 rounded-md transition-colors ${
        active
          ? "text-[var(--accent)] bg-[var(--accent-soft)]"
          : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
      }`}
    >
      {children}
    </button>
  );
}

export const MessageItem = memo(function MessageItem({ message, onRegenerate }: MessageItemProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
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
  const rehypePlugins = useMemo(() => [
    [rehypeSanitize, {
      tagNames: ['p','br','strong','em','code','pre','ul','ol','li','h1','h2','h3','a','blockquote','hr','table','thead','tbody','tr','th','td'],
      attributes: { code: ['className'], pre: ['className'], a: ['href','target','rel'] }
    }]
  ], []);

  return (
    <div className={`group/msg flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className="flex flex-col gap-1">
        <div
          className={`relative max-w-[75%] rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-[var(--accent)] text-white"
              : "bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)]"
          }`}
        >
          {isUser ? (
            <div className="prose prose-sm max-w-none prose-invert break-words">
              <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}>
                {message.content}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="prose prose-sm max-w-none break-words" translate="no">
              <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={markdownComponents}>
                {message.content}
              </ReactMarkdown>

              {message.sources && message.sources.length > 0 && (
                <div className="mt-3 pt-2 border-t border-[var(--border)]">
                  <p className="text-xs text-[var(--text-tertiary)] mb-1.5 inline-flex items-center gap-1"><BookOpen size={12} /> 参考来源</p>
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

              {message.intent && message.intent !== "chat" && (
                <div className="mt-2">
                  <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">
                    {message.intent === "rag" ? <span className="inline-flex items-center gap-1"><BookOpen size={12} /> 知识问答</span> : message.intent === "mixed" ? <span className="inline-flex items-center gap-1"><Link size={12} /> 混合</span> : <span className="inline-flex items-center gap-1"><Bot size={12} /> 工具</span>}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Hover toolbar — only for AI messages */}
        {!isUser && message.content && (
          <div className="flex items-center gap-0.5 opacity-0 group-hover/msg:opacity-100 transition-opacity duration-150 ml-1">
            <ToolbarBtn onClick={handleCopy} title={t("chat.copy")} active={copied}>
              {copied ? (
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75" />
                </svg>
              )}
            </ToolbarBtn>
            {onRegenerate && (
              <ToolbarBtn onClick={onRegenerate} title={t("chat.regenerate")}>
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
                </svg>
              </ToolbarBtn>
            )}
            <ToolbarBtn onClick={() => setFeedback("up")} title="Good" active={feedback === "up"}>
              <svg className="w-3.5 h-3.5" fill={feedback === "up" ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75A2.25 2.25 0 0116.5 4.5c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H14.23c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904M14.25 9h2.25M5.904 18.75c.083.228.22.444.414.624.194.18.43.3.68.336.25.036.5-.05.66-.22a.75.75 0 00.12-.553 2.25 2.25 0 00-.414-.624.75.75 0 00-.66-.22.75.75 0 00-.553.12c-.172.16-.256.41-.22.66.036.25-.05.5-.22.66a2.25 2.25 0 00-.624.414c-.18.194-.3.43-.336.68a.75.75 0 00.22.553c.16.172.41.256.66.22.25-.036.5.05.66.22.172.16.256.41.22.66" />
              </svg>
            </ToolbarBtn>
            <ToolbarBtn onClick={() => setFeedback("down")} title="Bad" active={feedback === "down"}>
              <svg className="w-3.5 h-3.5 rotate-180" fill={feedback === "down" ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75A2.25 2.25 0 0116.5 4.5c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H14.23c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904M14.25 9h2.25M5.904 18.75c.083.228.22.444.414.624.194.18.43.3.68.336.25.036.5-.05.66-.22a.75.75 0 00.12-.553 2.25 2.25 0 00-.414-.624.75.75 0 00-.66-.22.75.75 0 00-.553.12c-.172.16-.256.41-.22.66.036.25-.05.5-.22.66a2.25 2.25 0 00-.624.414c-.18.194-.3.43-.336.68a.75.75 0 00.22.553c.16.172.41.256.66.22.25-.036.5.05.66.22.172.16.256.41.22.66" />
              </svg>
            </ToolbarBtn>
          </div>
        )}
      </div>
    </div>
  );
});