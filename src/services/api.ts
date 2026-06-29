/** 后端 API 地址（通过环境变量配置，默认本地开发） */
const API_URL = (import.meta.env.VITE_API_URL as string) || "/api/chat/stream";

/** 增强 API 地址（含 RAG 意图路由） */
const ENHANCED_API_URL = (import.meta.env.VITE_ENHANCED_API_URL as string) || "/api/chat/enhanced/stream";

import { authFetch } from "./authFetch";

/** SSE 事件数据结构 */
export interface SSEEvent {
  type: "session" | "text" | "tool_start" | "tool_end" | "sources" | "intent" | "route" | "done" | "error";
  content: unknown;
  sources?: Array<{ title: string; slug: string; score?: number }>;
}

/** 流式聊天参数 */
export interface StreamChatParams {
  message: string;
  sessionId: string | null;
  onEvent: (event: SSEEvent) => void;
  onError: (error: string) => void;
  signal?: AbortSignal;
}

const BACKPRESSURE_HIGH_WATER = 50; // 未处理事件超过此数则暂停读取

/**
 * 生成指定字节长度的十六进制字符串。
 *
 * @param byteLength - 字节长度（1 字节 = 2 个 hex 字符）
 * @returns 小写十六进制字符串（长度 = byteLength * 2）
 *
 * @example
 *   generateHexId(8);  // => "a3f12b9c4d5e6f70"（16 字符）
 *   generateHexId(16); // => 32 字符
 */
export function generateHexId(byteLength: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(byteLength));
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * 生成 W3C Trace Context 的 traceparent header。
 *
 * 格式：`00-{trace-id}-{span-id}-01`
 * - version: 00（固定）
 * - trace-id: 32 字符十六进制（16 字节）
 * - span-id: 16 字符十六进制（8 字节）
 * - trace-flags: 01（采样标志位，01 表示采样）
 *
 * @returns 符合 W3C Trace Context 规范的 traceparent 字符串
 *
 * @example
 *   generateTraceparent(); // => "00-a3f12b9c4d5e6f70a3f12b9c4d5e6f70-9c4d5e6f70a3f12b-01"
 */
export function generateTraceparent(): string {
  const traceId = generateHexId(16); // 16 bytes = 32 hex chars
  const spanId = generateHexId(8); // 8 bytes = 16 hex chars
  return `00-${traceId}-${spanId}-01`;
}

/**
 * 检测当前运行环境是否支持 crypto.getRandomValues。
 *
 * 浏览器环境原生支持；Node.js 17+ 也通过 globalThis.crypto 提供。
 * 旧环境降级为不注入 traceparent。
 */
function isCryptoAvailable(): boolean {
  return (
    typeof crypto !== "undefined" &&
    typeof crypto.getRandomValues === "function"
  );
}

/**
 * 构建带 trace 传播 header 的 Headers 对象。
 *
 * 在所有出站请求中注入：
 * - `traceparent`: W3C Trace Context 标准 header，供后端 OTel 关联前后端 span
 * - `X-Trace-Id`: 简化版 trace ID，用于日志关联（非标准但便于检索）
 *
 * 若 crypto API 不可用（旧浏览器/SSR），降级为不添加。
 *
 * @param existing - 已有的 Headers 对象（可选）
 * @returns 合并了 trace header 的 Headers 对象
 */
function withTraceHeaders(existing?: HeadersInit): Headers {
  const headers = new Headers(existing);
  if (isCryptoAvailable()) {
    try {
      const traceparent = generateTraceparent();
      headers.set("traceparent", traceparent);
      // 从 traceparent 中提取 trace-id 用于日志关联
      // 格式：00-{trace-id}-{span-id}-01
      const parts = traceparent.split("-");
      if (parts.length >= 2) {
        headers.set("X-Trace-Id", parts[1]);
      }
    } catch {
      // crypto 调用异常时降级为不添加 trace header
    }
  }
  return headers;
}

/**
 * 通用 SSE 流处理函数
 * @param url - API 端点 URL
 * @param body - 请求体
 * @param onEvent - 事件回调
 * @param onError - 错误回调
 * @param signal - AbortSignal
 */
async function fetchSSE(
  url: string,
  body: Record<string, unknown>,
  onEvent: (event: SSEEvent) => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    // 注入 traceparent + X-Trace-Id header 用于全链路追踪
    const headers = withTraceHeaders({ "Content-Type": "application/json" });

    const response = await authFetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
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
    let pendingEvents = 0;

    while (true) {
      // 背压：如果 React 处理速度跟不上，暂停读取
      if (pendingEvents > BACKPRESSURE_HIGH_WATER) {
        await new Promise((resolve) => setTimeout(resolve, 10));
        continue;
      }

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data:")) continue;

        const data = trimmed.slice(5).trim();
        try {
          const event: SSEEvent = JSON.parse(data);
          pendingEvents++;
          onEvent(event);
          // Defer decrement to next macrotask so pendingEvents reflects
          // events dispatched but not yet rendered by React
          setTimeout(() => pendingEvents--, 0);
        } catch {
          continue;
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    onError(
      err instanceof Error ? err.message : "网络请求异常，请检查后端是否运行",
    );
  }
}

/**
 * SSE 带指数退避自动重连。
 * 仅对网络错误（TypeError）重试，最大 3 次，退避 1s/2s/4s。
 */
async function fetchSSEWithRetry(
  url: string,
  body: Record<string, unknown>,
  onEvent: (event: SSEEvent) => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
  maxRetries = 3,
): Promise<void> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      await fetchSSE(url, body, onEvent, onError, signal);
      return;
    } catch (err) {
      if (attempt === maxRetries) throw err;
      if (err instanceof TypeError && (err as Error).message?.includes('fetch')) {
        await new Promise(r => setTimeout(r, Math.min(1000 * 2 ** attempt, 16000)));
        continue;
      }
      throw err;
    }
  }
}

/**
 * 以 SSE 流式方式调用后端 Chat API，带背压控制
 */
export async function streamChat(params: StreamChatParams): Promise<void> {
  const { message, sessionId, onEvent, onError, signal } = params;
  await fetchSSEWithRetry(
    API_URL,
    { message, session_id: sessionId },
    onEvent,
    onError,
    signal,
  );
}

/**
 * 以 SSE 流式方式调用增强 Chat API（含 RAG 意图路由）
 */
export async function streamEnhancedChat(params: StreamChatParams): Promise<void> {
  const { message, sessionId, onEvent, onError, signal } = params;
  await fetchSSEWithRetry(
    ENHANCED_API_URL,
    { message, session_id: sessionId },
    onEvent,
    onError,
    signal,
  );
}
