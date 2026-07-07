import { authFetch } from "./authFetch";

export interface RagUploadResult {
  status: string;
  filename: string;
  chunks_created: number;
  elapsed_seconds: number;
  warnings?: string[];
  job_id?: string;
  error?: string | null;
}

interface PollOptions {
  pollIntervalMs?: number;
  timeoutMs?: number;
  uploadUrl?: string;
}

const DEFAULT_POLL_INTERVAL_MS = 2000;
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitForRagUploadJob(
  jobId: string,
  options: PollOptions = {},
): Promise<RagUploadResult> {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const uploadUrl = options.uploadUrl ?? "/api/rag/upload";
    const statusUrl = `${uploadUrl.replace(/\/upload$/, "/upload/status")}/${encodeURIComponent(jobId)}`;
    const res = await authFetch(statusUrl);
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(data?.detail || `HTTP ${res.status}`);
    }
    if (data?.status === "ok") {
      return data;
    }
    if (data?.status === "error") {
      throw new Error(data.error || "Upload indexing failed");
    }
    await sleep(pollIntervalMs);
  }

  throw new Error(`Upload indexing timed out: ${jobId}`);
}

export async function uploadRagFile(
  file: File,
  options: PollOptions = {},
): Promise<RagUploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  const uploadUrl = options.uploadUrl ?? "/api/rag/upload";
  const res = await authFetch(uploadUrl, {
    method: "POST",
    body: formData,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || `HTTP ${res.status}`);
  }

  if (data?.job_id && ["queued", "processing"].includes(data.status)) {
    return waitForRagUploadJob(data.job_id, { ...options, uploadUrl });
  }
  if (data?.status === "error") {
    throw new Error(data.error || "Upload failed");
  }
  return data;
}
