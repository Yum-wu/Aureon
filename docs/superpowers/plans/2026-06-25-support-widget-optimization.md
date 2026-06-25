# Support Widget Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 8 feature additions to the floating support widget: message toolbar, source citations, conversation persistence, proactive greeting, improved typing indicator, dynamic quick replies, offline message form, unread badge.

**Architecture:** All frontend changes in `SupportWidget.tsx` + 4 new hooks + 2 shared components + i18n keys. Backend adds 1 new endpoint. Tests updated inline.

**Tech Stack:** React 19 + TypeScript, Zustand (indirect), react-i18next, WebSocket, localStorage, FastAPI + SQLite (backend).

---

### Task 1: Add i18n keys for all new features

**Files:**
- Modify: `src/i18n/en.json`
- Modify: `src/i18n/zh.json`

- [ ] **Add English keys**

Insert into `support` section of `src/i18n/en.json`:
```json
{
  "support": {
    "copy": "Copy",
    "copy_success": "Copied!",
    "regenerate": "Regenerate",
    "feedback_up": "Helpful",
    "feedback_down": "Not helpful",
    "feedback_thanks": "Thanks for your feedback!",
    "sources": "Sources",
    "sources_toggle": "Show more",
    "greeting": "Hi! Need help?",
    "typing": "is typing",
    "offline_title": "Leave a message",
    "offline_name": "Your name",
    "offline_email": "Your email",
    "offline_message": "How can we help?",
    "offline_submit": "Send message",
    "offline_success": "Thank you! We'll get back to you soon.",
    "offline_error": "Failed to send. Please try again.",
    "qr_search_tips": "How to search more accurately?",
    "qr_search_filters": "What filters are supported?",
    "qr_upload_doc": "How to upload documents?",
    "qr_file_formats": "What file formats are supported?",
    "qr_dashboard_metrics": "What do dashboard metrics mean?",
    "qr_analytics_frequency": "How often is analytics data updated?",
    "qr_admin_permissions": "How to manage user permissions?",
    "qr_cost_calculation": "How is cost calculated?"
  }
}
```

- [ ] **Add Chinese keys**

Insert into `support` section of `src/i18n/zh.json`:
```json
{
  "support": {
    "copy": "复制",
    "copy_success": "已复制！",
    "regenerate": "重新生成",
    "feedback_up": "有帮助",
    "feedback_down": "没帮助",
    "feedback_thanks": "感谢反馈！",
    "sources": "来源",
    "sources_toggle": "查看更多",
    "greeting": "你好！有什么可以帮助您？",
    "typing": "正在输入",
    "offline_title": "给我们留言",
    "offline_name": "您的姓名",
    "offline_email": "您的邮箱",
    "offline_message": "请描述您的问题",
    "offline_submit": "发送留言",
    "offline_success": "感谢您的留言，我们会尽快联系您！",
    "offline_error": "发送失败，请重试。",
    "qr_search_tips": "怎样搜索更精准？",
    "qr_search_filters": "支持哪些筛选条件？",
    "qr_upload_doc": "如何上传文档？",
    "qr_file_formats": "支持哪些文件格式？",
    "qr_dashboard_metrics": "仪表盘指标的含义？",
    "qr_analytics_frequency": "分析数据更新频率？",
    "qr_admin_permissions": "如何管理用户权限？",
    "qr_cost_calculation": "成本是怎么计算的？"
  }
}
```

- [ ] **Commit**

```bash
git add src/i18n/en.json src/i18n/zh.json
git commit -m "i18n: add support widget feature keys"
```

---

### Task 2: Backend — offline message endpoint

**Files:**
- Create: `backend/app/routers/support.py`
- Modify: `backend/app/main.py`

- [ ] **Create support router**

