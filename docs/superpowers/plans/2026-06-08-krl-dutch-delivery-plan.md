# KRL-Dutch Delivery Plan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare Aureon for KRL-Dutch Upwork delivery — optimize RAG quality, add voice input, support 200 concurrent connections, and create commercial assets (Portfolio, Proposal).

**Architecture:** Dual-track approach: Track 1 (Week 1, quick submit) adds prompt optimization, voice input, concurrency limits, and a Portfolio MVP. Track 2 (Week 1-3) adds CRAG confidence gating, multi-query LLM expansion, post-generation reflection, Gunicorn multi-worker, and deployment scripts. Commercial prep (Week 3-4) produces a Portfolio v2, demo video, and second-tier proposal.

**Tech Stack:** Python 3.12, FastAPI, React 19, TypeScript, Tailwind CSS, Web Speech API, asyncio.Semaphore, Gunicorn + Uvicorn, Redis Pub/Sub

**Spec:** `docs/superpowers/specs/2026-06-08-krl-dutch-delivery-plan.md`

**Reference:** `docs/RAG_OPTIMIZATION_PROMPT.md` (technical details for each optimization)

---

## File Structure

### New Files

| File | Responsibility |
|------|----------------|
| `backend/app/concurrency.py` | LLM API + RAG pipeline Semaphore rate limiting |
| `backend/tests/test_concurrency.py` | Concurrency module tests |
| `src/hooks/useSpeechRecognition.ts` | Web Speech API hook (STT) |
| `src/components/VoiceButton.tsx` | Microphone button component |
| `src/__tests__/useSpeechRecognition.test.ts` | Speech hook tests |
| `src/__tests__/VoiceButton.test.tsx` | Voice button tests |
| `src/pages/Portfolio.tsx` | Portfolio showcase page |
| `src/__tests__/Portfolio.test.tsx` | Portfolio page tests |
| `backend/app/rag/retrieval_confidence.py` | CRAG confidence gating |
| `backend/tests/test_retrieval_confidence.py` | CRAG tests |
| `backend/app/rag/multi_query_llm.py` | LLM Multi-Query Expansion |
| `backend/tests/test_multi_query_llm.py` | Multi-query tests |
| `backend/app/rag/post_generation_reflection.py` | Self-RAG reflection |
| `backend/tests/test_post_generation_reflection.py` | Reflection tests |
| `backend/app/rag/threshold_tuner.py` | Grid search threshold optimizer |
| `backend/tests/test_threshold_tuner.py` | Threshold tuner tests |
| `backend/app/vector_store_interface.py` | Abstract vector store interface |
| `backend/app/pgvector_store.py` | pgvector adapter (optional) |
| `backend/tests/test_vector_store_interface.py` | Interface tests |
| `deploy/digitalocean/docker-compose.prod.yml` | DO production compose |
| `deploy/digitalocean/nginx.conf` | Nginx WebSocket proxy config |
| `deploy/digitalocean/deploy.sh` | One-click DO deploy script |
| `deploy/digitalocean/Dockerfile.gunicorn` | Gunicorn multi-worker Dockerfile |

### Modified Files

| File | Changes |
|------|---------|
| `backend/app/rag/qa_chain.py:621-651` | Rewrite QA_SYSTEM_PROMPT + QA_SYSTEM_PROMPT_EN with prohibitions and examples |
| `backend/app/langgraph/nodes/agent.py:52-54` | Fix `full_query` construction with proper system prefix |
| `src/components/ChatWidget.tsx:199-225` | Add VoiceButton next to send button |
| `src/App.tsx:46-50` | Add `/portfolio` route |
| `src/i18n/en.json` | Add portfolio + voice i18n keys |
| `src/i18n/zh.json` | Add portfolio + voice i18n keys |
| `backend/app/config.py` | Add concurrency + CRAG config vars |
| `backend/.env.example` | Add new environment variables |
| `backend/Dockerfile:31` | Add Gunicorn entrypoint option |
| `backend/app/main.py` | Import concurrency module |

---

## Track 1: Quick Submit (Week 1)

### Task 1: Rewrite QA_SYSTEM_PROMPT

**Files:**
- Modify: `backend/app/rag/qa_chain.py:621-651`
- Test: `backend/tests/test_rag_quality.py` (existing)

- [ ] **Step 1: Read current prompts**

Read `backend/app/rag/qa_chain.py` lines 621-651 to understand the current `QA_SYSTEM_PROMPT` and `QA_SYSTEM_PROMPT_EN`.

- [ ] **Step 2: Write the optimized Chinese prompt**

Replace `QA_SYSTEM_PROMPT` (line 621-635) with:

```python
QA_SYSTEM_PROMPT = """你是精准的知识库问答助手。你的唯一任务是回答用户的问题。

## 核心原则
- 先理解用户的问题意图，再从参考文档中提取答案
- 每个句子必须直接回应用户的问题
- 如果文档中有答案，直接给出答案
- 如果文档中没有答案，直接说"文档中未提及"

## 回答结构（必须遵守）
1. **直接回答**（1-2 句话，直接回答问题核心）
2. **补充细节**（仅当用户问题需要更详细解释时）
3. **引用来源**（格式：[来源: 文章标题]）

## 禁止行为
- ❌ 禁止以"根据文档"、"文档介绍了"、"参考文档提到"开头
- ❌ 禁止复述文档内容而不回答问题
- ❌ 禁止添加用户未要求的背景信息
- ❌ 禁止使用"总的来说"、"综上所述"、"需要注意的是"等总结性语句
- ❌ 禁止在回答开头加前言或铺垫

## 正确示例

用户问："BM25 的核心原理是什么？"
✅ 正确："BM25 通过词频饱和度和文档长度归一化计算关键词匹配分数，核心公式包含 TF（词频）和 IDF（逆文档频率）两个组件。[来源: RAG 优化实战]"
❌ 错误："文档介绍了 RAG 系统中使用的多种检索技术。BM25 是其中一种经典的排序算法，它的核心原理是..."

用户问："如何配置 Redis 缓存？"
✅ 正确："配置步骤：1) 安装 redis-py；2) 设置 REDIS_URL 环境变量；3) 在 config.py 中启用缓存层。[来源: Redis 集成指南]"
❌ 错误："Redis 是一个高性能的内存数据库，在 RAG 系统中常用于缓存。下面文档介绍了如何配置..."

## 负面回答模式
如果参考文档中没有相关信息，直接回答：
"文档中未提及该信息。"

不要猜测、不要补充你认为可能正确的信息。

{lang_instruction}

参考文档中每段以 [Source N: 文章标题] 开头。引用时用自然方式标注来源，例如：[来源: Hermes Agent 实战]。

参考文档：
{context}
"""
```

- [ ] **Step 3: Write the optimized English prompt**

Replace `QA_SYSTEM_PROMPT_EN` (line 637-651) with:

```python
QA_SYSTEM_PROMPT_EN = """You are a precise knowledge base QA assistant. Your only task is to answer the user's question.

## Core Principles
- Understand the user's question intent first, then extract the answer from reference documents
- Every sentence must directly address the user's question
- If the documents contain the answer, give it directly
- If the documents don't contain the answer, say "Not mentioned in the documents"

## Answer Structure (mandatory)
1. **Direct answer** (1-2 sentences, addressing the core question)
2. **Supporting details** (only when the user needs more explanation)
3. **Source citation** (format: [Source: Article Title])

## Prohibited Patterns
- ❌ Do NOT start with "Based on the documents", "The documents mention", "According to the reference"
- ❌ Do NOT summarize document content without answering the question
- ❌ Do NOT add background information the user didn't ask for
- ❌ Do NOT use "In summary", "To summarize", "It's worth noting" as transitions
- ❌ Do NOT add preamble or setup before the actual answer

## Correct Examples

User: "What is the core principle of BM25?"
✅ Correct: "BM25 calculates keyword matching scores through term frequency saturation and document length normalization, with TF and IDF as its two core components. [Source: RAG Optimization Guide]"
❌ Wrong: "The documents describe various retrieval techniques used in RAG systems. BM25 is one of the classic ranking algorithms. Its core principle is..."

User: "How to configure Redis caching?"
✅ Correct: "Steps: 1) Install redis-py; 2) Set REDIS_URL environment variable; 3) Enable cache layer in config.py. [Source: Redis Integration Guide]"
❌ Wrong: "Redis is a high-performance in-memory database commonly used for caching in RAG systems. The following documents describe how to configure..."

## Negative Response
If the reference documents don't contain the relevant information, answer directly:
"The documents do not contain information about this topic."

Do not guess or supplement information you think might be correct.

{lang_instruction}

Each paragraph in the reference documents starts with [Source N: Article Title]. When citing, naturally mention the source, e.g., [Source: Hermes Agent in Practice].

Reference documents:
{context}
"""
```

- [ ] **Step 4: Run existing RAG quality tests**

Run: `cd backend && python -m pytest tests/test_rag_quality.py -v -x 2>&1 | tail -20`
Expected: All existing tests pass (prompts are string changes, logic unchanged)

- [ ] **Step 5: Run DeepEval evaluation to measure Answer Relevance improvement**

Run: `cd backend && python tests/deepeval_eval.py 2>&1 | tail -30`
Expected: Answer Relevancy score improves from 0.21 toward 0.55+

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat(rag): rewrite QA prompts with prohibitions and examples for Answer Relevance improvement

