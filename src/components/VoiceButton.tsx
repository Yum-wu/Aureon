/**
 * Microphone button for voice input.
 * Shows recording state with animated indicator.
 */

import { useSpeechRecognition } from '../hooks/useSpeechRecognition';

interface VoiceButtonProps {
  onTranscript: (text: string) => void;
  lang?: string;
  className?: string;
  disabled?: boolean;
}

export function VoiceButton({
  onTranscript,
  lang = 'en-US',
  className = '',
  disabled = false,
}: VoiceButtonProps) {
  const {
    isListening,
    transcript,
    interimTranscript,
    isSupported,
    error,
    startListening,
    stopListening,
    resetTranscript,
  } = useSpeechRecognition();

  const handleClick = () => {
    if (isListening) {
      stopListening();
      if (transcript.trim()) {
        onTranscript(transcript.trim());
      }
      resetTranscript();
    } else {
      startListening(lang);
    }
  };

  if (!isSupported) {
    return null;
  }

  return (
    <div className={`voice-button-container relative ${className}`}>
      <button
        onClick={handleClick}
        disabled={disabled}
        className={`relative p-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 ${
          isListening
            ? 'bg-red-500 hover:bg-red-600 text-white focus:ring-red-500 animate-pulse'
            : 'bg-gray-100 hover:bg-gray-200 text-gray-600 focus:ring-gray-400'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        title={isListening ? 'Stop recording' : 'Start voice input'}
        data-testid="voice-button"
        aria-label={isListening ? 'Stop recording' : 'Start voice input'}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="w-5 h-5"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 18.75a6 6 0 0 0 6-6v-1.5m-6 7.5a6 6 0 0 1-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 0 1-3-3V4.5a3 3 0 1 1 6 0v8.25a3 3 0 0 1-3 3Z"
          />
        </svg>
        {isListening && (
          <span className="absolute top-0 right-0 w-2.5 h-2.5 bg-white rounded-full animate-ping" />
        )}
      </button>

      {isListening && interimTranscript && (
        <p
          className="absolute bottom-full left-0 mb-1 text-xs text-gray-400 whitespace-nowrap"
          data-testid="interim-transcript"
        >
          {interimTranscript}...
        </p>
      )}

      {error && (
        <p className="text-xs text-red-500 mt-1" data-testid="voice-error">
          {error}
        </p>
      )}
    </div>
  );
}
