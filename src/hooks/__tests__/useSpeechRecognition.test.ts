import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
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
  onresult: any = null;
  onerror: any = null;
  onend: any = null;
}

describe('useSpeechRecognition', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window as any).SpeechRecognition = MockSpeechRecognition;
  });

  afterEach(() => {
    delete (window as any).SpeechRecognition;
  });

  it('should report isSupported as true when SpeechRecognition exists', () => {
    const { result } = renderHook(() => useSpeechRecognition());
    expect(result.current.isSupported).toBe(true);
  });

  it('should report isSupported as false when SpeechRecognition is missing', () => {
    delete (window as any).SpeechRecognition;
    const { result } = renderHook(() => useSpeechRecognition());
    expect(result.current.isSupported).toBe(false);
  });

  it('should start listening with correct language', () => {
    const { result } = renderHook(() => useSpeechRecognition());
    act(() => {
      result.current.startListening('nl-NL');
    });
    expect(result.current.isListening).toBe(true);
    expect(mockStart).toHaveBeenCalled();
  });

  it('should stop listening', () => {
    const { result } = renderHook(() => useSpeechRecognition());
    act(() => {
      result.current.startListening();
    });
    act(() => {
      result.current.stopListening();
    });
    expect(result.current.isListening).toBe(false);
  });

  it('should reset transcript', () => {
    const { result } = renderHook(() => useSpeechRecognition());
    act(() => {
      result.current.resetTranscript();
    });
    expect(result.current.transcript).toBe('');
    expect(result.current.interimTranscript).toBe('');
  });

  it('should set error when starting without support', () => {
    delete (window as any).SpeechRecognition;
    const { result } = renderHook(() => useSpeechRecognition());
    act(() => {
      result.current.startListening();
    });
    expect(result.current.error).toBe('Speech recognition is not supported in this browser');
  });
});