Based on RAG_OPTIMIZATION_PROMPT.md §3: added prohibited patterns, correct/wrong
examples, and structured answer format. Expected Answer Relevance 0.21 -> 0.55+."
```

---

### Task 2: Fix Agent Path Prompt

**Files:**
- Modify: `backend/app/langgraph/nodes/agent.py:44-61`
- Test: `backend/tests/test_agent_flow.py` (existing)

- [ ] **Step 1: Read current agent.py**

Read `backend/app/langgraph/nodes/agent.py` lines 44-61 to understand `run_agent_node`.

- [ ] **Step 2: Define the agent system prefix constant**

Add above `run_agent_node` (after line 42):

```python
_AGENT_SYSTEM_PREFIX = """你是知识库问答助手。基于参考上下文回答用户问题。

规则：
1. 直接回答问题，不要以"根据文档"开头
2. 每个句子必须直接回应用户的问题
3. 不要总结文档内容，直接给出答案
4. 引用来源：[来源: 文章标题]

参考上下文：
{context}
"""
```

- [ ] **Step 3: Update run_agent_node to use the prefix**

Replace lines 52-54 in `run_agent_node`:

```python
    # Combine context + query with proper system instructions
    full_query = query
    if context:
        full_query = f"{_AGENT_SYSTEM_PREFIX.format(context=context)}\n\n用户问题：{query}"
```

- [ ] **Step 4: Run existing agent tests**

Run: `cd backend && python -m pytest tests/test_agent_flow.py -v -x 2>&1 | tail -20`
Expected: All existing agent tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/langgraph/nodes/agent.py
git commit -m "fix(agent): add proper system prefix to agent path prompt

Aligns agent.py answer quality with qa_chain.py by adding prohibited patterns
and structured answer format. Fixes quality gap between RAG and Agent paths."
```

---

### Task 3: Add Concurrency Semaphore Module

**Files:**
- Create: `backend/app/concurrency.py`
- Create: `backend/tests/test_concurrency.py`
- Modify: `backend/app/main.py` (import)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_concurrency.py`:

```python
"""Tests for concurrency rate limiting module."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException


@pytest.fixture
def concurrency_module():
    """Import concurrency module with fresh state."""
    import importlib
    import app.concurrency
    importlib.reload(app.concurrency)
    return app.concurrency


class TestSemaphoreLimits:
    """Test that semaphores enforce concurrency limits."""

    @pytest.mark.asyncio
    async def test_llm_semaphore_allows_concurrent_calls(self, concurrency_module):
        """LLM semaphore should allow calls within limit."""
        cm = concurrency_module
        # Default deepseek-chat limit is 30
        results = []

        async def mock_call():
            async with cm.llm_call_with_semaphore("deepseek-chat"):
                results.append(True)
                await asyncio.sleep(0.01)

        # 5 concurrent calls should all succeed
        await asyncio.gather(*[mock_call() for _ in range(5)])
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_rag_semaphore_allows_concurrent_calls(self, concurrency_module):
        """RAG pipeline semaphore should allow calls within limit."""
        cm = concurrency_module
        results = []

        async def mock_call():
            async with cm.rag_pipeline_semaphore():
                results.append(True)
                await asyncio.sleep(0.01)

        await asyncio.gather(*[mock_call() for _ in range(5)])
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_queue_timeout_returns_503(self, concurrency_module):
        """Should raise HTTPException 503 when queue times out."""
        cm = concurrency_module
        # Override timeout to be very short for testing
        original_timeout = cm.QUEUE_TIMEOUT_SECONDS
        cm.QUEUE_TIMEOUT_SECONDS = 0.01

        # Exhaust the semaphore
        sem = cm._LLM_SEMAPHORES.get("test-model")
        if sem is None:
            cm._LLM_SEMAPHORES["test-model"] = asyncio.Semaphore(1)
            sem = cm._LLM_SEMAPHORES["test-model"]

        await sem.acquire()  # Hold the only slot

        with pytest.raises(HTTPException) as exc_info:
            async with cm.llm_call_with_semaphore("test-model"):
                pass

        assert exc_info.value.status_code == 503
        sem.release()
        cm.QUEUE_TIMEOUT_SECONDS = original_timeout


class TestConnectionStats:
    """Test connection statistics reporting."""

    def test_get_stats_returns_dict(self, concurrency_module):
        """get_concurrency_stats should return a dict with expected keys."""
        stats = concurrency_module.get_concurrency_stats()
        assert isinstance(stats, dict)
        assert "llm_semaphores" in stats
        assert "rag_semaphore_available" in stats
        assert "queue_timeout_seconds" in stats
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_concurrency.py -v -x 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.concurrency'`

- [ ] **Step 3: Implement concurrency.py**

Create `backend/app/concurrency.py`:

```python
"""Concurrency rate limiting for LLM API and RAG pipeline.

Uses asyncio.Semaphore to prevent thundering herd when many concurrent
requests hit the same LLM API or RAG pipeline. Each model gets its own
semaphore so different providers don't block each other.

Based on RAG_OPTIMIZATION_PROMPT.md §5.3.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Dict

import structlog

logger = structlog.get_logger()

# ── Configuration ──

QUEUE_TIMEOUT_SECONDS = float(os.getenv("QUEUE_TIMEOUT_SECONDS", "30"))

# LLM API semaphores (per model)
_LLM_SEMAPHORES: Dict[str, asyncio.Semaphore] = {
    "deepseek-chat": asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_DEEPSEEK", "30"))),
    "deepseek-reasoner": asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_REASONER", "10"))),
    "dashscope-embedding": asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_EMBEDDING", "50"))),
}

# RAG pipeline semaphore (vector retrieval + rerank)
_RAG_SEMAPHORE = asyncio.Semaphore(int(os.getenv("RAG_SEMAPHORE", "40")))

# Default semaphore for unknown models
_DEFAULT_LLM_SEMAPHORE = asyncio.Semaphore(int(os.getenv("LLM_SEMAPHORE_DEFAULT", "20")))


@asynccontextmanager
async def llm_call_with_semaphore(model: str):
    """Rate-limit LLM API calls by model.

    Usage:
        async with llm_call_with_semaphore("deepseek-chat"):
            result = await llm.ainvoke(prompt)
    """
    sem = _LLM_SEMAPHORES.get(model, _DEFAULT_LLM_SEMAPHORE)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        from fastapi import HTTPException
        logger.warning("LLM semaphore timeout", model=model, timeout=QUEUE_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=503,
            detail="System busy. Please try again later.",
        )
    try:
        yield
    finally:
        sem.release()


