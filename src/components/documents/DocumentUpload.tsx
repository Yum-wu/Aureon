import { useState, useRef, useCallback, type DragEvent, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

type UploadStatus = "idle" | "uploading" | "success" | "error";

interface UploadResult {
  filename: string;
  chunks_created: number;
  elapsed_seconds: number;
}

interface DocumentUploadProps {
  onUploadSuccess?: () => void;
}

const ALLOWED_EXTENSIONS = new Set([".md", ".txt"]);
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export function DocumentUpload({ onUploadSuccess }: DocumentUploadProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetState = useCallback(() => {
    setStatus("idle");
    setResult(null);
    setErrorMsg("");
  }, []);

  const uploadFile = useCallback(
    async (file: File) => {
      // Check file size
      if (file.size > MAX_FILE_SIZE) {
        setStatus("error");
        setErrorMsg(t("documents.upload.file_too_large"));
        return;
      }

      // Validate extension
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      if (!ALLOWED_EXTENSIONS.has(ext)) {
        setStatus("error");
        setErrorMsg(t("documents.upload.unsupported_format", { ext }));
        return;
      }

      setStatus("uploading");
      setErrorMsg("");
      setResult(null);

      try {
        const formData = new FormData();
        formData.append("file", file);

        const res = await fetch("/api/rag/upload", {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(data?.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        setResult({
          filename: data.filename,
          chunks_created: data.chunks_created,
          elapsed_seconds: data.elapsed_seconds,
        });
        setStatus("success");
        onUploadSuccess?.();
      } catch (err) {
        setStatus("error");
        setErrorMsg(
          err instanceof Error ? err.message : t("documents.upload.upload_failed")
        );
      }
    },
    [t, onUploadSuccess]
  );

  const handleFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) uploadFile(file);
      // Reset input so same file can be re-selected
      e.target.value = "";
    },
    [uploadFile]
  );

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) uploadFile(file);
    },
    [uploadFile]
  );

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        data-testid="upload-dropzone"
        onClick={handleClick}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`
          relative flex flex-col items-center justify-center
          rounded-xl border-2 border-dashed p-8 cursor-pointer
          transition-colors duration-200
          ${
            isDragging
              ? "border-blue-400 bg-blue-50"
              : "border-gray-200 bg-gray-50/50 hover:border-gray-300 hover:bg-gray-50"
          }
        `}
      >
        <input
          ref={fileInputRef}
          data-testid="upload-file-input"
          type="file"
          accept=".md,.txt"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="text-3xl mb-3">
          {isDragging ? "📥" : "📄"}
        </div>

        <p className="text-sm font-medium text-gray-700">
          {t("documents.upload.drop_text")}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {t("documents.upload.supported_formats")}
        </p>
      </div>

      {/* Uploading state */}
      {status === "uploading" && (
        <div
          data-testid="upload-progress"
          className="flex items-center gap-3 rounded-lg bg-blue-50 border border-blue-100 px-4 py-3"
        >
          <div className="flex space-x-1">
            <span
              className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
              style={{ animationDelay: "150ms" }}
            />
            <span
              className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
              style={{ animationDelay: "300ms" }}
            />
          </div>
          <span className="text-sm text-blue-700">
            {t("documents.upload.uploading")}
          </span>
        </div>
      )}

      {/* Success state */}
      {status === "success" && result && (
        <div
          data-testid="upload-success"
          className="flex items-center justify-between rounded-lg bg-green-50 border border-green-100 px-4 py-3"
        >
          <div className="flex items-center gap-2">
            <span className="text-green-600">✓</span>
            <span className="text-sm text-green-700">
              {t("documents.upload.success", {
                filename: result.filename,
                chunks: result.chunks_created,
              })}
            </span>
          </div>
          <button
            onClick={resetState}
            className="text-xs text-green-600 hover:text-green-800"
          >
            {t("documents.upload.upload_another")}
          </button>
        </div>
      )}

      {/* Error state */}
      {status === "error" && (
        <div
          data-testid="upload-error"
          className="flex items-center justify-between rounded-lg bg-red-50 border border-red-100 px-4 py-3"
        >
          <div className="flex items-center gap-2">
            <span className="text-red-600">✕</span>
            <span className="text-sm text-red-700">{errorMsg}</span>
          </div>
          <button
            onClick={resetState}
            className="text-xs text-red-600 hover:text-red-800"
          >
            {t("documents.upload.retry")}
          </button>
        </div>
      )}
    </div>
  );
}
