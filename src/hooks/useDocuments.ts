import { useState, useEffect, useCallback } from "react";
import { authFetch } from "../services/authFetch";

interface DocumentItem {
  title: string;
  source: string;
  file_type: string;
  chunk_count: number;
  status: string;
}

interface DocumentsData {
  documents: DocumentItem[];
  totalDocs: number;
  totalChunks: number;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

const DOCS_URL = "/api/rag/documents";

export function useDocuments(): DocumentsData {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [totalDocs, setTotalDocs] = useState(0);
  const [totalChunks, setTotalChunks] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trigger, setTrigger] = useState(0);

  const fetchDocs = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await authFetch(DOCS_URL, { signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDocuments(data.documents ?? []);
      setTotalDocs(data.total_docs ?? 0);
      setTotalChunks(data.total_chunks ?? 0);
      setError(null);
      setLoading(false);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchDocs(controller.signal);
    return () => controller.abort();
  }, [fetchDocs, trigger]);

  const refetch = useCallback(() => {
    setLoading(true);
    setTrigger(prev => prev + 1);
  }, []);

  return { documents, totalDocs, totalChunks, loading, error, refetch };
}
