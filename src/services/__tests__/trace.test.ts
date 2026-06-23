import { describe, it, expect, vi, beforeEach } from 'vitest';
import { generateHexId, generateTraceparent, streamChat } from '../api';

// Mock authFetch 以便捕获 fetch 调用参数
const mockAuthFetch = vi.fn();
vi.mock('../authFetch', () => ({
  authFetch: (...args: unknown[]) => mockAuthFetch(...args),
}));

/** Helper: 创建一个空的 ReadableStream 用于 mock 响应 */
function createEmptyStream(): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.close();
    },
  });
}

describe('generateHexId', () => {
  it('生成正确长度的十六进制字符串', () => {
    // 8 字节 = 16 hex 字符
    expect(generateHexId(8)).toHaveLength(16);
    // 16 字节 = 32 hex 字符
    expect(generateHexId(16)).toHaveLength(32);
  });

  it('只包含有效的十六进制字符', () => {
    const hex = generateHexId(16);
    expect(hex).toMatch(/^[0-9a-f]+$/);
  });

  it('每次调用生成不同的值（极大概率）', () => {
    const a = generateHexId(16);
    const b = generateHexId(16);
    expect(a).not.toBe(b);
  });

  it('处理 0 字节长度', () => {
    expect(generateHexId(0)).toBe('');
  });
});

describe('generateTraceparent', () => {
  it('生成符合 W3C Trace Context 格式的字符串', () => {
    const tp = generateTraceparent();
    // 格式：00-{trace-id(32)}-{span-id(16)}-01
    // 总长度：2 + 1 + 32 + 1 + 16 + 1 + 2 = 55
    expect(tp).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
  });

  it('version 字段固定为 00', () => {
    const tp = generateTraceparent();
    expect(tp.startsWith('00-')).toBe(true);
  });

  it('trace-flags 字段固定为 01（采样）', () => {
    const tp = generateTraceparent();
    expect(tp.endsWith('-01')).toBe(true);
  });

  it('trace-id 为 32 字符十六进制', () => {
    const tp = generateTraceparent();
    const parts = tp.split('-');
    expect(parts[1]).toHaveLength(32);
    expect(parts[1]).toMatch(/^[0-9a-f]+$/);
  });

  it('span-id 为 16 字符十六进制', () => {
    const tp = generateTraceparent();
    const parts = tp.split('-');
    expect(parts[2]).toHaveLength(16);
    expect(parts[2]).toMatch(/^[0-9a-f]+$/);
  });

  it('每次调用生成不同的 trace-id', () => {
    const a = generateTraceparent();
    const b = generateTraceparent();
    const traceIdA = a.split('-')[1];
    const traceIdB = b.split('-')[1];
    expect(traceIdA).not.toBe(traceIdB);
  });
});

describe('streamChat trace 注入', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('在请求 header 中注入 traceparent 和 X-Trace-Id', async () => {
    // mock 一个成功响应（空流）
    mockAuthFetch.mockResolvedValueOnce({
      ok: true,
      body: createEmptyStream(),
    });

    await streamChat({
      message: 'hello',
      sessionId: null,
      onEvent: vi.fn(),
      onError: vi.fn(),
    });

    expect(mockAuthFetch).toHaveBeenCalledTimes(1);
    const [, init] = mockAuthFetch.mock.calls[0];
    const headers = init.headers as Headers;

    expect(headers.get('traceparent')).toMatch(
      /^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/,
    );
    // X-Trace-Id 应等于 traceparent 中的 trace-id 部分
    const traceparent = headers.get('traceparent')!;
    const expectedTraceId = traceparent.split('-')[1];
    expect(headers.get('X-Trace-Id')).toBe(expectedTraceId);
  });

  it('保留 Content-Type header', async () => {
    mockAuthFetch.mockResolvedValueOnce({
      ok: true,
      body: createEmptyStream(),
    });

    await streamChat({
      message: 'test',
      sessionId: 'session-123',
      onEvent: vi.fn(),
      onError: vi.fn(),
    });

    const [, init] = mockAuthFetch.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('每次请求生成新的 traceparent', async () => {
    mockAuthFetch.mockResolvedValue({
      ok: true,
      body: createEmptyStream(),
    });

    await streamChat({
      message: 'first',
      sessionId: null,
      onEvent: vi.fn(),
      onError: vi.fn(),
    });
    await streamChat({
      message: 'second',
      sessionId: null,
      onEvent: vi.fn(),
      onError: vi.fn(),
    });

    expect(mockAuthFetch).toHaveBeenCalledTimes(2);
    const headers1 = mockAuthFetch.mock.calls[0][1].headers as Headers;
    const headers2 = mockAuthFetch.mock.calls[1][1].headers as Headers;

    const tp1 = headers1.get('traceparent');
    const tp2 = headers2.get('traceparent');
    expect(tp1).not.toBe(tp2);
  });
});
