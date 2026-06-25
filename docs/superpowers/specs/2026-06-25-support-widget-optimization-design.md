# Support Widget Optimization Design

## Goals

1. Add message toolbar (copy/feedback/regenerate)
2. Add source citations to AI answers
3. Persist conversation across page reloads
4. Proactive greeting after 10s
5. Improve streaming indicator (typing text + dots)
6. Dynamic quick replies based on page route
7. Offline message collection form
8. Unread badge counter on FAB

## Architecture

No new services or frameworks. All changes within existing files:

- `src/components/SupportWidget.tsx` — main widget (8 feature additions)
- `src/components/shared/SourceCard.tsx` — extracted shared source component (new)
- `src/components/shared/MessageActions.tsx` — toolbar component (new)
- `src/hooks/useSupportMessages.ts` — extracted message persistence hook (new)
- `src/hooks/useSupportGreeting.ts` — greeting trigger hook (new)
- `src/hooks/useOfflineMessage.ts` — offline form hook (new)
- `src/hooks/useUnreadCount.ts` — unread badge hook (new)
- `src/support/quickReplyRoutes.ts` — route→questions mapping (new)
- `src/i18n/en.json` + `src/i18n/zh.json` — new translation keys
- `backend/app/routers/support.py` — offline message endpoint (new)
- `backend/app/main.py` — register new router

## Phase 1 — Items

### 1. Message Toolbar

**Component:** `src/components/shared/MessageActions.tsx`

- Props: `message: ChatMessage, onCopy, onFeedback, onRegenerate`
- User messages → only copy button
- AI messages → copy / thumbs-up / thumbs-down / regenerate
- Thumbs state: `null | 'up' | 'down'`, once set stays set
- Copy uses `navigator.clipboard.writeText()` + toast
- Regenerate: find last user message, trim messages array to before that, resend
- Toolbar appears on hover (opacity transition), visible on the message's right side
- i18n keys: `support.copy`, `support.copy_success`, `support.regenerate`, `support.feedback_up`, `support.feedback_down`, `support.feedback_thanks`

### 2. Source Citations

**Backend:** already sends `type: "sources"` and `type: "citation"` WebSocket messages → no changes needed.

**Frontend:**
- Add `sources` field to message state alongside `role/content`
- Parse `sources` and `citation` WebSocket events
- Extract `SourceCard` from `ChatWidget.tsx` into `src/components/shared/SourceCard.tsx`
- Render collapsed by default (max 2 sources), "查看更多" toggle
- i18n keys: `support.sources`, `support.sources_toggle`

### 3. Conversation Persistence

**Hook:** `src/hooks/useSupportMessages.ts`

- Load from `localStorage['aureon_support_messages']` on mount
- Subscribe to message changes, debounce 500ms write to localStorage
- Max 50 messages, trim oldest on overflow
- Clear action also clears localStorage
- Edge case: streaming state is not persisted (only completed messages)

### 4. Proactive Greeting

**Hook:** `src/hooks/useSupportGreeting.ts`

- Timer starts when SupportWidget mounts
- After 10s, if panel is closed and no greeting shown yet: show float bubble
- Bubble: arrow-tipped popover, positioned above FAB, dismisses on panel open
- `sessionStorage['aureon_support_greeted']` — once per session
- i18n: `support.greeting` ("Hi! Need help?" / "你好！有什么可以帮助您？")

### 5. Typing Indicator

**Current:** three bouncing dots only.
**Change:** `AI ${t('support.typing')}...` + three dots animation
- i18n: `support.typing` → "is typing" / "正在输入"
- Keep existing `data-testid="support-loading"`

## Phase 2 — Items

### 6. Dynamic Quick Replies

**File:** `src/support/quickReplyRoutes.ts`
```ts
const routeQuestions: Record<string, string[]> = {
  '/search': ['support.qr_search_tips', 'support.qr_search_filters'],
  '/documents': ['support.qr_upload_doc', 'support.qr_file_formats'],
  '/dashboard': ['support.qr_dashboard_metrics'],
  '/analytics': ['support.qr_analytics_frequency'],
  '/admin': ['support.qr_admin_permissions'],
  '/cost': ['support.qr_cost_calculation'],
};
```

- Merge static i18n `quickReplies` + dynamic route matches
- Deduplicate by text content
- Only show when no messages sent yet (existing behavior preserved)
- Re-calculated on panel open

**i18n keys:** `support.qr_search_tips`, `support.qr_search_filters`, etc.

### 7. Offline Message

**Backend:** `POST /api/v1/support/offline-message`
- Body: `{ name: string, email: string, message: string, page_url?: string }`
- Write to SQLite `support_messages` table (id, name, email, message, page_url, created_at, resolved: false)
- No auth required (public endpoint for guest visitors)
- Rate limit: 5/min per IP

**Frontend:**
- Detect WebSocket disconnected + user tries to send → slide in form replacing input area
- Fields: name, email, message textarea, submit button
- On success: confirmation text, dismiss after 5s
- On error: error text, retry button
- i18n: `support.offline_title`, `support.offline_name`, `support.offline_email`, `support.offline_message`, `support.offline_submit`, `support.offline_success`, `support.offline_error`

### 8. Unread Badge

**Hook:** `src/hooks/useUnreadCount.ts`
- Ref `isPanelOpen` set by SupportWidget
- WebSocket `text`/`response_complete` events → increment count when panel closed
- Panel opens → reset count
- FAB renders red badge: `bg-red-500 text-white text-xs rounded-full min-w-[20px] h-5`
- Position: `top-[-4px] right-[-4px]`
- Count > 99 → "99+"
- `data-testid="support-unread-badge"`

## Data Flow

```
WebSocket event ──→ useWebSocket hook ──→ SupportWidget state
                                              │
                    ┌─────────────────────────┤
                    ▼                         ▼
            MessageActions.tsx        localStorage persistence
            SourceCard.tsx            (useSupportMessages)
            unread badge
            greeting timer
```

## Testing

| Test | Coverage |
|------|----------|
| MessageActions: copy calls clipboard | new |
| MessageActions: thumbs up/down sets state | new |
| MessageActions: regenerate resends last user message | new |
| SourceCard renders from `sources` state | new |
| Persistence: messages survive page reload | update existing |
| Greeting: shows after 10s, dismisses on open | new |
| Typing: shows "typing" text + dots | update existing |
| Dynamic QR: route-specific questions appear | new |
| Offline form: submit calls API, shows success | new |
| Unread badge: increments while closed, resets on open | new |

## Files Changed Summary

| File | Change |
|------|--------|
| `src/components/SupportWidget.tsx` | Major: add 8 features |
| `src/components/shared/MessageActions.tsx` | New: toolbar component |
| `src/components/shared/SourceCard.tsx` | New: extracted from ChatWidget |
| `src/hooks/useSupportMessages.ts` | New: localStorage persistence |
| `src/hooks/useSupportGreeting.ts` | New: 10s greeting trigger |
| `src/hooks/useUnreadCount.ts` | New: unread badge state |
| `src/support/quickReplyRoutes.ts` | New: route→questions map |
| `src/i18n/en.json` | +~15 keys |
| `src/i18n/zh.json` | +~15 keys |
| `src/components/ChatWidget.tsx` | Minor: extract SourceCard |
| `backend/app/routers/support.py` | New: offline message endpoint |
| `backend/app/main.py` | +register support router |
