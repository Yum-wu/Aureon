import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { authFetch } from "../services/authFetch";
import i18n from "../i18n/config";
import { RagQueryForm } from "./rag/RagQueryForm";
import { RagQueryResult } from "./rag/RagQueryResult";
import { RagUploadPanel } from "./rag/RagUploadPanel";
import type { Source } from "./rag/RagSourceList";

const RAG_API_URL =
  (import.meta.env.VITE_API_RAG_URL as string) || "/api/rag/query";

const RAG_STREAM_URL = `${RAG_API_URL}/stream`;

interface SSEEvent {
  type: "sources" | "text" | "done" | "error";
  sources?: Source[];
  content?: string;
  model?: string;
}

export function RagQuery() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const handleStreamSubmit = async () => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    // Cancel previous request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setAnswer("");
    setSources([]);

    try {
      const res = await authFetch(RAG_STREAM_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: trimmed,
          top_k: 3,
          use_mmr: true,
          language: (i18n.language || "en").startsWith("zh") ? "zh" : "en",
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(body || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine || !trimmedLine.startsWith("data:")) continue;

          try {
            const event: SSEEvent = JSON.parse(trimmedLine.slice(5).trim());
            if (event.type === "sources" && event.sources) {
              setSources(event.sources);
            } else if (event.type === "text" && event.content) {
              setAnswer((prev) => prev + event.content);
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-gray-800">
              📚 {t("rag.title")}
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">
              {t("rag.description")}
            </p>
          </div>
          <button
            onClick={() => setUploadOpen(!uploadOpen)}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors shrink-0 ml-4"
          >
            {uploadOpen ? "▲" : "▼"} {t("rag.upload.toggle")}
          </button>
        </div>
      </header>

      {/* Upload Panel */}
      <RagUploadPanel open={uploadOpen} onToggle={() => setUploadOpen(!uploadOpen)} />

      {/* Input Form */}
      <RagQueryForm
        query={query}
        onQueryChange={setQuery}
        loading={loading}
        onSubmit={handleStreamSubmit}
      />

      {/* Results */}
      <RagQueryResult
        answer={answer}
        sources={sources}
        loading={loading}
        error={error}
      />
    </div>
  );
}
