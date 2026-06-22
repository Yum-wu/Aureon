import { useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "../utils/toast";
import { authFetch } from "../services/authFetch";
import type { KeyboardEvent } from "react";

/** 支持的文件类型（与后端一致） */
const ALLOWED_EXTENSIONS = [".md", ".txt", ".pdf", ".docx", ".xlsx"];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

interface InputAreaProps {
  onSend: (content: string) => void;
  isLoading: boolean;
  onStop: () => void;
}

/** Container-style input — attachment button | textarea | send/stop button */
export function InputArea({ onSend, isLoading, onStop }: InputAreaProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
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

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 验证文件类型
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      toast.error(t("chat.unsupported_format", { ext }));
      e.target.value = "";
      return;
    }

    // 验证文件大小
    if (file.size > MAX_FILE_SIZE) {
      toast.error(t("chat.file_too_large"));
      e.target.value = "";
      return;
    }

    setSelectedFile(file);
  }, [t]);

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const res = await authFetch("/api/rag/upload", {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        const chunks = data.chunks_created ?? data.metadata?.chunks ?? 0;
        toast.success(t("chat.upload_success", { filename: selectedFile.name, chunks }));
        setSelectedFile(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      } else {
        const errData = await res.json().catch(() => null);
        const msg = errData?.detail || t("chat.upload_failed");
        toast.error(msg);
      }
    } catch {
      toast.error(t("chat.upload_failed"));
    } finally {
      setIsUploading(false);
    }
  }, [selectedFile, t]);

  const clearSelectedFile = useCallback(() => {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  return (
    <div className="border-t border-[var(--border)] px-4 py-3 glass-strong">
      <div className="max-w-3xl mx-auto">
        {/* 已选文件预览 */}
        {selectedFile && (
          <div className="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)]">
            <svg className="w-4 h-4 text-[var(--accent)] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            <span className="text-sm text-[var(--text-secondary)] truncate flex-1">
              {selectedFile.name}
            </span>
            <span className="text-xs text-[var(--text-tertiary)] shrink-0">
              {(selectedFile.size / 1024).toFixed(1)} KB
            </span>
            <button
              onClick={clearSelectedFile}
              className="p-0.5 rounded text-[var(--text-tertiary)] hover:text-[var(--error)] transition-colors shrink-0"
              title={t("chat.remove_file")}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="px-3 py-1 text-xs font-medium rounded-md bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              {isUploading ? t("chat.uploading") : t("chat.upload")}
            </button>
          </div>
        )}

        <div className="relative flex items-end rounded-xl border-2 border-[var(--border)] bg-[var(--bg-secondary)] transition-colors focus-within:border-[var(--accent)]">
          {/* Attachment button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="absolute bottom-3 left-3 p-1 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            title={t("chat.attach")}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept={ALLOWED_EXTENSIONS.join(",")}
            onChange={handleFileSelect}
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
