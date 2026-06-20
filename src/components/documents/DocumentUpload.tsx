import { useState, useEffect, useRef, useCallback, type DragEvent, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { authFetch } from "../../services/authFetch";
import { Upload, FileText, Check, X } from "lucide-react";

type UploadStatus = "idle" | "uploading" | "success" | "error";

interface UploadResult {
  filename: string;
  chunks_created: number;
  elapsed_seconds: number;
}

interface DocumentUploadProps {
  onUploadSuccess?: () => void;
}

const ALLOWED_EXTENSIONS = new Set([".md", ".txt", ".pdf", ".docx", ".xlsx"]);
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export function DocumentUpload({ onUploadSuccess }: DocumentUploadProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<'uploading' | 'parsing' | 'indexing'>('uploading');
  const [progress, setProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const progressTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const fileSizeRef = useRef<number>(0);

  const resetState = useCallback(() => {
    setStatus("idle");
    setResult(null);
    setErrorMsg("");
    setUploadPhase("uploading");
    setProgress(0);
    progressTimersRef.current.forEach(clearTimeout);
    progressTimersRef.current = [];
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
      setUploadPhase("uploading");
      setProgress(0);
      fileSizeRef.current = file.size;
      progressTimersRef.current.forEach(clearTimeout);
      progressTimersRef.current = [];

      try {
        const formData = new FormData();
        formData.append("file", file);

        const res = await authFetch("/api/rag/upload", {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(data?.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        setProgress(100);
        progressTimersRef.current.forEach(clearTimeout);
        progressTimersRef.current = [];
        // 短暂延迟让用户看到 100% 完成
        await new Promise(r => setTimeout(r, 300));
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

  // 三阶段进度模拟：根据文件大小决定总时长
  useEffect(() => {
    if (status !== "uploading") return;

    const size = fileSizeRef.current;
    const totalDuration = size < 1 * 1024 * 1024 ? 2000 : size < 5 * 1024 * 1024 ? 4000 : 6000;
    const intervalMs = 50;
    const totalTicks = totalDuration / intervalMs;
    const increment = 90 / totalTicks;

    const intervalId = setInterval(() => {
      setProgress(prev => {
        const next = prev + increment;
        return next >= 90 ? 90 : next;
      });
    }, intervalMs);

    return () => clearInterval(intervalId);
  }, [status]);

  // 根据进度自动切换阶段
  useEffect(() => {
    if (status !== "uploading") return;

    if (progress >= 70) {
      setUploadPhase("indexing");
    } else if (progress >= 30) {
      setUploadPhase("parsing");
    }
  }, [progress, status]);

  // 组件卸载时清除所有 timer
  useEffect(() => {
    return () => {
      progressTimersRef.current.forEach(clearTimeout);
    };
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
          accept=".md,.txt,.pdf,.docx,.xlsx"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="text-3xl mb-3">
          {isDragging ? <Upload size={24} /> : <FileText size={24} />}
        </div>

        <p className="text-sm font-medium text-gray-700">
          {t("documents.upload.drop_text")}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {t("documents.upload.supported_formats")}
        </p>
      </div>

      {/* Uploading state - three-phase progress bar */}
      {status === "uploading" && (
        <div
          data-testid="upload-progress"
          className="rounded-lg bg-blue-50 border border-blue-100 px-4 py-3 space-y-2"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm text-blue-700 font-medium">
              {t(`documents.upload.phase_${uploadPhase}`)}
            </span>
            <span className="text-xs text-blue-500">{Math.round(progress)}%</span>
          </div>
          {/* Progress bar */}
          <div className="w-full bg-blue-100 rounded-full h-2 overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          {/* Phase indicators */}
          <div className="flex justify-between text-xs text-blue-400">
            <span className={uploadPhase === 'uploading' ? 'text-blue-600 font-medium' : ''}>上传</span>
            <span className={uploadPhase === 'parsing' ? 'text-blue-600 font-medium' : ''}>解析</span>
            <span className={uploadPhase === 'indexing' ? 'text-blue-600 font-medium' : ''}>索引</span>
          </div>
        </div>
      )}

      {/* Success state */}
      {status === "success" && result && (
        <div
          data-testid="upload-success"
          className="flex items-center justify-between rounded-lg bg-green-50 border border-green-100 px-4 py-3"
        >
          <div className="flex items-center gap-2">
            <span className="text-green-600"><Check size={14} /></span>
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
            <span className="text-red-600"><X size={14} /></span>
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
