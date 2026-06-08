import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VoiceButton } from '../VoiceButton';

vi.mock('../../hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: vi.fn(),
}));

import { useSpeechRecognition } from '../../hooks/useSpeechRecognition';
const mockUseSpeechRecognition = useSpeechRecognition as unknown as ReturnType<typeof vi.fn> & { mockReturnValue: (v: any) => void };

describe('VoiceButton', () => {
  const defaultHookReturn = {
    isListening: false,
    transcript: '',
    interimTranscript: '',
    isSupported: true,
    error: null as string | null,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    resetTranscript: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSpeechRecognition.mockReturnValue(defaultHookReturn);
  });

  it('should render microphone button', () => {
    render(<VoiceButton onTranscript={vi.fn()} />);
    expect(screen.getByTestId('voice-button')).toBeTruthy();
  });

  it('should not render when speech recognition is not supported', () => {
    mockUseSpeechRecognition.mockReturnValue({
      ...defaultHookReturn,
      isSupported: false,
    });
    const { container } = render(<VoiceButton onTranscript={vi.fn()} />);
    expect(container.innerHTML).toBe('');
  });

  it('should start listening on click', () => {
    render(<VoiceButton onTranscript={vi.fn()} lang="nl-NL" />);
    fireEvent.click(screen.getByTestId('voice-button'));
    expect(defaultHookReturn.startListening).toHaveBeenCalledWith('nl-NL');
  });

  it('should stop and call onTranscript on second click', () => {
    const onTranscript = vi.fn();
    mockUseSpeechRecognition.mockReturnValue({
      ...defaultHookReturn,
      isListening: true,
      transcript: 'hello world',
    });
    render(<VoiceButton onTranscript={onTranscript} />);
    fireEvent.click(screen.getByTestId('voice-button'));
    expect(defaultHookReturn.stopListening).toHaveBeenCalled();
    expect(onTranscript).toHaveBeenCalledWith('hello world');
  });

  it('should be disabled when disabled prop is true', () => {
    render(<VoiceButton onTranscript={vi.fn()} disabled />);
    const button = screen.getByTestId('voice-button');
    expect(button).toBeDisabled();
  });
});
