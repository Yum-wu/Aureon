import { useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { KeyboardEvent } from "react";

interface InputAreaProps {
  onSend: (content: string) => void;
  isLoading: boolean;
  onStop: () => void;
}

/** Container-style input — attachment button | textarea | send/stop button */
export function InputArea({ onSend, isLoading, onStop }: InputAreaProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, isLoading, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleInput = useCallback((e: React.FormEvent<HTMLTextAreaElement>) => {
    const target = e.currentTarget;
    target.style.height = "auto";
    target.style.height = Math.min(target.scrollHeight, 128) + "px";
  }, []);

  return (
    <div className="border-t border-[var(--border)] px-4 py-3 glass-strong">
      <div className="max-w-3xl mx-auto">
        <div className="relative flex items-end rounded-xl border-2 border-[var(--border)] bg-[var(--bg-secondary)] transition-colors focus-within:border-[var(--accent)]">
          {/* Attachment button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="absolute bottom-3 left-3 p-1 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            title={t("chat.attach") || "Attach file"}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={() => {/* TODO: file upload */}}
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder={t("chat.inputPlaceholder")}
            rows={1}
            className="flex-1 resize-none bg-transparent px-12 py-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none max-h-32"
            style={{ minHeight: "48px" }}
          />

          {/* Send / Stop button */}
          {isLoading ? (
            <button
              onClick={onStop}
              className="absolute bottom-3 right-3 p-1.5 rounded-lg bg-[var(--error)] text-white hover:opacity-90 transition-opacity"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="absolute bottom-3 right-3 p-1.5 rounded-lg bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
              </svg>
            </button>
          )}
        </div>

        {/* Hint text */}
        <p className="text-[10px] text-[var(--text-tertiary)] mt-1.5 text-center opacity-60">
          Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}