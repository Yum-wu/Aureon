import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SupportWidget } from "../SupportWidget";

// Mock scrollIntoView (not available in jsdom)
Element.prototype.scrollIntoView = vi.fn();

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { returnObjects?: boolean }) => {
      if (key === "support.quickReplies" && options?.returnObjects) {
        return ["Question 1?", "Question 2?", "Question 3?", "Question 4?"];
      }
      const translations: Record<string, string> = {
        "support.title": "Aureon Support",
        "support.welcome": "Welcome! How can I help?",
        "support.online": "Online",
        "support.offline": "Offline",
        "support.placeholder": "Type your question...",
        "support.connecting": "Connecting...",
        "support.connected": "Connected and ready",
        "support.close": "Close",
        "chat.send": "Send",
      };
      return translations[key] || key;
    },
  }),
}));

// Mock useWebSocket hook — 匹配实际接口 { isConnected, send, lastMessage, connect, disconnect, connectionState }
const mockSend = vi.fn();
const mockUseWebSocket = vi.fn();

vi.mock("../../hooks/useWebSocket", () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

describe("SupportWidget", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default mock: connected, no last message
    mockUseWebSocket.mockReturnValue({
      isConnected: true,
      send: mockSend,
      lastMessage: null,
      connect: vi.fn(),
      disconnect: vi.fn(),
      connectionState: "connected",
    });
  });

  it("renders FAB button when closed", () => {
    render(<SupportWidget />);
    expect(screen.getByTestId("support-fab")).toBeInTheDocument();
  });

  it("opens panel when FAB is clicked", () => {
    render(<SupportWidget />);

    const fab = screen.getByTestId("support-fab");
    fireEvent.click(fab);

    expect(screen.getByTestId("support-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("support-fab")).not.toBeInTheDocument();
  });

  it("closes panel when close button is clicked", () => {
    render(<SupportWidget />);

    // Open panel
    fireEvent.click(screen.getByTestId("support-fab"));
    expect(screen.getByTestId("support-panel")).toBeInTheDocument();

    // Close panel
    fireEvent.click(screen.getByTestId("support-close"));
    expect(screen.queryByTestId("support-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("support-fab")).toBeInTheDocument();
  });

  it("shows connection status", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    const status = screen.getByTestId("support-status");
    expect(status).toHaveTextContent("Online");
  });

  it("shows offline status when disconnected", () => {
    mockUseWebSocket.mockReturnValue({
      isConnected: false,
      send: mockSend,
      lastMessage: null,
      connect: vi.fn(),
      disconnect: vi.fn(),
      connectionState: "disconnected",
    });

    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    const status = screen.getByTestId("support-status");
    expect(status).toHaveTextContent("Offline");
  });

  it("renders quick replies when no messages", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    expect(screen.getByTestId("quick-reply-0")).toHaveTextContent("Question 1?");
    expect(screen.getByTestId("quick-reply-1")).toHaveTextContent("Question 2?");
    expect(screen.getByTestId("quick-reply-2")).toHaveTextContent("Question 3?");
    expect(screen.getByTestId("quick-reply-3")).toHaveTextContent("Question 4?");
  });

  it("sends message via WebSocket when quick reply is clicked", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    fireEvent.click(screen.getByTestId("quick-reply-0"));

    expect(mockSend).toHaveBeenCalledWith(
      JSON.stringify({ type: "chat", content: "Question 1?", mode: "support" }),
    );
  });

  it("renders user message after sending", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    // Click quick reply to send a message
    fireEvent.click(screen.getByTestId("quick-reply-0"));

    // User message should appear in the UI
    expect(screen.getByTestId("support-message-user-0")).toHaveTextContent("Question 1?");
  });

  it("shows loading indicator after sending (streaming started)", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    // Click quick reply — this sets isStreaming=true, streamingText=''
    fireEvent.click(screen.getByTestId("quick-reply-0"));

    expect(screen.getByTestId("support-loading")).toBeInTheDocument();
  });

  it("hides quick replies after sending a message", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    // Quick replies visible initially
    expect(screen.getByTestId("quick-reply-0")).toBeInTheDocument();

    // Send a message
    fireEvent.click(screen.getByTestId("quick-reply-0"));

    // Quick replies should be hidden (messages.length > 0)
    expect(screen.queryByTestId("quick-reply-0")).not.toBeInTheDocument();
  });

  it("sends message on Enter key", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    const input = screen.getByTestId("support-input");
    fireEvent.change(input, { target: { value: "Test question" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    expect(mockSend).toHaveBeenCalledWith(
      JSON.stringify({ type: "chat", content: "Test question", mode: "support" }),
    );
  });

  it("disables send button when input is empty", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    const sendButton = screen.getByTestId("support-send");
    expect(sendButton).toBeDisabled();
  });

  it("enables send button when input has text and connected", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));

    const input = screen.getByTestId("support-input");
    fireEvent.change(input, { target: { value: "Test" } });

    const sendButton = screen.getByTestId("support-send");
    expect(sendButton).not.toBeDisabled();
  });
});