@asynccontextmanager
async def rag_pipeline_semaphore():
    """Rate-limit RAG pipeline calls.

    Usage:
        async with rag_pipeline_semaphore():
            chunks = await hybrid_retrieve(query)
    """
    try:
        await asyncio.wait_for(_RAG_SEMAPHORE.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        from fastapi import HTTPException
        logger.warning("RAG pipeline semaphore timeout", timeout=QUEUE_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline busy. Please try again later.",
        )
    try:
        yield
    finally:
        _RAG_SEMAPHORE.release()


def get_concurrency_stats() -> dict:
    """Return current concurrency statistics for monitoring."""
    return {
        "llm_semaphores": {
            model: {"limit": sem._value, "available": sem._value}
            for model, sem in _LLM_SEMAPHORES.items()
        },
        "rag_semaphore_available": _RAG_SEMAPHORE._value,
        "queue_timeout_seconds": QUEUE_TIMEOUT_SECONDS,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_concurrency.py -v -x 2>&1 | tail -20`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/concurrency.py backend/tests/test_concurrency.py
git commit -m "feat(concurrency): add asyncio.Semaphore rate limiting for LLM and RAG

Prevents thundering herd at 200 concurrent connections. Per-model LLM semaphores
(deepseek:30, embedding:50) + RAG pipeline semaphore (40). 30s queue timeout."
```

---

### Task 4: Add Voice Input (Web Speech API)

**Files:**
- Create: `src/hooks/useSpeechRecognition.ts`
- Create: `src/components/VoiceButton.tsx`
- Modify: `src/components/ChatWidget.tsx:199-225`
- Create: `src/__tests__/useSpeechRecognition.test.ts`
- Create: `src/__tests__/VoiceButton.test.tsx`

- [ ] **Step 1: Write the useSpeechRecognition hook**

Create `src/hooks/useSpeechRecognition.ts`:

```typescript
/**
 * Web Speech API hook for browser-native speech-to-text.
 *
 * Uses the SpeechRecognition API (webkitSpeechRecognition fallback).
 * Supports continuous listening and interim results.
 *
 * Browser support: Chrome, Edge, Safari (desktop). Firefox: degraded (text-only).
 */

import { useState, useCallback, useRef, useEffect } from 'react';

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message: string;
}

interface UseSpeechRecognitionReturn {
  isListening: boolean;
  transcript: string;
  interimTranscript: string;
  isSupported: boolean;
  error: string | null;
  startListening: (lang?: string) => void;
  stopListening: () => void;
  resetTranscript: () => void;
}

// Browser SpeechRecognition type
interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

const SpeechRecognitionConstructor =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export function useSpeechRecognition(): UseSpeechRecognitionReturn {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const isSupported = !!SpeechRecognitionConstructor;

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
    };
  }, []);

  const startListening = useCallback((lang: string = 'en-US') => {
    if (!isSupported) {
      setError('Speech recognition is not supported in this browser');
      return;
    }

    setError(null);
    setInterimTranscript('');

    const recognition: SpeechRecognitionInstance = new SpeechRecognitionConstructor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = lang;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }

      if (final) {
        setTranscript((prev) => prev + final);
      }
      setInterimTranscript(interim);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error !== 'aborted') {
        setError(`Speech recognition error: ${event.error}`);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  }, [isSupported]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsListening(false);
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript('');
    setInterimTranscript('');
  }, []);

  return {
    isListening,
    transcript,
    interimTranscript,
    isSupported,
    error,
    startListening,
    stopListening,
    resetTranscript,
  };
}
```

- [ ] **Step 2: Write the VoiceButton component**

Create `src/components/VoiceButton.tsx`:

```typescript
/**
 * Microphone button for voice input.
 *
 * Shows recording state with animated indicator.
 * On stop, returns the transcribed text via onTranscript callback.
 */

import React from 'react';
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
    return null; // Hide button if not supported
  }

  return (
    <div className={`voice-button-container ${className}`}>
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
        {/* Microphone icon */}
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
        {/* Recording indicator dot */}
        {isListening && (
          <span className="absolute top-0 right-0 w-2.5 h-2.5 bg-white rounded-full animate-ping" />
        )}
      </button>

      {/* Interim transcript preview */}
      {isListening && interimTranscript && (
        <p
          className="absolute bottom-full left-0 mb-1 text-xs text-gray-400 whitespace-nowrap"
          data-testid="interim-transcript"
        >
          {interimTranscript}...
        </p>
      )}

      {/* Error display */}
      {error && (
        <p className="text-xs text-red-500 mt-1" data-testid="voice-error">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Integrate VoiceButton into ChatWidget**

Edit `src/components/ChatWidget.tsx`. Add import at top (after line 13):

```typescript
import { VoiceButton } from './VoiceButton';
```

Replace the input area (lines 199-225) with:

```tsx
      {/* Input Area */}
      <div className="chat-input bg-white border-t border-gray-200 p-4 rounded-b-lg">
        <div className="flex items-end gap-3">
          {/* Voice Button */}
          <VoiceButton
            onTranscript={(text) => {
              setInput((prev) => (prev ? prev + ' ' + text : text));
              inputRef.current?.focus();
            }}
            disabled={!isConnected}
          />
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
            disabled={!isConnected}
            className="flex-1 resize-none rounded-lg border border-gray-300 px-4 py-3 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-all duration-200"
            data-testid="chat-input"
            rows={1}
            style={{ minHeight: '48px', maxHeight: '150px' }}
          />
          <button
            onClick={handleSend}
            disabled={!isConnected || !input.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold px-6 py-3 rounded-lg transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            data-testid="send-button"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          {isConnected ? 'Connected and ready to chat' : 'Connecting...'}
        </p>
      </div>
```

- [ ] **Step 4: Write tests for useSpeechRecognition**

Create `src/__tests__/useSpeechRecognition.test.ts`:

```typescript
import { renderHook, act } from '@testing-library/react';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';

// Mock SpeechRecognition API
const mockStart = jest.fn();
const mockStop = jest.fn();
const mockAbort = jest.fn();

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
    jest.clearAllMocks();
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
});
```

- [ ] **Step 5: Write tests for VoiceButton**

Create `src/__tests__/VoiceButton.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { VoiceButton } from '../components/VoiceButton';

// Mock the hook
jest.mock('../hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: jest.fn(),
}));

import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
const mockUseSpeechRecognition = useSpeechRecognition as jest.MockedFunction<typeof useSpeechRecognition>;

describe('VoiceButton', () => {
  const defaultHookReturn = {
    isListening: false,
    transcript: '',
    interimTranscript: '',
    isSupported: true,
    error: null,
    startListening: jest.fn(),
    stopListening: jest.fn(),
    resetTranscript: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseSpeechRecognition.mockReturnValue(defaultHookReturn);
  });

  it('should render microphone button', () => {
    render(<VoiceButton onTranscript={jest.fn()} />);
    expect(screen.getByTestId('voice-button')).toBeTruthy();
  });

  it('should not render when speech recognition is not supported', () => {
    mockUseSpeechRecognition.mockReturnValue({
      ...defaultHookReturn,
      isSupported: false,
    });
    const { container } = render(<VoiceButton onTranscript={jest.fn()} />);
    expect(container.innerHTML).toBe('');
  });

  it('should start listening on click', () => {
    render(<VoiceButton onTranscript={jest.fn()} lang="nl-NL" />);
    fireEvent.click(screen.getByTestId('voice-button'));
    expect(defaultHookReturn.startListening).toHaveBeenCalledWith('nl-NL');
  });

  it('should stop and call onTranscript on second click', () => {
    const onTranscript = jest.fn();
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
    render(<VoiceButton onTranscript={jest.fn()} disabled />);
    const button = screen.getByTestId('voice-button');
    expect(button).toBeDisabled();
  });
});
```

- [ ] **Step 6: Run frontend tests**

Run: `npm test -- --watchAll=false 2>&1 | tail -30`
Expected: All tests pass including new voice tests

- [ ] **Step 7: Commit**

```bash
git add src/hooks/useSpeechRecognition.ts src/components/VoiceButton.tsx src/components/ChatWidget.tsx src/__tests__/useSpeechRecognition.test.ts src/__tests__/VoiceButton.test.tsx
git commit -m "feat(voice): add browser-native Web Speech API voice input

VoiceButton component with mic toggle, interim transcript preview.
Integrated into ChatWidget next to send button. Supports en-US + nl-NL.
Pure frontend — no backend changes needed."
```

---

### Task 5: Upgrade WebSocket Connection Manager

**Files:**
- Modify: `backend/app/api/websocket.py:13-50`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Read current WebSocketManager**

Read `backend/app/api/websocket.py` to understand the current implementation.

- [ ] **Step 2: Add max_connections and heartbeat config to Settings**

Edit `backend/app/config.py` — add after the existing settings:

```python
    # WebSocket configuration
    websocket_max_connections: int = int(os.getenv("WEBSOCKET_MAX_CONNECTIONS", "300"))
    websocket_heartbeat_interval: int = int(os.getenv("WEBSOCKET_HEARTBEAT_INTERVAL", "30"))
    websocket_heartbeat_timeout: int = int(os.getenv("WEBSOCKET_HEARTBEAT_TIMEOUT", "300"))
```

- [ ] **Step 3: Add connection limit and oldest-eviction to WebSocketManager**

Edit `backend/app/api/websocket.py` — update the `__init__` and `connect` methods:

In `__init__`, add max_connections and connection timestamps:

```python
    def __init__(self):
        """Initialize WebSocket manager."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._max_connections = int(os.getenv("WEBSOCKET_MAX_CONNECTIONS", "300"))
        self._connection_order: list = []  # tracks connect order for eviction
```

Update `connect` to enforce limit with oldest-eviction:

```python
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept WebSocket connection and register client.

        If at capacity, evicts the oldest idle connection.
        """
        # Evict oldest if at capacity
        if len(self.active_connections) >= self._max_connections and client_id not in self.active_connections:
            if self._connection_order:
                oldest_id = self._connection_order.pop(0)
                await self._evict_client(oldest_id)

        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.connection_metadata[client_id] = {
                "connected_at": datetime.now(),
                "last_heartbeat": datetime.now(),
                "message_count": 0,
                "conversation_id": None,
            }
            if client_id not in self._connection_order:
                self._connection_order.append(client_id)
            logger.info(
                "Client connected",
                client_id=client_id,
                total_connections=len(self.active_connections),
            )
        except Exception as e:
            logger.error("Connection failed", client_id=client_id, error=str(e))
            raise
```

Add `_evict_client` method:

```python
    async def _evict_client(self, client_id: str):
        """Gracefully close and remove a client connection."""
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_json({"type": "error", "message": "Connection evicted: server at capacity"})
                await ws.close(code=1013, reason="Server full")
            except Exception:
                pass
        self.active_connections.pop(client_id, None)
        self.connection_metadata.pop(client_id, None)
        logger.info("Client evicted", client_id=client_id)
```

- [ ] **Step 4: Add disconnect cleanup for _connection_order**

In the existing `disconnect` method, also remove from `_connection_order`:

```python
    async def disconnect(self, client_id: str):
        """Disconnect and clean up client."""
        self.active_connections.pop(client_id, None)
        self.connection_metadata.pop(client_id, None)
        if client_id in self._connection_order:
            self._connection_order.remove(client_id)
```

- [ ] **Step 5: Run existing WebSocket tests**

Run: `cd backend && python -m pytest tests/test_websocket_manager.py tests/test_websocket_chat.py -v -x 2>&1 | tail -20`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/websocket.py backend/app/config.py
git commit -m "feat(ws): add connection limit 300 + oldest-eviction strategy

Supports 200+ concurrent WebSocket connections for KRL-Dutch project.
Evicts oldest idle connection when at capacity. Configurable via env vars."
```

---

### Task 6: Add Portfolio Page MVP

**Files:**
- Create: `src/pages/Portfolio.tsx`
- Modify: `src/App.tsx:46-50` (add route)
- Modify: `src/i18n/en.json`
- Modify: `src/i18n/zh.json`

- [ ] **Step 1: Read App.tsx routing structure**

Read `src/App.tsx` to understand route registration pattern and nav items.

