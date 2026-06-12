import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useSpeechRecognition } from '../useSpeechRecognition';

const mockStart = vi.fn();
const mockStop = vi.fn();
const mockAbort = vi.fn();

class MockSpeechRecognition {
  continuous = false;
  interimResults = false;
  lang = '';
  start = mockStart;
  stop = mockStop;
  abort = mockAbort;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onresult: any = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onerror: any = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onend: any = null;
}

describe('useSpeechRecognition', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).SpeechRecognition = MockSpeechRecognition;
  });

  afterEach(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).SpeechRecognition;
  });

  it('should report isSupported as true when SpeechRecognition exists', () => {
    const { result } = renderHook(() => useSpeechRecognition());
    expect(result.current.isSupported).toBe(true);
  });

  it('should report isSupported as false when SpeechRecognition is missing', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).SpeechRecognition;
    const { result } = renderHook(() => useSpeechRecognition());
    expect(result.current.isSupported).toBe(false);
  });

  it('should start listening with correct language', async () => {
    const { result } = renderHook(() => useSpeechRecognition());
    await act(async () => {
      result.current.startListening('nl-NL');
    });
    await waitFor(() => {
      expect(result.current.isListening).toBe(true);
    });
    expect(mockStart).toHaveBeenCalled();
  });

  it('should stop listening', async () => {
    const { result } = renderHook(() => useSpeechRecognition());
    await act(async () => {
      result.current.startListening();
    });
    await act(async () => {
      result.current.stopListening();
    });
    await waitFor(() => {
      expect(result.current.isListening).toBe(false);
    });
  });

  it('should reset transcript', () => {
    const { result } = renderHook(() => useSpeechRecognition());
    result.current.resetTranscript();
    expect(result.current.transcript).toBe('');
    expect(result.current.interimTranscript).toBe('');
  });

  it('should set error when starting without support', async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).SpeechRecognition;
    const { result } = renderHook(() => useSpeechRecognition());
    await act(async () => {
      result.current.startListening();
    });
    await waitFor(() => {
      expect(result.current.error).toBe('Speech recognition is not supported in this browser');
    });
  });
});
