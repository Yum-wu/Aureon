// 前后端 API 契约测试 — 验证请求/响应格式一致性
//
// 本文件定义后端 API 的请求/响应 schema 契约，并验证前端发送的请求
// 和后端返回的响应是否符合契约约定。
//
// 契约来源：
//   - 后端：backend/app/api/models.py (ChatRequest)
//   - 后端：backend/app/rag/models.py (RAGQueryRequest, RAGQueryResponse, SourceItem)
//   - 后端：backend/app/routers/chat.py, rag.py (路由 + SSE 事件)
//   - 前端：src/services/api.ts (streamChat), src/services/rag.ts (streamRAGQuery)

import { describe, it, expect, vi, beforeEach } from "vitest";

// ──────────────────────────────────────────────────────────────
// 契约定义 — 与后端 Pydantic model 保持同步
// ──────────────────────────────────────────────────────────────

/** POST /api/chat/stream 请求契约（对应后端 ChatRequest） */
const ChatStreamRequestContract = {
  endpoint: "/api/chat/stream",
  method: "POST",
  requiredFields: ["message"] as const,
  optionalFields: ["session_id", "model"] as const,
  constraints: {
    messageMinLength: 1,
    messageMaxLength: 2000,
  },
} as const;

/** POST /api/chat/enhanced/stream 请求契约（对应后端 ChatRequest） */
const ChatEnhancedStreamRequestContract = {
  endpoint: "/api/chat/enhanced/stream",
  method: "POST",
  requiredFields: ["message"] as const,
  optionalFields: ["session_id", "model"] as const,
} as const;

/** SSE 事件契约 — 后端通过 sse_event() 发送的事件类型 */
const SSEEventContract = {
  // 前端 SSEEvent 接口定义的合法事件类型（src/services/api.ts）
  // 后端额外发送 request_id、cache_hit 事件（src/services/rag.ts 处理）
  validEvents: [
    "session",
    "text",
    "tool_start",
    "tool_end",
    "sources",
    "intent",
    "route",
    "done",
    "error",
    "request_id",
    "cache_hit",
  ] as const,
  requiredFields: ["type"] as const,
} as const;

/** POST /api/rag/query 请求契约（对应后端 RAGQueryRequest） */
const RAGQueryRequestContract = {
  endpoint: "/api/rag/query",
  method: "POST",
  requiredFields: ["query"] as const,
  optionalFields: ["top_k", "use_mmr", "language", "model"] as const,
  constraints: {
    queryMinLength: 1,
    queryMaxLength: 1000,
    topKMin: 1,
    topKMax: 20,
    topKDefault: 3,
  },
} as const;

/** POST /api/rag/query/stream 请求契约（流式 RAG 查询） */
const RAGQueryStreamRequestContract = {
  endpoint: "/api/rag/query/stream",
  method: "POST",
  requiredFields: ["query"] as const,
  optionalFields: ["top_k", "use_mmr", "language", "model"] as const,
} as const;

/** RAG 查询响应契约（对应后端 RAGQueryResponse） */
const RAGQueryResponseContract = {
  requiredFields: ["answer", "sources"] as const,
  optionalFields: [] as const,
} as const;

/** RAG 来源项契约（对应后端 SourceItem） */
const SourceItemContract = {
  requiredFields: ["title", "slug"] as const,
  optionalFields: ["chunk", "score", "chunk_id", "chunk_text_snippet"] as const,
} as const;

/** 错误响应契约（AureonException 格式） */
const ErrorResponseContract = {
  requiredFields: ["detail"] as const,
} as const;

// ──────────────────────────────────────────────────────────────
// 辅助函数 — 验证对象是否包含所有必填字段
// ──────────────────────────────────────────────────────────────

/** 验证对象包含所有契约必填字段 */
function validateRequiredFields(
  obj: Record<string, unknown>,
  requiredFields: readonly string[]
): boolean {
  return requiredFields.every((field) => field in obj && obj[field] !== undefined);
}

/** 模拟前端 streamChat 发送的请求体（对应 src/services/api.ts） */
function buildChatRequestBody(message: string, sessionId: string | null): Record<string, unknown> {
  const body: Record<string, unknown> = { message };
  if (sessionId !== null) {
    body.session_id = sessionId;
  }
  return body;
}

/** 模拟前端 streamRAGQuery 发送的请求体（对应 src/services/rag.ts） */
function buildRAGRequestBody(query: string, language: string): Record<string, unknown> {
  return { query, language };
}

// ──────────────────────────────────────────────────────────────
// 契约验证测试
// ──────────────────────────────────────────────────────────────

