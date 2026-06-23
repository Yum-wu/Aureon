/**
 * useDeleteDocument — 删除已上传文档的 mutation hook
 *
 * 调用后端 DELETE /api/rag/upload/{filename}，同时删除:
 * - Qdrant 向量索引中的所有 chunks
 * - uploads 目录中的物理文件
 *
 * 成功后自动失效 documents query，触发列表刷新。
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { authFetch } from "../services/authFetch";
import { toast } from "../utils/toast";

export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (source: string) => {
      // source 即 metadata.source，与后端 delete_from_index(filename) 的 filename 一致
      const encoded = encodeURIComponent(source);
      const res = await authFetch(`/api/rag/upload/${encoded}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Delete failed: ${res.status}`);
      }
      return res.json();
    },
    onSuccess: () => {
      // 失效 documents 缓存，触发列表重新拉取
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      toast.success("文档已删除");
    },
    onError: (err: Error) => {
      toast.error(`删除失败: ${err.message}`);
    },
  });
}
