import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../components/SupportWidget';

const STORAGE_KEY = 'aureon_support_messages';
const MAX_MESSAGES = 50;

export function useSupportMessages(
  messages: ChatMessage[],
  setMessages: (fn: (prev: ChatMessage[]) => ChatMessage[]) => void,
  isStreaming: boolean
) {
  const loaded = useRef(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as ChatMessage[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(() => parsed);
        }
      }
    } catch { /* ignore corrupt data */ }
    loaded.current = true;
  }, [setMessages]);

  useEffect(() => {
    if (!loaded.current) return;
    if (isStreaming) return;
    const timer = setTimeout(() => {
      try {
        const toSave = messages.slice(-MAX_MESSAGES);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
      } catch { /* storage full */ }
    }, 500);
    return () => clearTimeout(timer);
  }, [messages, isStreaming]);
}