`backend/app/routers/support.py`:
```python
"""Support router — offline message collection."""
import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/support", tags=["Support"])
limiter = Limiter(key_func=get_remote_address)

class OfflineMessage(BaseModel):
    name: str
    email: str
    message: str
    page_url: str | None = None

@router.post("/offline-message")
@limiter.limit("5/minute")
async def submit_offline_message(msg: OfflineMessage):
    """Record an offline support message from a disconnected user."""
    from app.config import settings
    conn = get_db()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                page_url TEXT,
                created_at TEXT NOT NULL,
                resolved INTEGER DEFAULT 0
            )"""
        )
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO support_messages (name, email, message, page_url, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg.name, msg.email, msg.message, msg.page_url, now),
        )
        conn.commit()
        logger.info("support.offline_message_saved", email=msg.email)
        return {"status": "ok", "message": "Message saved"}
    except Exception as e:
        logger.exception("support.offline_message_error")
        raise HTTPException(status_code=500, detail="Failed to save message")
    finally:
        conn.close()
```

- [ ] **Register router in main.py**

`backend/app/main.py` — add imports and include:
```python
from app.routers.support import router as support_router
```
After existing routers (before SPA static mount):
```python
app.include_router(support_router)
```

- [ ] **Commit**

```bash
git add backend/app/routers/support.py backend/app/main.py
git commit -m "feat: add offline message endpoint for support widget"
```

---

### Task 3: Extract shared SourceCard component

**Files:**
- Create: `src/components/shared/SourceCard.tsx`
- Modify: `src/components/ChatWidget.tsx` (replace inline rendering)

- [ ] **Create SourceCard component**

