import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { authFetch } from "../../services/authFetch";
import { uploadRagFile } from "../../services/ragUpload";

const RAG_BASE_URL =
  (import.meta.env.VITE_API_RAG_URL as string)?.replace(/\/query$/, "") || "/api/rag";
const RAG_UPLOAD_URL = RAG_BASE_URL.endsWith("/upload")
  ? RAG_BASE_URL
  : `${RAG_BASE_URL}/upload`;
const RAG_UPLOADS_URL = RAG_BASE_URL.endsWith("/upload")
  ? RAG_BASE_URL.replace(/\/upload$/, "/uploads")
  : `${RAG_BASE_URL}/uploads`;
const SUPPORTED_UPLOAD_EXTENSIONS = ["md", "txt", "pdf", "docx", "xlsx", "csv", "pptx"];
const SUPPORTED_UPLOAD_ACCEPT = SUPPORTED_UPLOAD_EXTENSIONS.map((ext) => `.${ext}`).join(",");

interface RagUploadPanelProps {
  open: boolean;
}

export function RagUploadPanel({ open }: RagUploadPanelProps) {
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);

  const fetchUploadedFiles = useCallback(async () => {
    try {
      const res = await authFetch(RAG_UPLOADS_URL);
      if (!res.ok) return;
      const data = await res.json();
      setUploadedFiles(
        (data.files || []).map((f: { filename: string }) => f.filename),
      );
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchUploadedFiles();
  }, [fetchUploadedFiles]);

  const handleDeleteFile = useCallback(
    async (filename: string) => {
      try {
        const res = await authFetch(
          `${RAG_UPLOAD_URL}/${encodeURIComponent(filename)}`,
          { method: "DELETE" },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setUploadedFiles((prev) => prev.filter((f) => f !== filename));
        setUploadMessage({
          type: "success",
          text: t("rag.upload.deleted", { filename }),
        });
      } catch (err) {
        setUploadMessage({
          type: "error",
          text: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [t],
  );

  const handleUpload = useCallback(
    async (file: File) => {
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (!ext || !SUPPORTED_UPLOAD_EXTENSIONS.includes(ext)) {
        setUploadMessage({ type: "error", text: t("rag.upload.badFormat") });
        return;
      }

      setUploading(true);
      setUploadMessage(null);

      try {
        const data = await uploadRagFile(file, { uploadUrl: RAG_UPLOAD_URL });
        const warnings = Array.isArray(data.warnings)
          ? data.warnings.filter((warning: unknown) => typeof warning === "string")
          : [];
        const successText = t("rag.upload.success", {
          filename: file.name,
          chunks: data.chunks_created,
        });
        setUploadMessage({
          type: "success",
          text: warnings.length ? `${successText}\n${warnings.join("\n")}` : successText,
        });
        fetchUploadedFiles();
      } catch (err) {
        setUploadMessage({
          type: "error",
          text: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setUploading(false);
      }
    },
    [t, fetchUploadedFiles],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleUpload(file);
    },
    [handleUpload],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  if (!open) return null;

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-4">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => document.getElementById("rag-upload-input")?.click()}
        className={`relative border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200 ${
          dragOver
            ? "border-blue-500 bg-blue-50 scale-[1.02] shadow-lg"
            : "border-gray-300 hover:border-gray-400 bg-gray-50 hover:bg-gray-100"
        }`}
      >
        <input
          id="rag-upload-input"
          type="file"
          accept={SUPPORTED_UPLOAD_ACCEPT}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleUpload(file);
            e.target.value = "";
          }}
        />
        {uploading ? (
          <div className="text-sm text-gray-500">
            <span className="inline-block animate-spin mr-2">?</span>
            {t("rag.upload.uploading")}
          </div>
        ) : (
          <>
            <div className="text-2xl mb-2">?</div>
            <p className="text-sm text-gray-600">{t("rag.upload.hint")}</p>
            <p className="text-xs text-gray-400 mt-1">
              {t("rag.upload.formats")}
            </p>
            {dragOver && (
              <div className="absolute inset-0 flex items-center justify-center bg-blue-500/10 rounded-xl">
                <span className="text-blue-600 font-semibold text-sm">
                  释放以上传
                </span>
              </div>
            )}
          </>
        )}
      </div>
      {uploadMessage && (
        <div
          className={`mt-3 text-sm px-3 py-2 rounded-lg ${
            uploadMessage.type === "success"
              ? "bg-green-50 text-green-700 border border-green-200"
              : "bg-red-50 text-red-700 border border-red-200"
          }`}
        >
          {uploadMessage.type === "success" ? "? " : "?? "}
          {uploadMessage.text}
        </div>
      )}

      {uploadedFiles.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-gray-500 mb-2">
            {t("rag.upload.files")}
          </p>
          <div className="space-y-1.5">
            {uploadedFiles.map((fname) => (
              <div
                key={fname}
                className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 text-sm"
              >
                <span className="text-gray-700 truncate mr-2">? {fname}</span>
                <button
                  onClick={() => handleDeleteFile(fname)}
                  className="text-xs text-red-500 hover:text-red-700 hover:bg-red-50 px-2 py-0.5 rounded transition-colors shrink-0"
                >
                  {t("rag.upload.delete")}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