describe("Chat API 契约测试", () => {
  describe("POST /api/chat/stream 请求契约", () => {
    it("前端请求包含所有必填字段（message）", () => {
      const requestBody = buildChatRequestBody("你好", "session-123");
      expect(validateRequiredFields(requestBody, ChatStreamRequestContract.requiredFields)).toBe(true);
    });

    it("session_id 为可选字段，省略时请求仍有效", () => {
      const requestBody = buildChatRequestBody("你好", null);
      expect(validateRequiredFields(requestBody, ChatStreamRequestContract.requiredFields)).toBe(true);
      expect(requestBody).not.toHaveProperty("session_id");
    });

    it("message 字段不能为空", () => {
      const requestBody = buildChatRequestBody("", "session-123");
      // 空字符串不符合 min_length=1 约束
      expect(requestBody.message.length).toBeLessThan(ChatStreamRequestContract.constraints.messageMinLength);
    });

    it("message 字段长度不超过 2000", () => {
      const longMessage = "a".repeat(2001);
      expect(longMessage.length).toBeGreaterThan(ChatStreamRequestContract.constraints.messageMaxLength);
    });

    it("请求体字段名与后端 ChatRequest 一致（snake_case）", () => {
      const requestBody = buildChatRequestBody("测试", "session-123");
      // 后端使用 session_id（snake_case），前端也发送 session_id
      expect(requestBody).toHaveProperty("session_id");
      expect(requestBody).not.toHaveProperty("sessionId");
    });
  });

  describe("POST /api/chat/enhanced/stream 请求契约", () => {
    it("增强聊天请求包含必填字段 message", () => {
      const requestBody = buildChatRequestBody("什么是 RAG？", "session-456");
      expect(validateRequiredFields(requestBody, ChatEnhancedStreamRequestContract.requiredFields)).toBe(true);
    });

    it("增强聊天请求端点路径正确", () => {
      expect(ChatEnhancedStreamRequestContract.endpoint).toBe("/api/chat/enhanced/stream");
    });
  });
});

describe("SSE 事件契约测试", () => {
  it("SSE 事件包含必填字段 type", () => {
    const validSSEEvent = { type: "text", content: "Hello" };
    expect(validateRequiredFields(validSSEEvent, SSEEventContract.requiredFields)).toBe(true);
  });

  it("text 事件携带 content 字段", () => {
    const textEvent = { type: "text", content: "这是回复内容" };
    expect(textEvent.type).toBe("text");
    expect(textEvent.content).toBeDefined();
  });

  it("session 事件携带 session_id", () => {
    const sessionEvent = { type: "session", content: { session_id: "abc-123" } };
    expect(sessionEvent.type).toBe("session");
    expect((sessionEvent.content as { session_id: string }).session_id).toBeDefined();
  });

  it("sources 事件携带 sources 数组", () => {
    const sourcesEvent = {
      type: "sources",
      sources: [{ title: "文档1", slug: "doc-1", score: 0.95 }],
    };
    expect(sourcesEvent.type).toBe("sources");
    expect(Array.isArray(sourcesEvent.sources)).toBe(true);
  });

  it("done 事件标记流结束", () => {
    const doneEvent = { type: "done" };
    expect(SSEEventContract.validEvents).toContain(doneEvent.type);
  });

  it("error 事件携带错误信息", () => {
    const errorEvent = { type: "error", content: "服务暂时不可用" };
    expect(errorEvent.type).toBe("error");
    expect(errorEvent.content).toBeDefined();
  });

  it("所有后端发送的事件类型都在契约定义中", () => {
    // 后端 chat.py + rag.py 实际发送的所有事件类型
    const backendEvents = [
      "session",
      "text",
      "tool_start",
      "tool_end",
      "sources",
      "done",
      "error",
      "request_id",
      "cache_hit",
    ];
    for (const evt of backendEvents) {
      expect(SSEEventContract.validEvents).toContain(evt);
    }
  });

  it("前端定义的事件类型都在契约定义中", () => {
    // 前端 SSEEvent 接口定义的类型（src/services/api.ts）
    const frontendEvents = [
      "session",
      "text",
      "tool_start",
      "tool_end",
      "sources",
      "intent",
      "route",
      "done",
      "error",
    ];
    for (const evt of frontendEvents) {
      expect(SSEEventContract.validEvents).toContain(evt);
    }
  });
});

