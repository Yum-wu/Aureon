import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useChatStore } from '../useChatStore';

// Mock dependencies that run in browser environment
vi.mock('../../services/api', () => ({
  streamEnhancedChat: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../services/storage', () => ({
  loadMessages: vi.fn().mockReturnValue([]),
  saveMessages: vi.fn(),
  clearMessages: vi.fn(),
}));

vi.mock('i18next', () => ({
  default: { t: (key: string) => key },
}));

describe('useChatStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useChatStore.setState({
      messages: [],
      isLoading: false,
      error: null,
    });
  });

  it('should have empty initial messages', () => {
    const { messages } = useChatStore.getState();
    expect(messages).toEqual([]);
  });

  it('should have isLoading false by default', () => {
    const { isLoading } = useChatStore.getState();
    expect(isLoading).toBe(false);
  });

  it('should have error null by default', () => {
    const { error } = useChatStore.getState();
    expect(error).toBeNull();
  });

  it('should clear chat and reset state', () => {
    // Set some messages first
    useChatStore.setState({
      messages: [
        { id: '1', role: 'user', content: 'hello', timestamp: Date.now() },
        { id: '2', role: 'assistant', content: 'hi', timestamp: Date.now() },
      ],
      isLoading: true,
      error: 'some error',
    });

    const { clearChat } = useChatStore.getState();
    clearChat();

    const state = useChatStore.getState();
    expect(state.messages).toEqual([]);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('should clear error', () => {
    useChatStore.setState({ error: 'some error' });

    const { clearError } = useChatStore.getState();
    clearError();

    expect(useChatStore.getState().error).toBeNull();
  });

  it('should not send empty message', async () => {
    const { sendMessage } = useChatStore.getState();
    await sendMessage('');

    // Messages should remain empty
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it('should not send whitespace-only message', async () => {
    const { sendMessage } = useChatStore.getState();
    await sendMessage('   ');

    expect(useChatStore.getState().messages).toEqual([]);
  });

  it('should stop generation and clean up empty assistant message', () => {
    // Simulate a streaming state with empty assistant message
    useChatStore.setState({
      messages: [
        { id: '1', role: 'user', content: 'hello', timestamp: Date.now() },
        { id: '2', role: 'assistant', content: '', timestamp: Date.now() },
      ],
      isLoading: true,
    });

    const { stopGeneration } = useChatStore.getState();
    stopGeneration();

    const state = useChatStore.getState();
    // Empty assistant message should be removed
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].role).toBe('user');
    expect(state.isLoading).toBe(false);
  });

  it('should append stop marker to non-empty assistant message on stop', () => {
    useChatStore.setState({
      messages: [
        { id: '1', role: 'user', content: 'hello', timestamp: Date.now() },
        { id: '2', role: 'assistant', content: 'partial', timestamp: Date.now() },
      ],
      isLoading: true,
    });

    const { stopGeneration } = useChatStore.getState();
    stopGeneration();

    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[1].content).toContain('partial');
    expect(state.isLoading).toBe(false);
  });

  it('should expose sendMessage function', () => {
    const state = useChatStore.getState();
    expect(typeof state.sendMessage).toBe('function');
  });

  it('should expose clearChat function', () => {
    const state = useChatStore.getState();
    expect(typeof state.clearChat).toBe('function');
  });

  it('should expose stopGeneration function', () => {
    const state = useChatStore.getState();
    expect(typeof state.stopGeneration).toBe('function');
  });

  it('should expose clearError function', () => {
    const state = useChatStore.getState();
    expect(typeof state.clearError).toBe('function');
  });
});