`src/components/shared/SourceCard.tsx`:
```tsx
interface Source {
  title: string;
  score?: number;
  snippet?: string;
  url?: string;
}

interface SourceCardProps {
  sources: Source[];
  maxVisible?: number;
  t: (key: string) => string;
}

export function SourceCard({ sources, maxVisible = 2, t }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? sources : sources.slice(0, maxVisible);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-3 pt-2 border-t border-[var(--border)]">
      <p className="text-xs font-medium text-[var(--text-tertiary)] mb-1 inline-flex items-center gap-1">
        {t('support.sources')}:
      </p>
      <div className="space-y-1">
        {visible.map((source, idx) => (
          <div key={idx} className="flex items-center gap-2 text-xs">
            <span className="text-[var(--accent)] font-medium truncate max-w-[200px]">{source.title}</span>
            {source.score !== undefined && (
              <span className="text-[var(--text-tertiary)] shrink-0">
                ({(source.score * 100).toFixed(0)}%)
              </span>
            )}
          </div>
        ))}
      </div>
      {sources.length > maxVisible && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-[var(--accent)] mt-1 hover:underline"
        >
          {expanded ? t('support.sources_toggle') : `${t('support.sources_toggle')} (${sources.length - maxVisible})`}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Update ChatWidget to use shared SourceCard**

In `src/components/ChatWidget.tsx`:
- Import `SourceCard` from `../components/shared/SourceCard`
- Replace the inline source rendering block (lines 94-110) with:
```tsx
<SourceCard sources={msg.sources} t={t} />
```

- [ ] **Integrate SourceCard into SupportWidget**

In `SupportWidget.tsx`:
- Import `SourceCard`
- Add `sources` to `ChatMessage` type: `export interface ChatMessage { role: 'user' | 'assistant'; content: string; sources?: Source[]; }`
- In WebSocket `onMessage`, handle `sources` and `citation` events:
```tsx
if (msg.type === 'sources' && Array.isArray(msg.sources)) {
  // Store sources for the current streaming message
  setStreamingSources(msg.sources);
} else if (msg.type === 'citation') {
  // Append single citation
  setStreamingSources(prev => [...prev, msg.source]);
}
```
- Add `streamingSources` state
- When `response_complete`/`done` fires, attach sources to the final message:
```tsx
setMessages((msgs) => [...msgs, { role: 'assistant' as const, content: prev, sources: streamingSources }]);
setStreamingSources([]);
```
- Render `SourceCard` at the bottom of each assistant message:
```tsx
{msg.sources && msg.sources.length > 0 && (
  <SourceCard sources={msg.sources} t={t} />
)}
```

- [ ] **Commit**

```bash
git add src/components/shared/SourceCard.tsx src/components/ChatWidget.tsx src/components/SupportWidget.tsx
git commit -m "refactor: extract SourceCard shared component, integrate sources into SupportWidget"
```

---

### Task 4: Message toolbar (copy/feedback/regenerate)

**Files:**
- Create: `src/components/shared/MessageActions.tsx`
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Create MessageActions component**

`src/components/shared/MessageActions.tsx`:
```tsx
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
          <button onClick={() => setFeedback(feedback === 'down' ? 'null' : 'down')} className={`p-1 rounded hover:bg-[var(--bg-tertiary)] ${feedback === 'down' ? 'text-red-400' : ''}`} title={t('support.feedback_down')} data-testid="msg-feedback-down">
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
```

- [ ] **Add toolbar to SupportWidget messages**

In `SupportWidget.tsx`:
- Import `MessageActions`
- Wrap each message div with `className="group"` to enable hover show
- Add `<MessageActions>` inside each message bubble, after `<p>` content
- Pass `onRegenerate` for assistant messages: find last user message index, truncate messages to before it, resend

Specifically, change the message rendering block (around line 270-290):
```tsx
{messages.map((msg: ChatMessage, idx: number) => (
  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} group`} data-testid={`support-message-${msg.role}-${idx}`}>
    <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${msg.role === 'user' ? 'rounded-br-none' : 'rounded-bl-none'}`} style={{ background: msg.role === 'user' ? 'var(--accent)' : 'var(--bg-tertiary)', color: msg.role === 'user' ? 'white' : 'var(--text-primary)' }}>
      <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
      <MessageActions role={msg.role} content={msg.content} onRegenerate={msg.role === 'assistant' ? () => handleRegenerate(idx) : undefined} t={t} />
    </div>
  </div>
))}
```

Add `handleRegenerate` callback:
```tsx
const handleRegenerate = useCallback((assistantIdx: number) => {
  // Find the last user message before this assistant message
  let lastUserIdx = -1;
  for (let i = assistantIdx - 1; i >= 0; i--) {
    if (messages[i].role === 'user') {
      lastUserIdx = i;
      break;
    }
  }
  if (lastUserIdx === -1) return;
  const userMessage = messages[lastUserIdx].content;
  // Truncate messages to before the user message
  setMessages(messages.slice(0, lastUserIdx));
  // Resend
  handleSend(userMessage);
}, [messages, handleSend]);
```

- [ ] **Commit**

```bash
git add src/components/shared/MessageActions.tsx src/components/SupportWidget.tsx
git commit -m "feat: add message toolbar (copy/feedback/regenerate) to support widget"
```

---

### Task 5: Conversation persistence

**Files:**
- Create: `src/hooks/useSupportMessages.ts`
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Create persistence hook**

`src/hooks/useSupportMessages.ts`:
```tsx
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

  // Load on mount
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

  // Save on change (debounced, skip during streaming)
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
```

- [ ] **Integrate into SupportWidget**

In `SupportWidget.tsx`:
- Export `ChatMessage` interface (or extract to shared type)
- Import and call `useSupportMessages(messages, setMessages, isStreaming)`

- [ ] **Commit**

```bash
git add src/hooks/useSupportMessages.ts src/components/SupportWidget.tsx
git commit -m "feat: persist support conversations to localStorage"
```

---

### Task 6: Proactive greeting

**Files:**
- Create: `src/hooks/useSupportGreeting.ts`
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Create greeting hook**

`src/hooks/useSupportGreeting.ts`:
```tsx
import { useState, useEffect } from 'react';

const SESSION_KEY = 'aureon_support_greeted';
const GREET_DELAY_MS = 10_000;

