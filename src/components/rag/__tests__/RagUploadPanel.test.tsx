import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RagUploadPanel } from "../RagUploadPanel";
import { authFetch } from "../../../services/authFetch";

vi.mock("../../../services/authFetch", () => ({
  authFetch: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (key === "rag.upload.success") return `uploaded ${params?.filename} ${params?.chunks}`;
      return key;
    },
  }),
}));

const mockAuthFetch = vi.mocked(authFetch);

describe("RagUploadPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ files: [] }),
    } as Response);
  });

  it("accepts all backend-supported upload formats", async () => {
    render(<RagUploadPanel open />);
    await waitFor(() => expect(mockAuthFetch).toHaveBeenCalledTimes(1));

    const input = document.querySelector("#rag-upload-input");

    expect(mockAuthFetch).toHaveBeenCalledWith("/api/rag/uploads");
    expect(input).toHaveAttribute("accept", ".md,.txt,.pdf,.docx,.xlsx,.csv,.pptx");
  });

  it("uploads csv and pptx instead of rejecting them in the client", async () => {
    mockAuthFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ files: [] }) } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: "ok", chunks_created: 2, warnings: [] }),
      } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ files: [] }) } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: "ok", chunks_created: 3, warnings: [] }),
      } as Response);

    render(<RagUploadPanel open />);

    const input = document.querySelector("#rag-upload-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["a,b\n1,2"], "data.csv")] } });
    await waitFor(() => expect(screen.getByText(/uploaded data\.csv 2/)).toBeInTheDocument());
    expect(mockAuthFetch).toHaveBeenNthCalledWith(
      2,
      "/api/rag/upload",
      expect.objectContaining({ method: "POST" }),
    );

    fireEvent.change(input, { target: { files: [new File(["pptx"], "deck.pptx")] } });
    await waitFor(() => expect(screen.getByText(/uploaded deck\.pptx 3/)).toBeInTheDocument());
  });

  it("rejects unsupported extensions before upload", async () => {
    render(<RagUploadPanel open />);

    const input = document.querySelector("#rag-upload-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["bad"], "bad.exe")] } });

    expect(await screen.findByText(/rag\.upload\.badFormat/)).toBeInTheDocument();
    expect(mockAuthFetch).toHaveBeenCalledTimes(1);
  });

  it("shows backend warnings after a successful upload", async () => {
    mockAuthFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ files: [] }) } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          status: "ok",
          chunks_created: 1,
          warnings: ["PDF contains little or no extractable text; it may be scanned or image-based."],
        }),
      } as Response);

    render(<RagUploadPanel open />);

    const input = document.querySelector("#rag-upload-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["pdf"], "scan.pdf")] } });

    expect(
      await screen.findByText(/PDF contains little or no extractable text/),
    ).toBeInTheDocument();
  });
});