- [ ] **Step 2: Create Portfolio page**

Create `src/pages/Portfolio.tsx`:

```typescript
/**
 * Portfolio showcase page.
 *
 * Displays Aureon's key metrics, tech stack, and demo screenshots
 * for Upwork proposals and client presentations.
 */

import { useTranslation } from 'react-i18next';

const METRICS = [
  { value: '96.5%', label: 'portfolio.metrics.recall', sub: 'Recall@3 (192 QA)' },
  { value: '0.901', label: 'portfolio.metrics.mrr', sub: 'Mean Reciprocal Rank' },
  { value: '0.914', label: 'portfolio.metrics.ndcg', sub: 'nDCG@10' },
  { value: '200+', label: 'portfolio.metrics.ws', sub: 'WebSocket Connections' },
];

const TECH_STACK = [
  { category: 'Frontend', items: ['React 19', 'TypeScript', 'Tailwind CSS', 'Vite'] },
  { category: 'Backend', items: ['Python 3.12', 'FastAPI', 'LangChain', 'LangGraph'] },
  { category: 'AI/ML', items: ['DeepSeek', 'OpenAI', 'Claude', 'BGE Embeddings'] },
  { category: 'Infrastructure', items: ['Docker', 'Redis', 'ChromaDB', 'Qdrant'] },
];

export function Portfolio() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      {/* Hero */}
      <section className="py-20 px-6 text-center" style={{ background: 'var(--bg-secondary)' }}>
        <h1 className="text-4xl font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
          {t('portfolio.hero.title')}
        </h1>
        <p className="text-xl mb-8" style={{ color: 'var(--text-secondary)' }}>
          {t('portfolio.hero.subtitle')}
        </p>
      </section>

      {/* Metrics */}
      <section className="py-16 px-6 max-w-6xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {METRICS.map((m) => (
            <div
              key={m.label}
              className="rounded-xl p-6 text-center shadow-sm"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
            >
              <div className="text-3xl font-bold mb-1" style={{ color: 'var(--accent)' }}>
                {m.value}
              </div>
              <div className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
                {t(m.label)}
              </div>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                {m.sub}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Tech Stack */}
      <section className="py-16 px-6 max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold mb-8 text-center" style={{ color: 'var(--text-primary)' }}>
          {t('portfolio.techStack')}
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {TECH_STACK.map((cat) => (
            <div
              key={cat.category}
              className="rounded-xl p-5"
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
            >
              <h3 className="font-semibold mb-3" style={{ color: 'var(--accent)' }}>
                {cat.category}
              </h3>
              <ul className="space-y-1.5">
                {cat.items.map((item) => (
                  <li key={item} className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Benchmark Link */}
      <section className="py-16 px-6 text-center">
        <a
          href="/benchmark"
          className="inline-block px-8 py-3 rounded-lg font-semibold text-white transition-colors"
          style={{ background: 'var(--accent)' }}
        >
          {t('portfolio.viewBenchmark')}
        </a>
      </section>
    </div>
  );
}

export default Portfolio;
```

- [ ] **Step 3: Add route and nav item in App.tsx**

Add lazy import (after line 21):

```typescript
const Portfolio = lazy(() => import("./pages/Portfolio").then(m => ({ default: m.Portfolio })));
```

Add to navItems array:

```typescript
    { path: "/portfolio", key: "app.nav.portfolio" },
```

Add route inside the Routes section (follow existing pattern).

- [ ] **Step 4: Add i18n keys**

Edit `src/i18n/en.json` — add:

```json
  "app.nav.portfolio": "Portfolio",
  "portfolio.hero.title": "Enterprise AI Knowledge Base Platform",
  "portfolio.hero.subtitle": "Production-grade RAG with verified benchmarks. 96.5% Recall, real-time streaming, enterprise-ready.",
  "portfolio.metrics.recall": "Recall@3",
  "portfolio.metrics.mrr": "MRR",
  "portfolio.metrics.ndcg": "nDCG@10",
  "portfolio.metrics.ws": "WebSocket",
  "portfolio.techStack": "Technology Stack",
  "portfolio.viewBenchmark": "View Full Benchmark Results"
```

Edit `src/i18n/zh.json` — add:

```json
  "app.nav.portfolio": "作品集",
  "portfolio.hero.title": "企业 AI 知识库平台",
  "portfolio.hero.subtitle": "Production 级 RAG 系统，可验证的 Benchmark 数据。96.5% 召回率，实时流式，企业就绪。",
  "portfolio.metrics.recall": "召回率@3",
  "portfolio.metrics.mrr": "MRR",
  "portfolio.metrics.ndcg": "nDCG@10",
  "portfolio.metrics.ws": "WebSocket",
  "portfolio.techStack": "技术栈",
  "portfolio.viewBenchmark": "查看完整 Benchmark 结果"
```

- [ ] **Step 5: Run frontend build check**

Run: `npm run build 2>&1 | tail -10`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add src/pages/Portfolio.tsx src/App.tsx src/i18n/en.json src/i18n/zh.json
git commit -m "feat(portfolio): add MVP portfolio page with metrics and tech stack

/showcase page for Upwork proposals. Displays 4 key metrics (96.5% Recall,
0.901 MRR, 0.914 nDCG, 200+ WS), tech stack grid, and benchmark link."
```

---

### Task 7: Add Environment Variables

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add new config fields to Settings**

Edit `backend/app/config.py` — add to the Settings class:

```python
    # Concurrency limits
    queue_timeout_seconds: float = 30.0
    llm_semaphore_deepseek: int = 30
    llm_semaphore_embedding: int = 50
    rag_semaphore: int = 40

    # CRAG confidence thresholds (Track 2, prepare now)
    crag_high_confidence: float = 0.05
    crag_low_confidence: float = 0.01
    crag_ambiguous_threshold: float = 0.03
    crag_enabled: bool = False  # enable after Track 2 Task 1

    # Post-generation reflection (Track 2, prepare now)
    reflection_enabled: bool = False  # enable after Track 2 Task 4
```

- [ ] **Step 2: Update .env.example**

Add to `backend/.env.example`:

```env
# ── Concurrency Limits ──
QUEUE_TIMEOUT_SECONDS=30
LLM_SEMAPHORE_DEEPSEEK=30
LLM_SEMAPHORE_EMBEDDING=50
RAG_SEMAPHORE=40

# ── CRAG Confidence Gating (disabled by default, enable after tuning) ──
CRAG_ENABLED=false
CRAG_HIGH_CONFIDENCE=0.05
CRAG_LOW_CONFIDENCE=0.01
CRAG_AMBIGUOUS_THRESHOLD=0.03

# ── Post-Generation Reflection (disabled by default) ──
REFLECTION_ENABLED=false

# ── WebSocket ──
WEBSOCKET_MAX_CONNECTIONS=300
WEBSOCKET_HEARTBEAT_INTERVAL=30
```

- [ ] **Step 3: Run backend tests to verify no breakage**

Run: `cd backend && python -m pytest tests/test_dependencies.py tests/test_config.py -v 2>&1 | tail -10`
Expected: Tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/.env.example
git commit -m "chore(config): add concurrency, CRAG, and reflection env vars

Prepares config for Track 2 optimization tasks. CRAG and reflection disabled
by default — will be enabled after threshold tuning."
```

---

## Track 2: Deep Optimization (Week 1-3)

### Task 8: CRAG Retrieval Confidence Gating

**Files:**
- Create: `backend/app/rag/retrieval_confidence.py`
- Create: `backend/tests/test_retrieval_confidence.py`
- Modify: `backend/app/rag/qa_chain.py:720-776`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_retrieval_confidence.py`:

```python
"""Tests for CRAG retrieval confidence gating."""
import pytest
from app.rag.retrieval_confidence import (
    evaluate_retrieval_confidence,
    build_answer_with_confidence,
)