export function useSupportGreeting(isOpen: boolean) {
  const [showGreeting, setShowGreeting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setShowGreeting(false);
      return;
    }
    const alreadyGreeted = sessionStorage.getItem(SESSION_KEY);
    if (alreadyGreeted) return;

    const timer = setTimeout(() => {
      setShowGreeting(true);
      sessionStorage.setItem(SESSION_KEY, '1');
    }, GREET_DELAY_MS);

    return () => clearTimeout(timer);
  }, [isOpen]);

  const dismissGreeting = () => setShowGreeting(false);

  return { showGreeting, dismissGreeting };
}
```

- [ ] **Add greeting bubble to FAB in SupportWidget**

In `SupportWidget.tsx`:
- Import and use `useSupportGreeting`
- Near the FAB button, conditionally render greeting bubble:
```tsx
{showGreeting && !isOpen && (
  <div className="fixed bottom-24 right-6 z-50 animate-fade-in">
    <div className="relative bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl px-4 py-3 shadow-lg max-w-[200px]">
      <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{t('support.greeting')}</p>
      <div className="absolute bottom-[-6px] right-6 w-3 h-3 bg-[var(--bg-secondary)] border-r border-b border-[var(--border)] rotate-45" />
    </div>
  </div>
)}
```

Add CSS animation:
```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-fade-in {
  animation: fadeIn 0.4s ease-out;
}
```

- [ ] **Commit**

```bash
git add src/hooks/useSupportGreeting.ts src/components/SupportWidget.tsx
git commit -m "feat: proactive greeting after 10s for support widget"
```

---

### Task 7: Improved typing indicator

**Files:**
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Update loading indicator**

Replace the simple loading block (around line 313-325):
```tsx
{isStreaming && !streamingText && (
  <div className="flex justify-start" data-testid="support-loading">
    <div className="rounded-2xl rounded-bl-none px-4 py-3" style={{ background: 'var(--bg-tertiary)' }}>
      <div className="flex items-center gap-1.5">
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>AI {t('support.typing')}...</span>
        <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '150ms' }} />
        <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-tertiary)', animationDelay: '300ms' }} />
      </div>
    </div>
  </div>
)}
```

- [ ] **Commit**

```bash
git add src/components/SupportWidget.tsx
git commit -m "feat: improve typing indicator with typing text"
```

---

### Task 8: Dynamic quick replies

**Files:**
- Create: `src/support/quickReplyRoutes.ts`
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Create route mapping**

`src/support/quickReplyRoutes.ts`:
```ts
const ROUTE_QUESTIONS: Record<string, string[]> = {
  '/search': ['support.qr_search_tips', 'support.qr_search_filters'],
  '/documents': ['support.qr_upload_doc', 'support.qr_file_formats'],
  '/dashboard': ['support.qr_dashboard_metrics'],
  '/analytics': ['support.qr_analytics_frequency'],
  '/admin': ['support.qr_admin_permissions'],
  '/cost': ['support.qr_cost_calculation'],
};

