import { useState } from 'react';

interface MessageActionsProps {
  role: 'user' | 'assistant';
  content: string;
  onRegenerate?: () => void;
  t: (key: string) => string;
}

export function MessageActions({ role, content, onRegenerate, t }: MessageActionsProps) {
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard not available */ }
  };

  return (
    <div className="flex items-center gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button onClick={handleCopy} className="p-1 rounded hover:bg-[var(--bg-tertiary)]" title={t('support.copy')} data-testid="msg-copy">
        {copied ? '✓' : (
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
        )}
      </button>
      {role === 'assistant' && (
        <>
          <button onClick={() => setFeedback(feedback === 'up' ? null : 'up')} className={`p-1 rounded hover:bg-[var(--bg-tertiary)] ${feedback === 'up' ? 'text-green-400' : ''}`} title={t('support.feedback_up')} data-testid="msg-feedback-up">
            <svg className="w-3.5 h-3.5" fill={feedback === 'up' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" /></svg>
          </button>
          <button onClick={() => setFeedback(feedback === 'down' ? null : 'down')} className={`p-1 rounded hover:bg-[var(--bg-tertiary)] ${feedback === 'down' ? 'text-red-400' : ''}`} title={t('support.feedback_down')} data-testid="msg-feedback-down">
            <svg className="w-3.5 h-3.5" fill={feedback === 'down' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018c.163 0 .327.02.486.06L17 3m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V3m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" /></svg>
          </button>
          {onRegenerate && (
            <button onClick={onRegenerate} className="p-1 rounded hover:bg-[var(--bg-tertiary)]" title={t('support.regenerate')} data-testid="msg-regenerate">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            </button>
          )}
        </>
      )}
    </div>
  );
}