class TestEvaluateRetrievalConfidence:
    """Test confidence evaluation against top RRF scores."""

    def test_empty_chunks_returns_incorrect(self):
        assert evaluate_retrieval_confidence([]) == "incorrect"

    def test_high_score_returns_correct(self):
        chunks = [{"score": 0.10, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "correct"

    def test_medium_score_returns_ambiguous(self):
        chunks = [{"score": 0.03, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "ambiguous"

    def test_low_score_returns_incorrect(self):
        chunks = [{"score": 0.005, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "incorrect"

    def test_boundary_high_confidence(self):
        chunks = [{"score": 0.05, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "correct"

    def test_boundary_low_confidence(self):
        chunks = [{"score": 0.01, "text": "test"}]
        assert evaluate_retrieval_confidence(chunks) == "ambiguous"


class TestBuildAnswerWithConfidence:
    """Test answer wrapping with confidence markers."""

    def test_correct_returns_original(self):
        assert build_answer_with_confidence("answer text", "correct", "en") == "answer text"

    def test_ambiguous_prepends_warning_en(self):
        result = build_answer_with_confidence("answer text", "ambiguous", "en")
        assert "limited" in result.lower()
        assert "answer text" in result

    def test_ambiguous_prepends_warning_zh(self):
        result = build_answer_with_confidence("答案内容", "ambiguous", "zh")
        assert "不完整" in result
        assert "答案内容" in result

    def test_incorrect_returns_fallback_en(self):
        result = build_answer_with_confidence("answer text", "incorrect", "en")
        assert "not find" in result.lower() or "no relevant" in result.lower()

    def test_incorrect_returns_fallback_zh(self):
        result = build_answer_with_confidence("答案内容", "incorrect", "zh")
        assert "没有找到" in result or "暂无相关" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_retrieval_confidence.py -v -x 2>&1 | tail -10`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement retrieval_confidence.py**

Create `backend/app/rag/retrieval_confidence.py`:

```python
"""CRAG-style retrieval quality confidence gating.

After retrieval, evaluates the top RRF score to determine retrieval quality:
- 'correct': high confidence, proceed to generation
- 'ambiguous': medium confidence, generate with uncertainty marker
- 'incorrect': low confidence, refuse to answer

Based on CRAG (arXiv:2401.15884) three-way branching.

Reference: docs/RAG_OPTIMIZATION_PROMPT.md §2.2
"""

import os
from typing import List, Dict, Any

import structlog

logger = structlog.get_logger()

CRAG_HIGH_CONFIDENCE = float(os.getenv("CRAG_HIGH_CONFIDENCE", "0.05"))
CRAG_LOW_CONFIDENCE = float(os.getenv("CRAG_LOW_CONFIDENCE", "0.01"))


def evaluate_retrieval_confidence(chunks: List[Dict[str, Any]]) -> str:
    """Evaluate retrieval quality based on top RRF score.

    Args:
        chunks: Retrieved chunks with 'score' field (RRF or reranker score)

    Returns:
        'correct' | 'ambiguous' | 'incorrect'
    """
    if not chunks:
        return "incorrect"

    top_score = chunks[0].get("score", 0)

    if top_score >= CRAG_HIGH_CONFIDENCE:
        return "correct"
    elif top_score >= CRAG_LOW_CONFIDENCE:
        return "ambiguous"
    else:
        return "incorrect"


def build_answer_with_confidence(answer: str, confidence: str, lang: str = "en") -> str:
    """Wrap answer with confidence marker based on retrieval quality.

    Args:
        answer: Generated answer text
        confidence: One of 'correct', 'ambiguous', 'incorrect'
        lang: Language code ('en' or 'zh')

    Returns:
        Answer with optional confidence warning prepended
    """
    if confidence == "correct":
        return answer

    if confidence == "ambiguous":
        if lang == "zh":
            return f"⚠️ 以下回答基于有限的参考信息，可能不完整：\n\n{answer}"
        return f"⚠️ The following answer is based on limited reference information and may be incomplete:\n\n{answer}"

    # incorrect
    if lang == "zh":
        return "抱歉，知识库中没有找到与您问题相关的信息。请尝试换个问法，或联系管理员确认知识库是否已覆盖该主题。"
    return "Sorry, no relevant information was found in the knowledge base. Please try rephrasing your question or contact the administrator to confirm coverage."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_retrieval_confidence.py -v -x 2>&1 | tail -15`
Expected: All 10 tests PASS

- [ ] **Step 5: Integrate CRAG into rag_query (qa_chain.py)**

Edit `backend/app/rag/qa_chain.py`. Add import at top:

```python
from app.rag.retrieval_confidence import evaluate_retrieval_confidence, build_answer_with_confidence
```

Add CRAG config variable (near other env vars):

```python
_CRAG_ENABLED = os.getenv("CRAG_ENABLED", "false").lower() == "true"
```

In `rag_query` (around line 767, after `if not chunks:` block), add CRAG check:

```python
    # 2b. CRAG confidence gating: evaluate retrieval quality
    if _CRAG_ENABLED and chunks:
        confidence = evaluate_retrieval_confidence(chunks)
        if confidence == "incorrect":
            return RAGQueryResponse(
                answer=build_answer_with_confidence("", "incorrect", lang),
                sources=[],
            )
```

In `rag_query` (after `answer = generate_answer(...)` on line 782), wrap answer:

```python
    # 3b. CRAG: wrap answer with confidence marker
    if _CRAG_ENABLED and chunks:
        confidence = evaluate_retrieval_confidence(chunks)
        answer = build_answer_with_confidence(answer, confidence, lang)
```

Apply the same pattern to `rag_query_async` (around line 1546) and `rag_query_astream` (around line 837).

- [ ] **Step 6: Run RAG quality tests**

Run: `cd backend && python -m pytest tests/test_rag_quality.py -v -x 2>&1 | tail -20`
Expected: All tests pass (CRAG is disabled by default)

- [ ] **Step 7: Commit**

```bash
git add backend/app/rag/retrieval_confidence.py backend/tests/test_retrieval_confidence.py backend/app/rag/qa_chain.py
git commit -m "feat(rag): add CRAG retrieval confidence gating

Three-way branching: correct (score>=0.05) / ambiguous (>=0.01) / incorrect.
Disabled by default (CRAG_ENABLED=false) — enable after threshold tuning.
Based on CRAG paper (arXiv:2401.15884)."
```

---

### Task 9: LLM Multi-Query Expansion

**Files:**
- Create: `backend/app/rag/multi_query_llm.py`
- Create: `backend/tests/test_multi_query_llm.py`
- Modify: `backend/app/rag/qa_chain.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_multi_query_llm.py`:

```python
"""Tests for LLM-based multi-query expansion."""
import pytest
import json
from unittest.mock import AsyncMock
from app.rag.multi_query_llm import multi_query_llm_rewrite, decompose_complex_query


class TestMultiQueryLLMRewrite:
    """Test LLM multi-query expansion."""

    @pytest.mark.asyncio
    async def test_returns_original_plus_variants(self):
        """Should return [original] + N variants."""
        mock_llm = AsyncMock(return_value=json.dumps([
            "BM25 keyword retrieval explained",
            "How BM25 scoring works",
        ]))
        result = await multi_query_llm_rewrite("What is BM25?", mock_llm, n_variants=2)
        assert len(result) == 3
        assert result[0] == "What is BM25?"

    @pytest.mark.asyncio
    async def test_deduplicates_original(self):
        """Should not include original query in variants."""
        mock_llm = AsyncMock(return_value=json.dumps([
            "What is BM25?",
            "BM25 explained",
        ]))
        result = await multi_query_llm_rewrite("What is BM25?", mock_llm, n_variants=2)
        assert result.count("What is BM25?") == 1

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self):
        """Should return [original] when LLM returns invalid JSON."""
        mock_llm = AsyncMock(return_value="not json")
        result = await multi_query_llm_rewrite("test query", mock_llm)
        assert result == ["test query"]

    @pytest.mark.asyncio
    async def test_limits_variants(self):
        """Should limit to n_variants."""
        mock_llm = AsyncMock(return_value=json.dumps(["v1", "v2", "v3", "v4"]))
        result = await multi_query_llm_rewrite("test", mock_llm, n_variants=2)
        assert len(result) <= 3  # original + 2 variants


class TestDecomposeComplexQuery:
    """Test complex query decomposition."""

    @pytest.mark.asyncio
    async def test_returns_sub_queries(self):
        """Should return list of sub-queries."""
        mock_llm = AsyncMock(return_value=json.dumps([
            "What is LangChain?",
            "What is LlamaIndex?",
            "LangChain vs LlamaIndex performance",
        ]))
        result = await decompose_complex_query(
            "Compare LangChain and LlamaIndex", mock_llm
        )
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        """Should return [original] on LLM error."""
        mock_llm = AsyncMock(side_effect=Exception("API error"))
        result = await decompose_complex_query("complex query", mock_llm)
        assert result == ["complex query"]

    @pytest.mark.asyncio
    async def test_limits_sub_queries(self):
        """Should limit to max_sub_queries."""
        mock_llm = AsyncMock(return_value=json.dumps([f"q{i}" for i in range(10)]))
        result = await decompose_complex_query("test", mock_llm, max_sub_queries=3)
        assert len(result) <= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_multi_query_llm.py -v -x 2>&1 | tail -10`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement multi_query_llm.py**

Create `backend/app/rag/multi_query_llm.py`:

```python
"""LLM-based multi-query expansion for cross-article retrieval.

Generates semantic variants of the user query to improve recall
when the query spans multiple documents.

Based on MultiQueryRetriever pattern (LangChain) and Adaptive-RAG (NAACL 2024).

Reference: docs/RAG_OPTIMIZATION_PROMPT.md §4.2
"""

import json
from typing import List, Callable, Awaitable

import structlog

logger = structlog.get_logger()


async def multi_query_llm_rewrite(
    query: str,
    llm_call_fn: Callable[..., Awaitable[str]],
    n_variants: int = 3,
) -> List[str]:
    """Generate N semantic variants of the query via LLM.

    Args:
        query: Original user query
        llm_call_fn: Async LLM function (prompt string -> response string)
        n_variants: Number of variants to generate

    Returns:
        [original_query] + up to n_variants unique variants
    """
    prompt = (
        f"将以下问题改写为 {n_variants} 个不同的表述，保持语义一致但用词和角度不同。\n"
        f"每个变体应该能独立用于检索，找到与原始问题相关的信息。\n"
        f"只返回 JSON 数组格式，不要其他内容。\n\n"
        f"原始问题: {query}\n\n"
        f"示例:\n"
        f'输入: "对比 BM25 和向量检索的优缺点"\n'
        f'输出: ["BM25 关键词检索的优势和局限性", "向量语义检索的性能特点", "BM25 vs Vector Search 各自适用场景"]'
    )

    try:
        resp = await llm_call_fn(prompt)
        variants = json.loads(str(resp))
        if not isinstance(variants, list):
            return [query]
        # Deduplicate against original
        result = [query]
        for v in variants:
            v = str(v).strip()
            if v and v != query and v not in result:
                result.append(v)
            if len(result) >= n_variants + 1:
                break
        return result
    except (json.JSONDecodeError, TypeError, Exception) as e:
        logger.warning("Multi-query LLM rewrite failed: %s, using original", e)
        return [query]


async def decompose_complex_query(
    query: str,
    llm_call_fn: Callable[..., Awaitable[str]],
    max_sub_queries: int = 5,
) -> List[str]:
    """Break a complex/comparative query into independent sub-queries.

    Each sub-query can be independently retrieved and answered.

    Args:
        query: Complex user query
        llm_call_fn: Async LLM function
        max_sub_queries: Maximum number of sub-queries

    Returns:
        List of sub-queries (may include original if decomposition fails)
    """
    prompt = (
        f"将以下复杂问题拆解为 {max_sub_queries} 个独立的子问题，每个子问题可以单独检索回答。\n"
        f"子问题应该覆盖原始问题的不同方面。\n"
        f"只返回 JSON 数组格式，不要其他内容。\n\n"
        f"原始问题: {query}\n\n"
        f"示例:\n"
        f'输入: "对比 LangChain 和 LlamaIndex 在 RAG 场景中的优缺点"\n'
        f'输出: ["LangChain 在 RAG 场景中的主要优势是什么？", "LlamaIndex 在 RAG 场景中的主要优势是什么？", "LangChain 和 LlamaIndex 的性能对比如何？"]'
    )

    try:
        resp = await llm_call_fn(prompt)
        sub_queries = json.loads(str(resp))
        if not isinstance(sub_queries, list):
            return [query]
        result = [str(q).strip() for q in sub_queries[:max_sub_queries] if str(q).strip()]
        return result if result else [query]
    except (json.JSONDecodeError, TypeError, Exception) as e:
        logger.warning("Query decomposition failed: %s, using original", e)
        return [query]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_multi_query_llm.py -v -x 2>&1 | tail -15`
Expected: All 7 tests PASS

- [ ] **Step 5: Integrate into multi_query_retrieve (qa_chain.py)**

Edit `backend/app/rag/qa_chain.py`. Add import:

```python
from app.rag.multi_query_llm import multi_query_llm_rewrite
```

Add config variable:

```python
_MULTI_QUERY_LLM_ENABLED = os.getenv("MULTI_QUERY_LLM_ENABLED", "false").lower() == "true"
```

In `multi_query_retrieve` (around line 532), after `variants = expand_queries_rules(query)`, add LLM expansion:

```python
    # LLM-based multi-query expansion (when enabled)
    if _MULTI_QUERY_LLM_ENABLED:
        try:
            # Note: llm_call_fn not available in sync path; use in async variants
            logger.info("Multi-query LLM expansion: using rule-based only in sync path")
        except Exception as e:
            logger.warning("LLM multi-query failed: %s", e)
```

In `hybrid_retrieve_async` or the async RAG paths, integrate the LLM expansion with the async llm_call_fn. This requires passing llm_call_fn into the retrieval function — add it as an optional parameter:

```python
async def multi_query_retrieve_async(
    query: str,
    top_k: int = 3,
    lang_filter: str = None,
    llm_call_fn=None,
) -> List[Dict[str, Any]]:
    """Async multi-query retrieval with optional LLM expansion."""
    import asyncio

    variants = expand_queries_rules(query)

    # LLM expansion for cross-article queries
    if _MULTI_QUERY_LLM_ENABLED and llm_call_fn and is_cross_article_query(query):
        try:
            llm_variants = await multi_query_llm_rewrite(query, llm_call_fn, n_variants=2)
            variants = list(dict.fromkeys(variants + llm_variants))[:6]
            logger.info("Multi-query LLM: expanded to %d variants", len(variants))
        except Exception as e:
            logger.warning("LLM multi-query failed: %s, using rule-based only", e)

    # Parallel retrieval for all variants
    import asyncio
    all_results = await asyncio.gather(*[
        hybrid_retrieve_async(v, top_k=top_k * 2, lang_filter=lang_filter)
        for v in variants
    ])

    # RRF fusion + diversity selection (same logic as existing multi_query_retrieve)
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict] = {}

    def _doc_key(doc: Dict) -> str:
        return doc.get("metadata", {}).get("slug", "") or doc.get("text", "")[:50]

    for variant_results in all_results:
        seen: Dict[str, int] = {}
        deduped = []
        for rank, doc in enumerate(variant_results, 1):
            key = _doc_key(doc)
            if key not in seen:
                seen[key] = rank
                deduped.append(doc)
        for rank, doc in enumerate(deduped, 1):
            key = _doc_key(doc)
            rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
            if key not in doc_map:
                doc_map[key] = doc

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    candidates = []
    for key, score in ranked:
        doc = doc_map[key].copy()
        doc["score"] = score
        candidates.append(doc)

    # Diversity selection
    selected = []
    seen_slugs = set()
    for doc in candidates:
        slug = doc.get("metadata", {}).get("slug", "")
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            selected.append(doc)
            if len(selected) >= top_k:
                break
    if len(selected) < top_k:
        for doc in candidates:
            if doc not in selected:
                selected.append(doc)
                if len(selected) >= top_k:
                    break

    if selected and selected[0].get("score", 0) < _MIN_RELEVANCE_SCORE:
        return []

    return selected
```

- [ ] **Step 6: Run all RAG tests**

Run: `cd backend && python -m pytest tests/test_rag_quality.py tests/test_rag_router.py -v -x 2>&1 | tail -20`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/rag/multi_query_llm.py backend/tests/test_multi_query_llm.py backend/app/rag/qa_chain.py
git commit -m "feat(rag): add LLM Multi-Query Expansion for cross-article retrieval

Generates semantic variants via LLM for better cross-article recall.
Disabled by default (MULTI_QUERY_LLM_ENABLED=false).
Based on MultiQueryRetriever + Adaptive-RAG (NAACL 2024)."
```

---

### Task 10: Post-Generation Self-Reflection

**Files:**
- Create: `backend/app/rag/post_generation_reflection.py`
- Create: `backend/tests/test_post_generation_reflection.py`
- Modify: `backend/app/rag/qa_chain.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_post_generation_reflection.py`:

```python
"""Tests for post-generation self-reflection (Self-RAG style)."""
import pytest
from unittest.mock import AsyncMock
from app.rag.post_generation_reflection import (
    reflect_on_answer,
    wrap_answer_with_reflection,
)


class TestReflectOnAnswer:
    """Test LLM-based answer reflection."""

    @pytest.mark.asyncio
    async def test_supported_returns_supported(self):
        mock_llm = AsyncMock(return_value="SUPPORTED")
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "supported"

    @pytest.mark.asyncio
    async def test_not_supported_returns_not_supported(self):
        mock_llm = AsyncMock(return_value="NOT_SUPPORTED")
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "not_supported"

    @pytest.mark.asyncio
    async def test_partial_returns_partial(self):
        mock_llm = AsyncMock(return_value="PARTIAL")
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "partial"

    @pytest.mark.asyncio
    async def test_error_defaults_to_supported(self):
        mock_llm = AsyncMock(side_effect=Exception("API error"))
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "supported"


class TestWrapAnswerWithReflection:
    """Test answer wrapping with reflection markers."""

    def test_supported_returns_original(self):
        result = wrap_answer_with_reflection("answer", "supported", "en")
        assert result == "answer"

    def test_not_supported_adds_warning_en(self):
        result = wrap_answer_with_reflection("answer", "not_supported", "en")
        assert "not fully supported" in result.lower()

    def test_partial_adds_note_zh(self):
        result = wrap_answer_with_reflection("答案", "partial", "zh")
        assert "不完整" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_post_generation_reflection.py -v -x 2>&1 | tail -10`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement post_generation_reflection.py**

Create `backend/app/rag/post_generation_reflection.py`:

```python
"""Post-generation self-reflection for RAG answers.

After generating an answer, verifies that each key claim is supported
by the reference documents. Based on Self-RAG (ICLR 2024) Reflection Tokens.

Reference: docs/RAG_OPTIMIZATION_PROMPT.md §2.2 Layer 4
"""

import os
from typing import Callable, Awaitable

import structlog

logger = structlog.get_logger()

_SELF_REFLECTION_PROMPT = """判断以下回答是否被参考文档充分支撑。

用户问题：{query}
参考文档：{context}
生成的回答：{answer}

规则：
1. 如果回答中的每个关键论断都能在参考文档中找到依据，回答 SUPPORTED
2. 如果回答包含推测、编造或文档中没有的信息，回答 NOT_SUPPORTED
3. 如果回答虽然正确但遗漏了重要信息，回答 PARTIAL

只回答 SUPPORTED / NOT_SUPPORTED / PARTIAL，不要其他内容。"""


async def reflect_on_answer(
    query: str,
    context: str,
    answer: str,
    llm_call_fn: Callable[..., Awaitable[str]],
) -> str:
    """Verify answer fidelity against reference documents.

    Args:
        query: User query
        context: Reference document context
        answer: Generated answer
        llm_call_fn: Async LLM function

    Returns:
        'supported' | 'not_supported' | 'partial'
    """
    prompt = _SELF_REFLECTION_PROMPT.format(
        query=query, context=context[:2000], answer=answer[:500]
    )

    try:
        response = await llm_call_fn(prompt)
        response_upper = str(response).strip().upper()
        if "NOT_SUPPORTED" in response_upper:
            return "not_supported"
        elif "PARTIAL" in response_upper:
            return "partial"
        else:
            return "supported"
    except Exception as e:
        logger.warning("Self-reflection failed: %s, defaulting to supported", e)
        return "supported"


def wrap_answer_with_reflection(answer: str, reflection: str, lang: str = "en") -> str:
    """Wrap answer with reflection confidence marker.

    Args:
        answer: Original generated answer
        reflection: Reflection result ('supported', 'not_supported', 'partial')
        lang: Language code

    Returns:
        Answer with optional warning prepended
    """
    if reflection == "supported":
        return answer

    if reflection == "not_supported":
        if lang == "zh":
            return f"⚠️ 以下回答可能包含参考文档未支撑的信息，请谨慎参考：\n\n{answer}"
        return f"⚠️ The following answer may contain information not supported by the reference documents. Please verify independently:\n\n{answer}"

    # partial
    if lang == "zh":
        return f"⚠️ 以下回答基于参考文档，但可能遗漏了部分信息：\n\n{answer}"
    return f"⚠️ The following answer is based on reference documents but may be incomplete:\n\n{answer}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_post_generation_reflection.py -v -x 2>&1 | tail -15`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/post_generation_reflection.py backend/tests/test_post_generation_reflection.py
git commit -m "feat(rag): add post-generation self-reflection (Self-RAG style)

Verifies answer fidelity against reference docs via LLM classification.
Three outcomes: supported / not_supported / partial.
Disabled by default (REFLECTION_ENABLED=false)."
```

---

### Task 11: Question Type Adaptive Prompt

**Files:**
- Modify: `backend/app/rag/qa_chain.py:654-670` (generate_answer function)

- [ ] **Step 1: Add query type instruction map**

Add above `generate_answer` in `backend/app/rag/qa_chain.py`:

```python
# ── Query type adaptive instructions ──
_QUERY_TYPE_INSTRUCTIONS = {
    "factual": {
        "zh": "给出明确的事实答案（时间、名称、数字）。一句话回答即可。",
        "en": "Give a clear factual answer (dates, names, numbers). One sentence is sufficient.",
    },
    "comparison": {
        "zh": "用表格或并列结构对比各项差异。每个维度直接回应用户关心的方面。",
        "en": "Use a table or parallel structure to compare differences. Each dimension should directly address what the user cares about.",
    },
    "how_to": {
        "zh": "给出清晰的步骤列表。每步操作直接可执行。",
        "en": "Provide a clear step-by-step list. Each step should be directly actionable.",
    },
    "reasoning": {
        "zh": "给出推理过程和结论。每个推理步骤都要有文档依据。",
        "en": "Provide reasoning process and conclusion. Each reasoning step should have document evidence.",
    },
}
```

- [ ] **Step 2: Update generate_answer to inject type instruction**

Modify `generate_answer` to accept an optional `query_type` parameter:

```python
def generate_answer(
    query: str,
    context: str,
    llm_call_fn,
    system_prompt: str = None,
    lang: str = "zh",
    query_type: str = None,
) -> str:
    """Call LLM with context and query. Return generated answer."""
    if system_prompt is None:
        system_prompt = QA_SYSTEM_PROMPT_EN if lang == "en" else QA_SYSTEM_PROMPT
    lang_instr = lang_instruction(lang).strip()

    # Inject query type instruction if available
    type_instruction = ""
    if query_type and query_type in _QUERY_TYPE_INSTRUCTIONS:
        type_instruction = "\n" + _QUERY_TYPE_INSTRUCTIONS[query_type].get(lang, "")

    prompt = system_prompt.format(context=context, lang_instruction=lang_instr + type_instruction)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query},
    ]
    return llm_call_fn(messages)
```

- [ ] **Step 3: Run existing RAG tests**

Run: `cd backend && python -m pytest tests/test_rag_quality.py -v -x 2>&1 | tail -20`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat(rag): add query-type adaptive prompt instructions

Injects type-specific instructions (factual/comparison/how_to/reasoning)
into the QA prompt based on query classification."
```

---

### Task 12: Gunicorn Multi-Worker Deployment

**Files:**
- Create: `deploy/digitalocean/Dockerfile.gunicorn`
- Create: `deploy/digitalocean/docker-compose.prod.yml`
- Create: `deploy/digitalocean/nginx.conf`
- Create: `deploy/digitalocean/deploy.sh`

- [ ] **Step 1: Create Gunicorn Dockerfile**

Create `deploy/digitalocean/Dockerfile.gunicorn`:

```dockerfile
# ── Aureon Backend: Gunicorn + Uvicorn Multi-Worker ──
FROM python:3.12-slim AS backend

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 nginx certbot python3-certbot-nginx \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Pre-download embedding model
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    || HF_ENDPOINT=https://hf-mirror.com python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

COPY backend/ .
RUN mkdir -p /app/data/vectors

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["gunicorn", "app.main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "50"]
```

- [ ] **Step 2: Create production docker-compose**

Create `deploy/digitalocean/docker-compose.prod.yml`:

```yaml
version: "3.8"

services:
  backend:
    build:
      context: ../..
      dockerfile: deploy/digitalocean/Dockerfile.gunicorn
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - WEBSOCKET_MAX_CONNECTIONS=300
      - RAG_SEMAPHORE=40
      - LLM_SEMAPHORE_DEEPSEEK=30
    depends_on:
      - redis
    volumes:
      - aureon-data:/app/data
    restart: unless-stopped

  redis:
    image: redis/redis-stack-server:latest
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped

  frontend:
    build:
      context: ../..
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  aureon-data:
  redis-data:
```

- [ ] **Step 3: Create Nginx config**

Create `deploy/digitalocean/nginx.conf`:

```nginx
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name _;

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # API proxy
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }

    # Frontend
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 4: Create deploy script**

Create `deploy/digitalocean/deploy.sh`:

```bash
#!/bin/bash
# One-click DigitalOcean deployment script
# Usage: ./deploy.sh <droplet-ip> <domain>

set -euo pipefail

DROPLET_IP="${1:?Usage: ./deploy.sh <droplet-ip> <domain>}"
DOMAIN="${2:?Usage: ./deploy.sh <droplet-ip> <domain>}"

echo "=== Aureon DigitalOcean Deployment ==="
echo "Target: $DROPLET_IP ($DOMAIN)"

# 1. Copy files
echo "[1/5] Copying project files..."
rsync -avz --exclude node_modules --exclude .git --exclude __pycache__ \
    ./ root@$DROPLET_IP:/opt/aureon/

# 2. Build and start
echo "[2/5] Building Docker images..."
ssh root@$DROPLET_IP "cd /opt/aureon && docker compose -f deploy/digitalocean/docker-compose.prod.yml build"

# 3. Start services
echo "[3/5] Starting services..."
ssh root@$DROPLET_IP "cd /opt/aureon && docker compose -f deploy/digitalocean/docker-compose.prod.yml up -d"

# 4. Setup SSL
echo "[4/5] Setting up SSL with Let's Encrypt..."
ssh root@$DROPLET_IP "certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || true"

# 5. Verify
echo "[5/5] Verifying deployment..."
sleep 10
HTTP_CODE=$(ssh root@$DROPLET_IP "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/health" || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "=== Deployment successful! ==="
    echo "Frontend: https://$DOMAIN"
    echo "API: https://$DOMAIN/api/"
    echo "WebSocket: wss://$DOMAIN/ws/chat/"
else
    echo "WARNING: Health check returned $HTTP_CODE. Check logs with:"
    echo "  ssh root@$DROPLET_IP 'cd /opt/aureon && docker compose -f deploy/digitalocean/docker-compose.prod.yml logs -f'"
fi
```

- [ ] **Step 5: Make deploy script executable**

Run: `chmod +x deploy/digitalocean/deploy.sh`

- [ ] **Step 6: Verify Dockerfile builds**

Run: `cd "C:/Users/Yum/Desktop/Aureon-test" && docker build -f deploy/digitalocean/Dockerfile.gunicorn -t aureon-test . 2>&1 | tail -10`
Expected: Build succeeds (or fails gracefully if Docker not available — that's OK for this step)

- [ ] **Step 7: Commit**

```bash
git add deploy/digitalocean/
git commit -m "feat(deploy): add DigitalOcean production deployment scripts

Gunicorn 4-worker Dockerfile, docker-compose.prod.yml, Nginx WebSocket proxy,
one-click deploy.sh script with SSL setup."
```

---

### Task 13: Threshold Auto-Tuning Script

**Files:**
- Create: `backend/app/rag/threshold_tuner.py`
- Create: `backend/tests/test_threshold_tuner.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_threshold_tuner.py`:

```python
"""Tests for CRAG threshold auto-tuning via grid search."""
import pytest
from app.rag.threshold_tuner import (
    ThresholdConfig,
    evaluate_thresholds,
    grid_search_thresholds,
)


class TestThresholdConfig:
    def test_default_values(self):
        cfg = ThresholdConfig()
        assert cfg.high == 0.05
        assert cfg.low == 0.01

    def test_custom_values(self):
        cfg = ThresholdConfig(high=0.10, low=0.02)
        assert cfg.high == 0.10


class TestEvaluateThresholds:
    def test_perfect_classification(self):
        """All positives above high, all negatives below low."""
        positive_scores = [0.10, 0.08, 0.06]
        negative_scores = [0.005, 0.003, 0.001]
        cfg = ThresholdConfig(high=0.05, low=0.01)
        result = evaluate_thresholds(cfg, positive_scores, negative_scores)
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_partial_classification(self):
        """Some positives in ambiguous zone."""
        positive_scores = [0.10, 0.03, 0.005]
        negative_scores = [0.001, 0.002]
        cfg = ThresholdConfig(high=0.05, low=0.01)
        result = evaluate_thresholds(cfg, positive_scores, negative_scores)
        assert 0 < result["f1"] < 1.0


class TestGridSearch:
    def test_returns_best_config(self):
        """Grid search should return config with highest F1."""
        positive_scores = [0.10, 0.08, 0.06, 0.04, 0.02]
        negative_scores = [0.005, 0.003, 0.001]
        result = grid_search_thresholds(positive_scores, negative_scores)
        assert isinstance(result, ThresholdConfig)
        assert result.high > result.low
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_threshold_tuner.py -v -x 2>&1 | tail -10`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement threshold_tuner.py**

Create `backend/app/rag/threshold_tuner.py`:

```python
"""CRAG threshold auto-tuning via grid search.

Optimizes high/low confidence thresholds for retrieval confidence gating
using existing negative QA pairs from the benchmark dataset.

Reference: docs/RAG_OPTIMIZATION_PROMPT.md §2.4
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ThresholdConfig:
    high: float = 0.05
    low: float = 0.01


def evaluate_thresholds(
    config: ThresholdConfig,
    positive_scores: List[float],
    negative_scores: List[float],
) -> Dict[str, float]:
    """Evaluate classification metrics for given thresholds.

    Args:
        config: Threshold values
        positive_scores: RRF scores from answerable queries (should be classified as 'correct' or 'ambiguous')
        negative_scores: RRF scores from unanswerable queries (should be classified as 'incorrect')

    Returns:
        Dict with precision, recall, f1 keys
    """
    # True positives: positive scores correctly classified (>= low threshold)
    tp = sum(1 for s in positive_scores if s >= config.low)
    # False negatives: positive scores incorrectly classified as incorrect
    fn = sum(1 for s in positive_scores if s < config.low)
    # True negatives: negative scores correctly classified (< low threshold)
    tn = sum(1 for s in negative_scores if s < config.low)
    # False positives: negative scores incorrectly classified as answerable
    fp = sum(1 for s in negative_scores if s >= config.low)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}


def grid_search_thresholds(
    positive_scores: List[float],
    negative_scores: List[float],
) -> ThresholdConfig:
    """Grid search over threshold combinations to maximize F1.

    Args:
        positive_scores: Scores from answerable queries
        negative_scores: Scores from unanswerable queries

    Returns:
        ThresholdConfig with best F1 score
    """
    best_config = ThresholdConfig()
    best_f1 = -1.0

    for high in [0.03, 0.05, 0.07, 0.10]:
        for low in [0.005, 0.01, 0.02]:
            if low >= high:
                continue
            cfg = ThresholdConfig(high=high, low=low)
            metrics = evaluate_thresholds(cfg, positive_scores, negative_scores)
            if metrics["f1"] > best_f1:
                best_f1 = metrics["f1"]
                best_config = cfg

    return best_config
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_threshold_tuner.py -v -x 2>&1 | tail -15`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/threshold_tuner.py backend/tests/test_threshold_tuner.py
git commit -m "feat(rag): add CRAG threshold auto-tuning via grid search

Grid search over high/low confidence thresholds to maximize F1
on existing negative QA pairs. Used to tune CRAG_ENABLED thresholds."
```

---

### Task 14: DeepEval Full Regression Test

**Files:**
- Modify: `backend/tests/deepeval_eval.py` (verify existing evaluation covers new metrics)

- [ ] **Step 1: Run full DeepEval evaluation with current state**

Run: `cd backend && python tests/deepeval_eval.py 2>&1 | tail -40`
Expected: 100% pass rate on reliable metrics (Context Precision, Context Recall, Faithfulness, Hallucination)

- [ ] **Step 2: Run benchmark suite**

Run: `cd backend && python tests/run_benchmark.py 2>&1 | tail -40`
Expected: All 7 benchmarks pass, metrics within expected ranges

- [ ] **Step 3: Document results**

Record the before/after comparison of key metrics:
- Answer Relevancy (target: >0.50, was 0.21)
- Negative Detection (target: ≥90%, was 50%)
- Context Precision (should remain ≥0.92)
- Faithfulness (should remain ≥0.96)

- [ ] **Step 4: Commit benchmark results**

```bash
git add backend/.deepeval/
git commit -m "test: DeepEval full regression after Track 1+2 optimizations

[Record actual metrics here]"
```

---

## Commercial Prep (Week 3-4)

### Task 15: Vector Store Interface Abstraction

**Files:**
- Create: `backend/app/vector_store_interface.py`
- Create: `backend/tests/test_vector_store_interface.py`
- Modify: `backend/app/rag/vector_store.py` (optional: implement interface)

- [ ] **Step 1: Write interface and tests**

Create `backend/app/vector_store_interface.py`:

```python
"""Abstract vector store interface for pluggable backends.

Allows switching between ChromaDB and pgvector without changing
RAG pipeline code. Only implement pgvector if client requires it.

Reference: docs/superpowers/specs/2026-06-08-krl-dutch-delivery-plan.md §4.2
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class VectorStoreInterface(ABC):
    """Abstract base for vector store implementations."""

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks.

        Returns list of dicts with 'text', 'metadata', 'score' keys.
        """
        ...

    @abstractmethod
    def upsert(self, chunks: List[Dict[str, Any]]) -> None:
        """Insert or update chunks in the store."""
        ...

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """Delete chunks by ID."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return total number of chunks in the store."""
        ...
```

Create `backend/tests/test_vector_store_interface.py`:

```python
"""Tests for vector store interface contract."""
import pytest
from app.vector_store_interface import VectorStoreInterface


class TestVectorStoreInterface:
    def test_is_abstract(self):
        """VectorStoreInterface should not be instantiable."""
        with pytest.raises(TypeError):
            VectorStoreInterface()

    def test_requires_all_methods(self):
        """Incomplete implementation should fail."""
        class Incomplete(VectorStoreInterface):
            pass

        with pytest.raises(TypeError):
            Incomplete()
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_vector_store_interface.py -v -x 2>&1 | tail -10`
Expected: 2 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/vector_store_interface.py backend/tests/test_vector_store_interface.py
git commit -m "feat(vector-store): add abstract VectorStoreInterface

Pluggable backend abstraction for Chroma/pgvector switching.
Only implement PgVectorStore if client requires pgvector."
```

---

### Task 16: 200 Concurrent WebSocket Load Test

**Files:**
- Modify: `backend/tests/benchmark_concurrent.py` (add 200-connection test)

- [ ] **Step 1: Run existing concurrent benchmark at 200 connections**

Run: `cd backend && python tests/benchmark_concurrent.py --connections 200 2>&1 | tail -30`
Expected: Record QPS, P50 latency, and error rate at 200 concurrent connections

- [ ] **Step 2: Analyze results and identify bottlenecks**

If QPS < 20 or error rate > 5%:
- Check if Semaphore limits need adjustment
- Check if Gunicorn workers are properly configured
- Check Redis connection pool size

- [ ] **Step 3: Tune Semaphore values if needed**

Adjust `LLM_SEMAPHORE_DEEPSEEK`, `RAG_SEMAPHORE` in `.env` based on load test results.

- [ ] **Step 4: Commit updated benchmark results**

```bash
git add backend/data/benchmark_history.jsonl
git commit -m "test: 200 concurrent WebSocket load test results

[Record QPS, P50, error rate at 200 connections]"
```

---

### Task 17: Upwork Proposal Finalization

**Files:**
- No code files — this is a document deliverable

- [ ] **Step 1: Write the first-tier proposal**

Using the template from the spec (§3.6), customize for KRL-Dutch:
- Reference specific Aureon metrics
- Mention voice input capability
- Highlight Docker + DigitalOcean compatibility
- Set rate at $20/hr

- [ ] **Step 2: Prepare portfolio screenshots**

Capture screenshots of:
- Landing Page (`/`)
- Chat with streaming response (`/search`)
- Voice input demo
- Dashboard with real metrics (`/dashboard`)
- Benchmark page (`/benchmark`)

- [ ] **Step 3: Submit proposal on Upwork**

Submit the proposal to KRL-Dutch project.

- [ ] **Step 4: No git commit needed — this is a business action**

---

## Self-Review Checklist

- [ ] All spec requirements mapped to tasks
- [ ] No TBD/TODO/placeholders in any task
- [ ] Every code step has actual code content
- [ ] All file paths are exact and verified against codebase
- [ ] Test code matches existing test patterns (pytest, @pytest.mark.asyncio)
- [ ] Commit messages follow conventional commits format
- [ ] Type names consistent across tasks (ThresholdConfig, VectorStoreInterface, etc.)
- [ ] New modules disabled by default (CRAG_ENABLED=false, REFLECTION_ENABLED=false)
- [ ] Track 1 tasks don't block on Track 2 tasks