export function getRouteQuickReplies(t: (key: string) => string): string[] {
  const path = window.location.pathname;
  // Find matching route (exact or prefix match)
  const keys = Object.entries(ROUTE_QUESTIONS).find(([route]) =>
    path === route || path.startsWith(route + '/')
  )?.[1] ?? [];
  return keys.map(k => t(k));
}
```

- [ ] **Integrate into SupportWidget**

In `SupportWidget.tsx`:
- Import `getRouteQuickReplies`
- Replace static quick replies with merged static + dynamic:
```tsx
const staticReplies = t('support.quickReplies', { returnObjects: true }) as string[];
const routeReplies = getRouteQuickReplies(t);
const allReplies = [...new Set([...routeReplies, ...staticReplies])];
```
Use `allReplies` instead of `quickReplies`.

- [ ] **Commit**

```bash
git add src/support/quickReplyRoutes.ts src/components/SupportWidget.tsx
git commit -m "feat: dynamic quick replies based on page route"
```

---

### Task 9: Offline message form

**Files:**
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Add offline message state and form**

In `SupportWidget.tsx`:
- Add state: `const [offlineMode, setOfflineMode] = useState(false);`
- Replace input area when `!isConnected && (user tries to send or offlineMode)` with form:

```tsx
{offlineMode || !isConnected ? (
  <div className="border-t p-3 shrink-0" style={{ borderColor: 'var(--border)' }}>
    <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-primary)' }}>{t('support.offline_title')}</p>
    {offlineStatus === 'idle' ? (
      <>
        <input ref={offlineNameRef} className="w-full rounded-lg border px-3 py-2 text-sm mb-2" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }} placeholder={t('support.offline_name')} data-testid="offline-name" />
        <input className="w-full rounded-lg border px-3 py-2 text-sm mb-2" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }} placeholder={t('support.offline_email')} type="email" data-testid="offline-email" />
        <textarea className="w-full rounded-lg border px-3 py-2 text-sm mb-2 resize-none" style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)', minHeight: '60px' }} placeholder={t('support.offline_message')} data-testid="offline-message" />
        <button onClick={handleOfflineSubmit} className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ background: 'var(--accent)' }} data-testid="offline-submit">{t('support.offline_submit')}</button>
      </>
    ) : offlineStatus === 'success' ? (
      <p className="text-sm text-green-400">{t('support.offline_success')}</p>
    ) : (
      <div><p className="text-sm text-red-400 mb-2">{t('support.offline_error')}</p><button onClick={() => setOfflineStatus('idle')} className="text-xs text-[var(--accent)] underline">{t('cost.retry')}</button></div>
    )}
  </div>
) : (
  // existing input area
)}
```

Add `handleOfflineSubmit`:
```tsx
const [offlineStatus, setOfflineStatus] = useState<'idle' | 'sending' | 'success' | 'error'>('idle');
const offlineNameRef = useRef<HTMLInputElement>(null);

const handleOfflineSubmit = useCallback(async () => {
  // Gather form values
  const nameEl = document.querySelector<HTMLInputElement>('[data-testid="offline-name"]');
  const emailEl = document.querySelector<HTMLInputElement>('[data-testid="offline-email"]');
  const msgEl = document.querySelector<HTMLTextAreaElement>('[data-testid="offline-message"]');
  if (!nameEl || !emailEl || !msgEl) return;
  const name = nameEl.value.trim();
  const email = emailEl.value.trim();
  const message = msgEl.value.trim();
  if (!name || !email || !message) return;

  setOfflineStatus('sending');
  try {
    const res = await fetch('/api/v1/support/offline-message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, message, page_url: window.location.href }),
    });
    if (res.ok) {
      setOfflineStatus('success');
      setTimeout(() => setOfflineStatus('idle'), 5000);
    } else {
      setOfflineStatus('error');
    }
  } catch {
    setOfflineStatus('error');
  }
}, []);
```

Also trigger offline mode when user tries to send while disconnected:
In `handleSend`:
```tsx
if (!isConnected) {
  setOfflineMode(true);
  return;
}
```

- [ ] **Commit**

```bash
git add src/components/SupportWidget.tsx
git commit -m "feat: offline message form when WebSocket disconnected"
```

---

### Task 10: Unread badge

**Files:**
- Create: `src/hooks/useUnreadCount.ts`
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Create unread count hook**

`src/hooks/useUnreadCount.ts`:
```tsx
import { useState, useCallback, useRef, useEffect } from 'react';

