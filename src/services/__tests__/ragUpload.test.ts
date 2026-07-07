import { describe, it, expect, vi, beforeEach } from "vitest";
import { uploadRagFile } from "../ragUpload";

const mockAuthFetch = vi.fn();
vi.mock("../authFetch", () => ({
  authFetch: (...args: unknown[]) => mockAuthFetch(...args),
}));

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  };
}

describe("uploadRagFile", () => {
  beforeEach(() => {
    mockAuthFetch.mockReset();
  });

  it("returns synchronous upload results", async () => {
    mockAuthFetch.mockResolvedValueOnce(jsonResponse({
      status: "ok",
      filename: "small.md",
      chunks_created: 2,
      elapsed_seconds: 0.5,
      warnings: [],
    }));

    const result = await uploadRagFile(new File(["content"], "small.md"));

    expect(mockAuthFetch).toHaveBeenCalledTimes(1);
    expect(mockAuthFetch).toHaveBeenCalledWith(
      "/api/rag/upload",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.status).toBe("ok");
    expect(result.chunks_created).toBe(2);
  });

  it("polls queued upload jobs until completion", async () => {
    mockAuthFetch
      .mockResolvedValueOnce(jsonResponse({
        status: "queued",
        filename: "large.csv",
        chunks_created: 0,
        elapsed_seconds: 0,
        job_id: "job-123",
      }, { status: 202 }))
      .mockResolvedValueOnce(jsonResponse({
        job_id: "job-123",
        status: "ok",
        filename: "large.csv",
        chunks_created: 282,
        elapsed_seconds: 118.2,
        warnings: [],
      }));

    const result = await uploadRagFile(
      new File(["content"], "large.csv"),
      { pollIntervalMs: 0, timeoutMs: 1000 },
    );

    expect(mockAuthFetch).toHaveBeenNthCalledWith(
      2,
      "/api/rag/upload/status/job-123",
    );
    expect(result.status).toBe("ok");
    expect(result.chunks_created).toBe(282);
  });

  it("throws when a queued upload job fails", async () => {
    mockAuthFetch
      .mockResolvedValueOnce(jsonResponse({
        status: "queued",
        filename: "large.csv",
        chunks_created: 0,
        elapsed_seconds: 0,
        job_id: "job-err",
      }, { status: 202 }))
      .mockResolvedValueOnce(jsonResponse({
        job_id: "job-err",
        status: "error",
        filename: "large.csv",
        error: "Index failed",
      }));

    await expect(uploadRagFile(
      new File(["content"], "large.csv"),
      { pollIntervalMs: 0, timeoutMs: 1000 },
    )).rejects.toThrow("Index failed");
  });
});
