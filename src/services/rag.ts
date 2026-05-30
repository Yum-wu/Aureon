/** RAG 查询后端 SSE streaming 地址 */
const RAG_STREAM_URL = "/api/rag/query/stream";

/** 引用来源 */
export interface Citation {
  id: number;
  title: string;
  snippet: string;
  url?: string;
}

/** Backend source object from SSE events */
interface BackendSource {
  index?: number;
  title?: string;
  slug?: string;
  chunk?: string;
  snippet?: string;
}

/**
 * Parse a single SSE data line and return typed event or null.
 */
function parseSSELine(line: string): { type: string; content?: string; citations?: Citation[] } | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("data:")) return null;

  try {
    const event = JSON.parse(trimmed.slice(5).trim());
    // Backend sends "text", frontend accepts both "text" and "token"
    if (event.type === "text" || event.type === "token") {
      return { type: "text", content: event.content };
    }
    // Backend sends "sources" or "citations"
    if (event.type === "sources" || event.type === "citations") {
      const sources = event.sources || event.citations || [];
      return {
        type: "sources",
        citations: sources.map((s: BackendSource, i: number) => {
          const citation: Citation = {
            id: s.index || i + 1,
            title: s.title || "",
            snippet: s.chunk || s.snippet || "",
          };
          if (s.slug) citation.url = `/search?ref=${s.slug}`;
          return citation;
        }),
      };
    }
    // Individual citation chunk
    if (event.type === "citation") {
      return {
        type: "sources",
        citations: [{
          id: event.source?.index || 1,
          title: event.source?.title || "",
          snippet: event.source?.chunk || "",
        }],
      };
    }
    // Cache hit, done, error — pass through
    if (event.type === "cache_hit" || event.type === "done") {
      return { type: event.type };
    }
  } catch {
    // Skip invalid JSON
  }
  return null;
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
      body: JSON.stringify({ query: question }),
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
        const parsed = parseSSELine(line);
        if (parsed?.type === "text" && parsed.content) {
          onToken(parsed.content);
        } else if (parsed?.type === "sources" && parsed.citations) {
          onCitations(parsed.citations);
        }
      }
    }

    // Process remaining event in buffer
    if (buffer.trim()) {
      const parsed = parseSSELine(buffer);
      if (parsed?.type === "text" && parsed.content) {
        onToken(parsed.content);
      } else if (parsed?.type === "sources" && parsed.citations) {
        onCitations(parsed.citations);
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    onError(err instanceof Error ? err.message : "网络请求异常，请检查后端是否运行");
  }
}