export function useUnreadCount(isOpen: boolean) {
  const [count, setCount] = useState(0);
  const panelWasOpen = useRef(isOpen);

  useEffect(() => {
    if (isOpen) {
      setCount(0);
    }
    panelWasOpen.current = isOpen;
  }, [isOpen]);

  const increment = useCallback(() => {
    if (!panelWasOpen.current) {
      setCount(c => Math.min(c + 1, 100));
    }
  }, []);

  const display = count > 99 ? '99+' : count > 0 ? String(count) : null;

  return { count, increment, display, reset: () => setCount(0) };
}
```

- [ ] **Integrate into SupportWidget**

In `SupportWidget.tsx`:
- Import and use `useUnreadCount(isOpen)`
- In WebSocket `onMessage` handler, call `increment()` on `text`/`response_complete` events
- On FAB button, render badge:
```tsx
{!isOpen && unreadDisplay && (
  <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full min-w-[20px] h-5 flex items-center justify-center px-1 font-bold" data-testid="support-unread-badge">
    {unreadDisplay}
  </span>
)}
```

- [ ] **Commit**

```bash
git add src/hooks/useUnreadCount.ts src/components/SupportWidget.tsx
git commit -m "feat: unread badge counter on support FAB"
```

---

### Task 11: Update tests

**Files:**
- Modify: `src/components/__tests__/SupportWidget.test.tsx`
- Create: `src/components/__tests__/MessageActions.test.tsx`
- Create: `src/components/__tests__/SourceCard.test.tsx`
- Create: `src/hooks/__tests__/useSupportMessages.test.ts`
- Create: `src/hooks/__tests__/useUnreadCount.test.ts`

- [ ] **Add i18n mock keys for new features**

Update mock in `SupportWidget.test.tsx`:
```ts
const translations: Record<string, string> = {
  "support.title": "Aureon Support",
  "support.welcome": "Welcome! How can I help?",
  "support.online": "Online",
  "support.offline": "Offline",
  "support.placeholder": "Type your question...",
  "support.connecting": "Connecting...",
  "support.connected": "Connected and ready",
  "support.close": "Close",
  "support.copy": "Copy",
  "support.regenerate": "Regenerate",
  "support.feedback_up": "Helpful",
  "support.feedback_down": "Not helpful",
  "support.greeting": "Hi! Need help?",
  "support.typing": "is typing",
  "support.sources": "Sources",
  "support.offline_title": "Leave a message",
  "support.offline_name": "Your name",
  "support.offline_email": "Your email",
  "support.offline_message": "How can we help?",
  "support.offline_submit": "Send message",
  "offline_success": "Thank you!",
  "chat.send": "Send",
};
```

- [ ] **MessageActions tests**

`src/components/__tests__/MessageActions.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MessageActions } from '../shared/MessageActions';

describe('MessageActions', () => {
  const mockT = (k: string) => ({ 'support.copy': 'Copy', 'support.feedback_up': 'Helpful', 'support.feedback_down': 'Not helpful', 'support.regenerate': 'Regenerate' }[k] || k);

  it('renders copy button for user messages', () => {
    render(<MessageActions role="user" content="test" t={mockT} />);
    expect(screen.getByTestId('msg-copy')).toBeInTheDocument();
    expect(screen.queryByTestId('msg-feedback-up')).not.toBeInTheDocument();
  });

  it('renders feedback and regenerate for assistant messages', () => {
    render(<MessageActions role="assistant" content="test" onRegenerate={vi.fn()} t={mockT} />);
    expect(screen.getByTestId('msg-feedback-up')).toBeInTheDocument();
    expect(screen.getByTestId('msg-feedback-down')).toBeInTheDocument();
    expect(screen.getByTestId('msg-regenerate')).toBeInTheDocument();
  });

  it('calls onRegenerate when regenerate clicked', () => {
    const spy = vi.fn();
    render(<MessageActions role="assistant" content="test" onRegenerate={spy} t={mockT} />);
    fireEvent.click(screen.getByTestId('msg-regenerate'));
    expect(spy).toHaveBeenCalled();
  });

  it('toggles feedback state on click', () => {
    render(<MessageActions role="assistant" content="test" t={mockT} />);
    const upBtn = screen.getByTestId('msg-feedback-up');
    fireEvent.click(upBtn);
    expect(upBtn.className).toContain('text-green-400');
    fireEvent.click(upBtn);
    expect(upBtn.className).not.toContain('text-green-400');
  });
});
```

- [ ] **SourceCard tests**

`src/components/__tests__/SourceCard.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SourceCard } from '../shared/SourceCard';

