/** 文档状态 Store */

import { create } from "zustand";
import type { DocumentsState } from "./types";
import { authFetch } from "../services/authFetch";

const DOCS_URL = "/api/rag/documents";

export const useDocumentsStore = create<DocumentsState>((set) => {
  let abortController: AbortController | null = null;

  const fetchDocuments = async () => {
    // 取消之前的请求
    abortController?.abort();
    abortController = new AbortController();

    set({ loading: true });
    try {
      const res = await authFetch(DOCS_URL, { signal: abortController.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      set({
        documents: data.documents ?? [],
        totalDocs: data.total_docs ?? 0,
        totalChunks: data.total_chunks ?? 0,
        error: null,
        loading: false,
      });
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      set({
        error: err instanceof Error ? err.message : String(err),
        loading: false,
      });
    }
  };

  return {
    documents: [],
    totalDocs: 0,
    totalChunks: 0,
    loading: true,
    error: null,
    filter: "",

    fetchDocuments,

    refetch: () => {
      set({ loading: true });
      fetchDocuments();
    },

    setFilter: (filter: string) => {
      set({ filter });
    },
  };
});
