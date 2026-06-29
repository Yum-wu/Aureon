/** 聊天状态 Store */

import { create } from "zustand";
import i18n from "i18next";
import type { ChatState } from "./types";
import type { Message } from "../types/message";
import type { SSEEvent } from "../services/api";
import { streamEnhancedChat } from "../services/api";
import {
  loadMessages,
  saveMessages,
  clearMessages as clearStorage,
} from "../services/storage";

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

const SESSION_KEY = "search_session_id";



export const useChatStore = create<ChatState>((set, get) => {
  const SSE_FLUSH_INTERVAL = 60;
  let _textBuffer = "";
  let _flushTimer: ReturnType<typeof setTimeout> | null = null;
  let _currentAssistantId = "";

  const _flushBuffer = () => {
    if (_flushTimer) {
      clearTimeout(_flushTimer);
      _flushTimer = null;
    }
    if (!_textBuffer) return;
    const text = _textBuffer;
    _textBuffer = "";
    const aid = _currentAssistantId;
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant" && last.id === aid) {
        messages[messages.length - 1] = { ...last, content: last.content + text };
      }
      return { messages };
    });
  };

  const _scheduleFlush = () => {
    if (_flushTimer) return;
    _flushTimer = setTimeout(() => {
      _flushTimer = null;
      _flushBuffer();
    }, SSE_FLUSH_INTERVAL);
  };

  const _appendText = (chunk: string) => {
    _textBuffer += chunk;
    _scheduleFlush();
  };

  let abortController: AbortController | null = null;
  let sending = false;
  let sessionId: string | null = localStorage.getItem(SESSION_KEY);

  const handleEvent = (event: SSEEvent, assistantId: string) => {
    switch (event.type) {
      case "session": {
        const sid = (event.content as { session_id: string }).session_id;
        sessionId = sid;
        localStorage.setItem(SESSION_KEY, sid);
        break;
      }
      case "text": {
        const chunk = event.content as string;
        _appendText(chunk);
        break;
      }
      case "tool_start":
      case "tool_end": {
        _flushBuffer();
        const info = event.content as Record<string, unknown>;
        const toolName = String(info.tool ?? "");
        set((state) => {
          const messages = [...state.messages];
          const last = messages[messages.length - 1];
          if (last && last.role === "assistant" && last.id === assistantId) {
            let suffix: string;
            if (event.type === "tool_start") {
              suffix = `\n\n> ${i18n.t("chat.calling")} ${toolName}...`;
            } else {
              const result = String(info.result ?? "");
              const preview = result.length > 100
                ? result.slice(0, 100) + "..."
                : result;
              suffix = `\n\n> ${toolName} ${i18n.t("chat.completed")}: ${preview}`;
            }
            messages[messages.length - 1] = {
              ...last,
              content: last.content + suffix,
            };
          }
          return { messages };
        });
        break;
      }
      case "sources": {
        _flushBuffer();
        const srcList = event.sources ?? (event.content as Array<{ title: string; slug: string; score?: number }>);
        if (srcList) {
          set((state) => {
            const messages = [...state.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "assistant" && last.id === assistantId) {
              messages[messages.length - 1] = { ...last, sources: srcList };
            }
            return { messages };
          });
        }
        break;
      }
      case "intent": {
        _flushBuffer();
        const intentData = event.content as { intent: string; confidence: number };
        set((state) => {
          const messages = [...state.messages];
          const last = messages[messages.length - 1];
          if (last && last.role === "assistant" && last.id === assistantId) {
            messages[messages.length - 1] = { ...last, intent: intentData.intent };
          }
          return { messages };
        });
        break;
      }
      case "error": {
        _flushBuffer();
        const err = event.content as { message: string };
        set({ error: err.message });
        break;
      }
    }
  };

  return {
    messages: loadMessages(),
    isLoading: false,
    error: null,

    sendMessage: async (content: string) => {
      if (!content.trim() || sending) return;

      sending = true;
      set({ error: null });

      const userMessage: Message = {
        id: generateId(),
        role: "user",
        content: content.trim(),
        timestamp: Date.now(),
      };

      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: "",
        timestamp: Date.now(),
      };

      _currentAssistantId = assistantMessage.id;
      set((state) => ({
        messages: [...state.messages, userMessage, assistantMessage],
        isLoading: true,
      }));

      abortController = new AbortController();

      await streamEnhancedChat({
        message: userMessage.content,
        sessionId,
        onEvent: (event) => handleEvent(event, assistantMessage.id),
        onError: (errMsg) => {
          set({ error: errMsg });
          set((state) => {
            const messages = [...state.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "assistant" && !last.content) {
              messages[messages.length - 1] = {
                ...last,
                content: `Error: ${errMsg}`,
              };
            }
            return { messages };
          });
        },
        signal: abortController.signal,
      });

      _flushBuffer();

      // 流结束：保存消息
      const { messages } = get();
      saveMessages(messages);

      set({ isLoading: false });
      abortController = null;
      sending = false;
    },

    clearChat: () => {
      _flushBuffer();
      abortController?.abort();
      clearStorage();
      set({ messages: [], isLoading: false, error: null });
      sending = false;
    },

    stopGeneration: () => {
      _flushBuffer();
      abortController?.abort();
      set((state) => {
        const messages = [...state.messages];
        const last = messages[messages.length - 1];
        if (last && last.role === "assistant") {
          if (!last.content) {
            messages.pop();
          } else {
            messages[messages.length - 1] = {
              ...last,
              content: last.content + `\n\n*[${i18n.t("chat.stopped")}]*`,
            };
          }
        }
        return { messages, isLoading: false };
      });
      sending = false;
    },

    clearError: () => {
      set({ error: null });
    },
  };
});