describe('SourceCard', () => {
  const mockT = (k: string) => ({ 'support.sources': 'Sources', 'support.sources_toggle': 'Show more' }[k] || k);
  const sources = [
    { title: 'Doc A', score: 0.95 },
    { title: 'Doc B', score: 0.87 },
    { title: 'Doc C', score: 0.72 },
  ];

  it('renders limited sources by default', () => {
    render(<SourceCard sources={sources} t={mockT} />);
    expect(screen.getByText('Doc A')).toBeInTheDocument();
    expect(screen.getByText('Doc B')).toBeInTheDocument();
    expect(screen.queryByText('Doc C')).not.toBeInTheDocument();
  });

  it('expands to show all sources', () => {
    render(<SourceCard sources={sources} t={mockT} />);
    fireEvent.click(screen.getByText('Show more (1)'));
    expect(screen.getByText('Doc C')).toBeInTheDocument();
  });
});
```

- [ ] **useSupportMessages test**

`src/hooks/__tests__/useSupportMessages.test.ts`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSupportMessages } from '../useSupportMessages';

describe('useSupportMessages', () => {
  beforeEach(() => localStorage.clear());

  it('loads persisted messages from localStorage', () => {
    const msgs = [{ role: 'user' as const, content: 'hello' }];
    localStorage.setItem('aureon_support_messages', JSON.stringify(msgs));

    let state: any[] = [];
    const setter = (fn: any) => { state = fn(state); };
    renderHook(() => useSupportMessages([], setter, false));

    expect(state).toEqual(msgs);
  });

  it('saves messages to localStorage (debounced)', async () => {
    const msgs = [{ role: 'assistant' as const, content: 'hi' }];
    let state = msgs;
    const setter = (fn: any) => { state = fn(state); };

    renderHook(() => useSupportMessages(msgs, setter, false));

    await new Promise(r => setTimeout(r, 600));
    const saved = JSON.parse(localStorage.getItem('aureon_support_messages')!);
    expect(saved).toEqual(msgs);
  });
});
```

- [ ] **useUnreadCount tests**

`src/hooks/__tests__/useUnreadCount.test.ts`:
```tsx
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useUnreadCount } from '../useUnreadCount';

describe('useUnreadCount', () => {
  it('starts at 0', () => {
    const { result } = renderHook(() => useUnreadCount(false));
    expect(result.current.count).toBe(0);
    expect(result.current.display).toBeNull();
  });

  it('increments when panel closed', () => {
    const { result } = renderHook(() => useUnreadCount(false));
    act(() => result.current.increment());
    expect(result.current.count).toBe(1);
    expect(result.current.display).toBe('1');
  });

  it('resets on panel open', () => {
    const { result, rerender } = renderHook(({ isOpen }) => useUnreadCount(isOpen), { initialProps: { isOpen: false } });
    act(() => result.current.increment());
    rerender({ isOpen: true });
    expect(result.current.count).toBe(0);
    expect(result.current.display).toBeNull();
  });

  it('caps at 99+', () => {
    const { result } = renderHook(() => useUnreadCount(false));
    for (let i = 0; i < 150; i++) {
      act(() => result.current.increment());
    }
    expect(result.current.display).toBe('99+');
  });
});
```

- [ ] **Run all tests to verify**

```bash
npm test -- --run
```

Expected: all test files pass (including existing 14 + new ~20).

- [ ] **Commit**

```bash
git add src/components/__tests__/ src/hooks/__tests__/
git commit -m "test: add tests for support widget features"
```
