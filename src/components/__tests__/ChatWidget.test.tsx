import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatWidget } from "../ChatWidget";

// Mock scrollIntoView (not available in jsdom)
Element.prototype.scrollIntoView = vi.fn();

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) => {
      const translations: Record<string, string> = {
        "chat.title": "Chat",
        "chat.welcome": "Welcome to Aureon",
        "chat.welcome_subtitle": "Ask me anything",
        "chat.placeholder": "Type a message...",
        "chat.send": "Send",
        "chat.ready": "Ready",
        "chat.streaming": "Streaming...",
        "chat.processing": "Processing...",
        "chat.sources": "Sources",
        "chat.emptyTitle": "Get started",
        "chat.emptyHint": "Try asking a question",
        "chat.suggestions.summarize_latest": "Summarize latest",
        "chat.suggestions.key_risks": "Key risks",
        "chat.suggestions.summarize_doc": `Summarize ${options?.title ?? ""}`,
        "chat.suggestions.about_doc": `About ${options?.title ?? ""}`,
      };
      return translations[key] || key;
    },
  }),
}));

// Mock useChatStore
const mockSendMessage = vi.fn();
const mockUseChatStore = vi.fn();

vi.mock("../../stores/useChatStore", () => ({
  useChatStore: (selector: (state: Record<string, unknown>) => unknown) =>
    mockUseChatStore(selector),
}));

// Mock useDocuments
const mockUseDocuments = vi.fn();
vi.mock("../../hooks/useDocumentsQuery", () => ({
  useDocuments: () => mockUseDocuments(),
}));

// Mock VoiceButton (renders nothing to simplify tests)
vi.mock("../VoiceButton", () => ({
  VoiceButton: () => null,
}));

// Mock lucide-react icons
vi.mock("lucide-react", () => ({
  BookOpen: () => null,
  AlertTriangle: () => null,
}));

describe("ChatWidget", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDocuments.mockReturnValue([]);

    // Default: empty messages, not loading, no error
    mockUseChatStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
      const state = {
        messages: [],
        isLoading: false,
        error: null,
        sendMessage: mockSendMessage,
      };
      return selector(state);
    });
  });

  it("renders empty state with welcome message", () => {
    render(<ChatWidget />);
    expect(screen.getByTestId("chat-widget")).toBeInTheDocument();
    expect(screen.getByText("Welcome to Aureon")).toBeInTheDocument();
    expect(screen.getByText("Ask me anything")).toBeInTheDocument();
  });

  it("renders suggestion buttons in empty state", () => {
    render(<ChatWidget />);
    expect(screen.getByText("Summarize latest")).toBeInTheDocument();
    expect(screen.getByText("Key risks")).toBeInTheDocument();
    expect(screen.getByText("Get started")).toBeInTheDocument();
    expect(screen.getByText("Try asking a question")).toBeInTheDocument();
  });

  it("renders messages list", () => {
    mockUseChatStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
      const state = {
        messages: [
          { id: "1", role: "user", content: "Hello", timestamp: 1 },
          { id: "2", role: "assistant", content: "Hi there!", timestamp: 2 },
        ],
        isLoading: false,
        error: null,
        sendMessage: mockSendMessage,
      };
      return selector(state);
    });

    render(<ChatWidget />);
    expect(screen.getByTestId("message-user-0")).toHaveTextContent("Hello");
    expect(screen.getByTestId("message-assistant-1")).toHaveTextContent("Hi there!");
  });

  it("hides welcome when messages exist", () => {
    mockUseChatStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
      const state = {
        messages: [{ id: "1", role: "user", content: "Hello", timestamp: 1 }],
        isLoading: false,
        error: null,
        sendMessage: mockSendMessage,
      };
      return selector(state);
    });

    render(<ChatWidget />);
    expect(screen.queryByText("Welcome to Aureon")).not.toBeInTheDocument();
  });

  it("handles input submission via button click", () => {
    render(<ChatWidget />);

    const input = screen.getByTestId("chat-input");
    fireEvent.change(input, { target: { value: "Test message" } });

    const sendButton = screen.getByTestId("send-button");
    expect(sendButton).not.toBeDisabled();

    fireEvent.click(sendButton);
    expect(mockSendMessage).toHaveBeenCalledWith("Test message");
  });

  it("handles input submission via Enter key", () => {
    render(<ChatWidget />);

    const input = screen.getByTestId("chat-input");
    fireEvent.change(input, { target: { value: "Hello via Enter" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    expect(mockSendMessage).toHaveBeenCalledWith("Hello via Enter");
  });

  it("does not submit on Shift+Enter", () => {
    render(<ChatWidget />);

    const input = screen.getByTestId("chat-input");
    fireEvent.change(input, { target: { value: "Line break" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });

    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it("disables send button when input is empty", () => {
    render(<ChatWidget />);
    const sendButton = screen.getByTestId("send-button");
    expect(sendButton).toBeDisabled();
  });

  it("shows loading/streaming state", () => {
    mockUseChatStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
      const state = {
        messages: [],
        isLoading: true,
        error: null,
        sendMessage: mockSendMessage,
      };
      return selector(state);
    });

    render(<ChatWidget />);
    expect(screen.getByTestId("streaming-message")).toBeInTheDocument();
    expect(screen.getByTestId("connection-status")).toHaveTextContent("Streaming...");
  });

  it("shows error when present", () => {
    mockUseChatStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
      const state = {
        messages: [],
        isLoading: false,
        error: "Something went wrong",
        sendMessage: mockSendMessage,
      };
      return selector(state);
    });

    render(<ChatWidget />);
    expect(screen.getByTestId("chat-error")).toHaveTextContent("Something went wrong");
  });

  it("renders source citations for assistant messages", () => {
    mockUseChatStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
      const state = {
        messages: [
          {
            id: "1",
            role: "assistant",
            content: "Answer with sources",
            timestamp: 1,
            sources: [
              { title: "Article A", slug: "a", score: 0.95 },
              { title: "Article B", slug: "b", score: 0.82 },
            ],
          },
        ],
        isLoading: false,
        error: null,
        sendMessage: mockSendMessage,
      };
      return selector(state);
    });

    render(<ChatWidget />);
    expect(screen.getByText("Article A")).toBeInTheDocument();
    expect(screen.getByText("(95%)")).toBeInTheDocument();
    expect(screen.getByText("Article B")).toBeInTheDocument();
    expect(screen.getByText("(82%)")).toBeInTheDocument();
  });

  it("sends suggestion text when suggestion button is clicked", () => {
    render(<ChatWidget />);
    fireEvent.click(screen.getByText("Summarize latest"));
    expect(mockSendMessage).toHaveBeenCalledWith("Summarize latest");
  });
});
