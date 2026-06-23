# Phase 2: Medium Effort — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 通过 20 项中等工作量改造，将 Aureon 综合评分从 7.5 提升到 8.5。

**Architecture:** 安全加固（CSP + rehype-sanitize + WS token）、代码健壮性（SSE 规范化 + JSON 解析）、性能（分布式锁 + Redis pipeline）、测试补齐（Chat + query_router + E2E）、可维护性（Dashboard 拆分 + Prompt 模板化）、鲁棒性（熔断器重写 + Redis 健康检查）、可扩展性（DI 升级 + 权限边界）。

**Tech Stack:** FastAPI middleware, rehype-sanitize, Playwright, asyncio.Semaphore, Redis SET NX, LangChain ChatPromptTemplate

---

## Batch 1: Security Hardening (S6-S9)

### S6: Content Security Policy
- File: `backend/app/main.py` — add SecurityHeadersMiddleware before CORS
- CSP: `default-src 'self'; script-src 'self'; connect-src 'self' https://aureon-production-659a.up.railway.app; frame-ancestors 'none'; base-uri 'self'`
- Also: X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security, Referrer-Policy

### S7: rehype-sanitize
- File: `src/components/MessageItem.tsx` — both user and AI message ReactMarkdown instances
- Install: `npm install rehype-sanitize`
- Schema: allow p, br, strong, em, code, pre, ul, ol, li, h1-h3, a (with href), blockquote

### S8: WebSocket token security
- File: `src/services/ws.ts:83` — move token from URL query to first message after connection
- Backend: accept auth via first WS message instead of URL param

### S9: /metrics endpoint auth
- File: `backend/app/main.py:141` — add optional METRICS_KEY env var check

## Batch 2: Code Robustness (R4-R6)

### R4: SSE protocol compliance
- File: `backend/app/common.py:72-74` — enhance sse_event() with event: and id: fields
- File: `src/services/api.ts` — handle done and error event types explicitly

### R5: LLM JSON parsing robustness
- File: `backend/app/memory/manager.py` — extract_atoms() handle ```json blocks
- Add generic parse_llm_json() utility

### R6: bare except elimination
- Global search for `except Exception:` without logging
- Add logger.exception() to all bare catches

## Batch 3: Performance (P5-P7)

### P5: Distributed lock rewrite
- File: `backend/app/rag/qdrant_ops.py:210-228` — replace sleep(10)*30 with Redis SET NX PX + Lua release

### P6: Redis pipeline batching
- File: `backend/app/cost/budget_engine.py:196-206` — pipeline hgetall
- File: `backend/app/cost/service.py:78-90` — pipeline hincrbyfloat

### P7: Embedding cache dedup
- File: `backend/app/rag/embedding.py` — check cache before API call in batch embed

## Batch 4: Testability (T3-T6)

### T3: ChatWidget test
- Create: `src/components/__tests__/ChatWidget.test.tsx`
- Test: send message, SSE stream, error state, empty state

### T4: query_router test
- Create: `backend/tests/test_query_router.py`
- Test: rule classification, LLM classification, timeout fallback

### T5: E2E chat flow
- Modify: `tests/e2e/chat.spec.ts` — mock SSE, test full conversation

### T6: Coverage threshold
- `backend/pyproject.toml` — increase fail_under from 50 to 55

## Batch 5: Maintainability (M4-M6)

### M4: Dashboard.tsx split
- Split 722-line file into container + 4 sub-components
- DashboardStatsGrid, DashboardRecentActivity, DashboardCharts, DashboardHeader

### M5: useDebouncedLocalStorage hook
- Create: `src/hooks/useDebouncedLocalStorage.ts`
- Replace 3 duplicate debounce patterns in Dashboard

### M6: System prompt modularization
- Extract prompts from `backend/app/agent/agent.py` to `backend/app/prompts/`
- Use ChatPromptTemplate with language variables

## Batch 6: Reliability + Extensibility (RB3-RB4, EX3-EX4)

### RB3: Circuit breaker rewrite
- File: `backend/app/reliability/circuit_breaker.py`
- HALF_OPEN: asyncio.Semaphore(3) for concurrent probes
- Success threshold: 3 consecutive successes to close
- State property: pure read, transitions in explicit methods
- Time window reset for failure counter

### RB4: Redis connection health check
- File: `backend/app/cache/connection.py` — add health_check_interval=30

### EX3: FastAPI DI upgrade
- Annotated type aliases for key dependencies
- @lru_cache Settings singleton

### EX4: Permission boundary enforcement
- File: `backend/app/security/roles_router.py:115` — max role constraint