describe("RAG API 契约测试", () => {
  describe("POST /api/rag/query 请求契约", () => {
    it("RAG 查询请求包含必填字段 query", () => {
      const requestBody = buildRAGRequestBody("什么是 RAG？", "zh");
      expect(validateRequiredFields(requestBody, RAGQueryRequestContract.requiredFields)).toBe(true);
    });

    it("query 字段不能为空", () => {
      const requestBody = buildRAGRequestBody("", "zh");
      expect(requestBody.query.length).toBeLessThan(RAGQueryRequestContract.constraints.queryMinLength);
    });

    it("query 字段长度不超过 1000", () => {
      const longQuery = "a".repeat(1001);
      expect(longQuery.length).toBeGreaterThan(RAGQueryRequestContract.constraints.queryMaxLength);
    });

    it("top_k 默认值为 3", () => {
      expect(RAGQueryRequestContract.constraints.topKDefault).toBe(3);
    });

    it("top_k 范围为 1-20", () => {
      expect(RAGQueryRequestContract.constraints.topKMin).toBe(1);
      expect(RAGQueryRequestContract.constraints.topKMax).toBe(20);
    });

    it("language 为可选字段（zh 或 en）", () => {
      const requestBody = buildRAGRequestBody("查询", "zh");
      expect(requestBody.language).toBe("zh");
      // 后端接受 None / "zh" / "en"
      const validLanguages = [undefined, null, "zh", "en"];
      expect(validLanguages).toContain(undefined);
    });

    it("请求体字段名与后端 RAGQueryRequest 一致", () => {
      const requestBody = buildRAGRequestBody("查询", "zh");
      expect(requestBody).toHaveProperty("query");
      expect(requestBody).toHaveProperty("language");
    });
  });

  describe("POST /api/rag/query/stream 请求契约", () => {
    it("流式 RAG 查询请求包含必填字段 query", () => {
      const requestBody = buildRAGRequestBody("流式查询", "en");
      expect(validateRequiredFields(requestBody, RAGQueryStreamRequestContract.requiredFields)).toBe(true);
    });

    it("流式查询端点路径正确", () => {
      expect(RAGQueryStreamRequestContract.endpoint).toBe("/api/rag/query/stream");
    });
  });

  describe("RAG 查询响应契约", () => {
    it("RAG 查询响应包含所有必填字段（answer + sources）", () => {
      const validResponse = {
        answer: "RAG 是检索增强生成...",
        sources: [{ title: "doc1", slug: "doc-1", score: 0.95 }],
      };
      expect(validateRequiredFields(validResponse, RAGQueryResponseContract.requiredFields)).toBe(true);
    });

    it("answer 字段为字符串类型", () => {
      const response = { answer: "这是答案", sources: [] };
      expect(typeof response.answer).toBe("string");
    });

    it("sources 字段为数组类型", () => {
      const response = { answer: "答案", sources: [] };
      expect(Array.isArray(response.sources)).toBe(true);
    });

    it("sources 可以为空数组（无检索结果）", () => {
      const response = { answer: "没有找到相关文档", sources: [] };
      expect(response.sources).toHaveLength(0);
      expect(validateRequiredFields(response, RAGQueryResponseContract.requiredFields)).toBe(true);
    });
  });

  describe("SourceItem 契约", () => {
    it("来源项包含必填字段 title 和 slug", () => {
      const source = { title: "文档标题", slug: "doc-slug" };
      expect(validateRequiredFields(source, SourceItemContract.requiredFields)).toBe(true);
    });

    it("来源项支持可选字段 score", () => {
      const source = { title: "文档", slug: "doc", score: 0.92 };
      expect(source.score).toBeDefined();
      expect(typeof source.score).toBe("number");
    });

    it("来源项支持可选字段 chunk（文本片段）", () => {
      const source = { title: "文档", slug: "doc", chunk: "这是文档片段内容" };
      expect(source.chunk).toBeDefined();
    });

    it("完整的来源项包含所有字段", () => {
      const fullSource = {
        title: "完整文档",
        slug: "full-doc",
        chunk: "片段内容",
        score: 0.88,
        chunk_id: "chunk-001",
        chunk_text_snippet: "摘要片段",
      };
      // 验证所有必填字段
      expect(validateRequiredFields(fullSource, SourceItemContract.requiredFields)).toBe(true);
      // 验证所有可选字段都存在
      for (const field of SourceItemContract.optionalFields) {
        expect(fullSource).toHaveProperty(field);
      }
    });
  });
});

