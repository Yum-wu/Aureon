/** RAG 查询后端 SSE streaming 地址 */
const RAG_STREAM_URL = "/api/rag/query/stream";

/** 引用来源 */
export interface Citation {
  id: number;
  title: string;
  snippet: string;
  url?: string;
}

/** streamRAGQuery 回调选项 */
export interface RAGStreamOptions {
  onToken: (token: string) => void;
  onCitations: (citations: Citation[]) => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

/**
 * 以 SSE 流式方式调用 /api/rag/query/stream，逐 token 推送结果。
 *
 * 内部维护跨 chunk 缓冲区，防止 SSE 事件在 chunk 边界被截断。
 */
export async function streamRAGQuery(
  question: string,
  options: RAGStreamOptions,
): Promise<void> {
  const { onToken, onCitations, onError, signal } = options;

  try {
    const response = await fetch(RAG_STREAM_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal,
    });

    if (!response.ok) {
      onError(`请求失败 (${response.status})`);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      onError("无法读取响应流");
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // 保留未完成行到下一 chunk
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data:")) continue;

        const data = trimmed.slice(5).trim();
        try {
          const event = JSON.parse(data);
          if (event.type === "token") {
            onToken(event.content);
          } else if (event.type === "citations") {
            onCitations(event.citations);
          }
        } catch {
          // Skip invalid JSON
        }
      }
    }

    // 处理 buffer 中剩余的最后一个事件
    if (buffer.trim()) {
      const trimmed = buffer.trim();
      if (trimmed.startsWith("data:")) {
        try {
          const event = JSON.parse(trimmed.slice(5).trim());
          if (event.type === "token") {
            onToken(event.content);
          } else if (event.type === "citations") {
            onCitations(event.citations);
          }
        } catch {
          // Skip invalid final event
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    onError(err instanceof Error ? err.message : "网络请求异常，请检查后端是否运行");
  }
}
