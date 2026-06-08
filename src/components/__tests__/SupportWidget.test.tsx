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

// Mock useWebSocket hook
const mockSendMessage = vi.fn();
const mockUseWebSocket = vi.fn();

vi.mock("../../hooks/useWebSocket", () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

describe("SupportWidget", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default mock: connected with no messages
    mockUseWebSocket.mockReturnValue({
      isConnected: true,
      messages: [],
      isStreaming: false,
      streamingText: "",
      error: null,
      sendMessage: mockSendMessage,
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
      messages: [],
      isStreaming: false,
      streamingText: "",
      error: null,
      sendMessage: mockSendMessage,
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

  it("sends message when quick reply is clicked", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));
    
    fireEvent.click(screen.getByTestId("quick-reply-0"));
    
    expect(mockSendMessage).toHaveBeenCalledWith("Question 1?", { mode: "support" });
  });

  it("renders user and assistant messages", () => {
    mockUseWebSocket.mockReturnValue({
      isConnected: true,
      messages: [
        { role: "user", content: "Hello", timestamp: new Date() },
        { role: "assistant", content: "Hi there!", timestamp: new Date() },
      ],
      isStreaming: false,
      streamingText: "",
      error: null,
      sendMessage: mockSendMessage,
    });
    
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));
    
    expect(screen.getByTestId("support-message-user-0")).toHaveTextContent("Hello");
    expect(screen.getByTestId("support-message-assistant-1")).toHaveTextContent("Hi there!");
  });

  it("shows streaming text when streaming", () => {
    mockUseWebSocket.mockReturnValue({
      isConnected: true,
      messages: [],
      isStreaming: true,
      streamingText: "Streaming response...",
      error: null,
      sendMessage: mockSendMessage,
    });
    
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));
    
    expect(screen.getByTestId("support-streaming")).toHaveTextContent("Streaming response...");
  });

  it("shows loading indicator when streaming but no text", () => {
    mockUseWebSocket.mockReturnValue({
      isConnected: true,
      messages: [],
      isStreaming: true,
      streamingText: "",
      error: null,
      sendMessage: mockSendMessage,
    });
    
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));
    
    expect(screen.getByTestId("support-loading")).toBeInTheDocument();
  });

  it("shows error when present", () => {
    mockUseWebSocket.mockReturnValue({
      isConnected: true,
      messages: [],
      isStreaming: false,
      streamingText: "",
      error: "Connection failed",
      sendMessage: mockSendMessage,
    });
    
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));
    
    expect(screen.getByTestId("support-error")).toHaveTextContent("Connection failed");
  });

  it("sends message on Enter key", () => {
    render(<SupportWidget />);
    fireEvent.click(screen.getByTestId("support-fab"));
    
    const input = screen.getByTestId("support-input");
    fireEvent.change(input, { target: { value: "Test question" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    
    expect(mockSendMessage).toHaveBeenCalledWith("Test question", { mode: "support" });
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
