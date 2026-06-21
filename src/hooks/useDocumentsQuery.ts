/**
 * useDocumentsQuery �� TanStack Query ���ĵ��б�����
 * ���ԭ useDocumentsStore��Zustand + ֱ�� fetch���޻��棩
 *
 * �Ľ���
 * - staleTime: 60s �� �����л�ʱ 60 ���ڲ���������
 * - gcTime: 5min �� �ڴ滺�汣�� 5 ����
 * - �ṹ������ �� �Զ�������ݱ仯
 * - ֧�� prefetchQuery �� hover Ԥȡ
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authFetch } from "../services/authFetch";

export interface DocumentItem {
  title: string;
  source: string;
  file_type: string;
  chunk_count: number;
  status: string;
}

interface DocumentsResponse {
  documents: DocumentItem[];
  total_docs: number;
  total_chunks: number;
}

const DOCS_QUERY_KEY = ["documents"] as const;
const STALE_TIME = 60_000; // 60 ���ڵ�����������������

async function fetchDocuments(): Promise<DocumentsResponse> {
  const res = await authFetch("/api/rag/documents");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return {
    documents: data.documents ?? [],
    total_docs: data.total_docs ?? 0,
    total_chunks: data.total_chunks ?? 0,
  };
}

/**
 * ��ȡ�ĵ��б����� TanStack Query ���棩
 */
export function useDocumentsQuery() {
  return useQuery({
    queryKey: DOCS_QUERY_KEY,
    queryFn: fetchDocuments,
    staleTime: STALE_TIME,
    gcTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    select: (data) => ({
      documents: data.documents,
      totalDocs: data.total_docs,
      totalChunks: data.total_chunks,
    }),
  });
}

/**
 * ��ȡ�ĵ��б��������ݣ��� ChatWidget �����ʹ�ã�
 * ���� documents ���飬�����ؼ���/����״̬
 */
export function useDocuments() {
  const { data } = useDocumentsQuery();
  return data?.documents ?? [];
}

/**
 * Ԥȡ�ĵ��б����� hover Ԥ����ʹ�ã�
 */
export function prefetchDocuments(queryClient: ReturnType<typeof useQueryClient>) {
  return queryClient.prefetchQuery({
    queryKey: DOCS_QUERY_KEY,
    queryFn: fetchDocuments,
    staleTime: STALE_TIME,
  });
}