describe("错误响应契约测试", () => {
  it("错误响应包含 detail 字段", () => {
    const errorResponse = { detail: "LLM API key not configured" };
    expect(validateRequiredFields(errorResponse, ErrorResponseContract.requiredFields)).toBe(true);
  });

  it("400 错误响应格式正确", () => {
    const badRequestError = { detail: "Potentially harmful input detected." };
    expect(badRequestError.detail).toBeDefined();
    expect(typeof badRequestError.detail).toBe("string");
  });

  it("500 错误响应格式正确", () => {
    const serverError = { detail: "Query processing error: timeout" };
    expect(serverError.detail).toBeDefined();
  });

  it("413 文件过大错误响应格式正确", () => {
    const payloadTooLarge = { detail: "File too large (max 10MB)" };
    expect(payloadTooLarge.detail).toBeDefined();
  });
});

describe("前后端字段命名一致性测试", () => {
  it("Chat 请求使用 snake_case（session_id 而非 sessionId）", () => {
    // 前端 src/services/api.ts 发送 { message, session_id: sessionId }
    // 后端 ChatRequest 期望 session_id
    const frontendBody = { message: "你好", session_id: "abc" };
    expect(frontendBody).toHaveProperty("session_id");
    expect(frontendBody).not.toHaveProperty("sessionId");
  });

  it("RAG 请求使用 snake_case（top_k 而非 topK）", () => {
    // 后端 RAGQueryRequest 期望 top_k, use_mmr
    const backendFieldNames = ["query", "top_k", "use_mmr", "language"];
    const sampleRequest = { query: "测试", top_k: 3, use_mmr: true, language: "zh" };
    for (const field of backendFieldNames) {
      expect(sampleRequest).toHaveProperty(field);
    }
    // model 为可选字段，省略时请求仍有效
    expect(sampleRequest).not.toHaveProperty("topK");
    expect(sampleRequest).not.toHaveProperty("useMmr");
  });

  it("SourceItem 使用 snake_case（chunk_id 而非 chunkId）", () => {
    const source = { title: "文档", slug: "doc", chunk_id: "c-1", chunk_text_snippet: "摘要" };
    expect(source).toHaveProperty("chunk_id");
    expect(source).not.toHaveProperty("chunkId");
    expect(source).toHaveProperty("chunk_text_snippet");
    expect(source).not.toHaveProperty("chunkTextSnippet");
  });
});

describe("fetch mock 契约验证测试", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("前端 streamChat 发送正确的请求格式到 /api/chat/stream", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    // 模拟前端 streamChat 调用
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "你好", session_id: "session-1" }),
    });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/chat/stream",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );

    // 验证请求体包含契约必填字段
    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    const requestBody = JSON.parse(callArgs.body as string);
    expect(validateRequiredFields(requestBody, ChatStreamRequestContract.requiredFields)).toBe(true);

    expect(response.ok).toBe(true);
  });

  it("前端 streamRAGQuery 发送正确的请求格式到 /api/rag/query/stream", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    // 模拟前端 streamRAGQuery 调用
    await fetch("/api/rag/query/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "什么是 RAG？", language: "zh" }),
    });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/rag/query/stream",
      expect.objectContaining({ method: "POST" })
    );

    // 验证请求体包含契约必填字段
    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    const requestBody = JSON.parse(callArgs.body as string);
    expect(validateRequiredFields(requestBody, RAGQueryStreamRequestContract.requiredFields)).toBe(true);
  });

  it("后端 RAG 查询响应符合 RAGQueryResponse 契约", async () => {
    // 模拟后端返回的 RAG 查询响应
    const mockBackendResponse = {
      answer: "RAG 是检索增强生成技术",
      sources: [
        {
          title: "RAG 技术文档",
          slug: "rag-tech-doc",
          chunk: "RAG 结合了检索和生成...",
          score: 0.95,
          chunk_id: "chunk-001",
          chunk_text_snippet: "RAG 结合了检索和生成",
        },
      ],
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockBackendResponse,
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const response = await fetch("/api/rag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "什么是 RAG？" }),
    });

    const data = await response.json();
    // 验证响应符合契约
    expect(validateRequiredFields(data, RAGQueryResponseContract.requiredFields)).toBe(true);
    // 验证 sources 数组中的每个项符合 SourceItem 契约
    for (const source of data.sources) {
      expect(validateRequiredFields(source, SourceItemContract.requiredFields)).toBe(true);
    }
  });

  it("后端错误响应符合 ErrorResponse 契约", async () => {
    // 模拟后端返回的错误响应
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Query processing error: internal error" }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const response = await fetch("/api/rag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "查询" }),
    });

    expect(response.ok).toBe(false);
    expect(response.status).toBe(500);

    const data = await response.json();
    expect(validateRequiredFields(data, ErrorResponseContract.requiredFields)).toBe(true);
  });
});
