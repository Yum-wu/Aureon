import { describe, it, expect, vi, beforeEach } from 'vitest';
import { streamRAGQuery, type Citation, type RAGStreamOptions } from '../rag';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

/** Helper: create a ReadableStream from SSE text */
function createSSEStream(sseText: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(sseText));
      controller.close();
    },
  });
}

describe('streamRAGQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls correct endpoint with question and processes token events', async () => {
    const ssePayload =
      'data: {"type":"token","content":"Hello"}\n' +
      'data: {"type":"token","content":" World"}\n' +
      'data: {"type":"citations","citations":[{"id":1,"title":"Doc","snippet":"snippet"}]}\n';

    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: createSSEStream(ssePayload),
    });

    const tokens: string[] = [];
    let resultCitations: Citation[] = [];

    const options: RAGStreamOptions = {
      onToken: (t) => tokens.push(t),
      onCitations: (c) => { resultCitations = c; },
      onError: vi.fn(),
    };

    await streamRAGQuery('test question', options);

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/rag/query/stream',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: 'test question' }),
      }),
    );

    expect(tokens).toEqual(['Hello', ' World']);
    expect(resultCitations).toEqual([{ id: 1, title: 'Doc', snippet: 'snippet' }]);
  });

  it('handles fetch errors and invokes onError', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network down'));

    const errors: string[] = [];
    const options: RAGStreamOptions = {
      onToken: vi.fn(),
      onCitations: vi.fn(),
      onError: (e) => errors.push(e),
    };

    await streamRAGQuery('fail question', options);

    expect(errors).toEqual(['Network down']);
  });

  it('handles non-ok response and invokes onError', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      body: null,
    });

    const errors: string[] = [];
    const options: RAGStreamOptions = {
      onToken: vi.fn(),
      onCitations: vi.fn(),
      onError: (e) => errors.push(e),
    };

    await streamRAGQuery('server error', options);

    expect(errors.length).toBe(1);
    expect(errors[0]).toContain('500');
  });

  it('handles cross-chunk SSE buffering correctly', async () => {
    // Simulate a chunk boundary splitting an SSE event in half
    const part1 = 'data: {"type":"token","content":"Hel';
    const part2 = 'lo"}\n';

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(part1));
        controller.enqueue(encoder.encode(part2));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({ ok: true, body: stream });

    const tokens: string[] = [];
    const options: RAGStreamOptions = {
      onToken: (t) => tokens.push(t),
      onCitations: vi.fn(),
      onError: vi.fn(),
    };

    await streamRAGQuery('buffer test', options);

    expect(tokens).toEqual(['Hello']);
  });

  it('does nothing on AbortError', async () => {
    const abortErr = new DOMException('Aborted', 'AbortError');
    mockFetch.mockRejectedValueOnce(abortErr);

    const errors: string[] = [];
    const options: RAGStreamOptions = {
      onToken: vi.fn(),
      onCitations: vi.fn(),
      onError: (e) => errors.push(e),
    };

    await streamRAGQuery('aborted', options);

    // AbortError should be silently swallowed
    expect(errors).toEqual([]);
  });
});
