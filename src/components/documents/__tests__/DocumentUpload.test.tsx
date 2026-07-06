import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DocumentUpload } from "../DocumentUpload";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("DocumentUpload", () => {
  const mockOnUploadSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders upload area", () => {
    render(<DocumentUpload onUploadSuccess={mockOnUploadSuccess} />);

    // Should render the drop zone
    expect(screen.getByTestId("upload-dropzone")).toBeInTheDocument();
    // Should show upload prompt text (i18n key as-is)
    expect(screen.getByText("documents.upload.drop_text")).toBeInTheDocument();
    // Should show file input
    expect(screen.getByTestId("upload-file-input")).toBeInTheDocument();
  });

  it("accepts csv and pptx files", () => {
    render(<DocumentUpload onUploadSuccess={mockOnUploadSuccess} />);

    const input = screen.getByTestId("upload-file-input");

    expect(input).toHaveAttribute("accept", ".md,.txt,.pdf,.docx,.xlsx,.csv,.pptx");
  });

  it("handles file selection", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "ok",
        filename: "test.md",
        documents_indexed: 1,
        chunks_created: 3,
        elapsed_seconds: 0.5,
      }),
    });

    render(<DocumentUpload onUploadSuccess={mockOnUploadSuccess} />);

    const file = new File(["# Test content"], "test.md", {
      type: "text/markdown",
    });
    const input = screen.getByTestId("upload-file-input");

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/rag/upload",
        expect.objectContaining({
          method: "POST",
          body: expect.any(FormData),
        })
      );
    });

    await waitFor(() => {
      expect(mockOnUploadSuccess).toHaveBeenCalled();
    });
  });

  it("shows upload progress", async () => {
    // Simulate a slow upload with delayed resolution
    let resolveUpload: (v: Response) => void;
    const uploadPromise = new Promise<Response>((resolve) => {
      resolveUpload = resolve;
    });
    mockFetch.mockReturnValueOnce(uploadPromise);

    render(<DocumentUpload onUploadSuccess={mockOnUploadSuccess} />);

    const file = new File(["content"], "progress-test.txt", {
      type: "text/plain",
    });
    const input = screen.getByTestId("upload-file-input");

    fireEvent.change(input, { target: { files: [file] } });

    // Should show uploading state
    await waitFor(() => {
      expect(screen.getByTestId("upload-progress")).toBeInTheDocument();
    });

    // Resolve the upload
    resolveUpload!({
      ok: true,
      json: async () => ({
        status: "ok",
        filename: "progress-test.txt",
        chunks_created: 1,
        elapsed_seconds: 0.2,
      }),
    } as Response);

    // Should show success state
    await waitFor(() => {
      expect(screen.getByTestId("upload-success")).toBeInTheDocument();
    });
  });
});
