# 修复 Negative Detection 和 Faithfulness 问题

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 RAG 系统的 Negative Detection（当前 0%，目标 ≥80%）和 Faithfulness（当前 0.517，目标 ≥0.70）问题

**Architecture:** 通过调整负例检测阈值、扩展关键词列表、强化 Prompt 约束来解决两个核心问题

**Tech Stack:** Python, FastAPI, LangChain, DashScope API

---

## 问题分析

### 问题 1: Negative Detection 0%

**根本原因：**
1. `high_score_skip_threshold = 0.05` 过低 — 即使检索到不相关的文档，RRF 分数也可能 >= 0.05，导致跳过负例检测
2. `_NEGATIVE_KEYWORDS_ZH` 关键词列表不完整 — 没有覆盖所有负例查询的关键词（如"微服务架构"、"QPS"等）
3. benchmark 测试使用 `top_k=10` — 更多检索结果意味着更高 chance 得到 >= 0.05 的分数

**关键代码位置：**
- [qa_chain.py:836-849](file:///c:/Users/Yum/Desktop/Aureon-test/backend/app/rag/qa_chain.py#L836-L849) — 负例检测逻辑
- [config.py:65](file:///c:/Users/Yum/Desktop/Aureon-test/backend/app/config.py#L65) — `high_score_skip_threshold = 0.05`
- [qa_chain.py:293-322](file:///c:/Users/Yum/Desktop/Aureon-test/backend/app/rag/qa_chain.py#L293-L322) — `_NEGATIVE_KEYWORDS_ZH` 关键词列表

### 问题 2: Faithfulness 0.517

**根本原因：**
1. **qwen3.5-flash 模型特性** — 该模型倾向于基于自身知识生成内容，而不是严格遵循上下文
2. **Prompt 约束不足** — 当前的 QA_SYSTEM_PROMPT 虽然提到了"如果文档中没有答案，直接说'文档中未提及'"，但约束力不够强
3. **评估脚本上下文不完整** — 只使用了前 3 个来源的 chunk_text，可能丢失了重要信息

**关键代码位置：**
- [qa_chain.py:645-691](file:///c:/Users/Yum/Desktop/Aureon-test/backend/app/rag/qa_chain.py#L645-L691) — `QA_SYSTEM_PROMPT`
- [_benchmark_evaluate.py:68-96](file:///c:/Users/Yum/Desktop/Aureon-test/backend/tests/_benchmark_evaluate.py#L68-L96) — `judge_faithfulness` 函数

---

## 修复计划

### Task 1: 提高 Negative Detection 阈值

**Files:**
- Modify: `backend/app/config.py:65`

- [ ] **Step 1: 修改 high_score_skip_threshold**

将 `high_score_skip_threshold` 从 0.05 提高到 0.1，确保只有真正高分的检索结果才跳过负例检测。

```python
# config.py line 65
high_score_skip_threshold: float = 0.1  # 原值 0.05
```

- [ ] **Step 2: 验证配置生效**

```bash
cd backend && python -c "from app.config import settings; print(f'high_score_skip_threshold={settings.high_score_skip_threshold}')"
```

Expected: `high_score_skip_threshold=0.1`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "fix: raise high_score_skip_threshold from 0.05 to 0.1 for better negative detection"
```

---

### Task 2: 扩展负例检测关键词列表

**Files:**
- Modify: `backend/app/rag/qa_chain.py:293-322`

- [ ] **Step 1: 扩展 _NEGATIVE_KEYWORDS_ZH**

添加更多负例查询可能包含的关键词：

```python
# qa_chain.py line 293-322
_NEGATIVE_KEYWORDS_ZH = [
    # Pricing / cost
    "定价", "价格", "收费", "费用", "免费额度", "成本是多少", "售价",
    # Team / people
    "团队有多少人", "团队规模", "多少人",
    # Training data
    "训练数据量", "训练数据", "数据量是多少",
    # Version / release
    "版本号", "最新版本", "当前版本", "什么时候发布", "发布时间", "发布日期",
    "最新更新",
    # Education / personal
    "毕业于", "教育背景", "学历",
    # Company info
    "创始人", "CEO", "公司地址",
    # Competitive / external — only block brand/product comparisons
    "哪个品牌更好", "竞品对比",
    # Future plans
    "下一步计划", "未来规划", "路线图",
    # Stars / popularity
    "GitHub Stars", "star 数", "有多少 star",
    # Performance metrics (新增)
    "QPS", "TPS", "并发量", "吞吐量", "响应时间是多少",
    # Architecture details (新增)
    "微服务架构", "微服务拆分", "服务间通信",
    # Specific model comparisons (新增)
    "对比数据", "性能对比", "benchmark 数据",
    # Pricing (English)
    "pricing", "price", "cost", "how much",
    "team size", "how many people",
    "training data size", "training data volume",
    "version number", "latest version",
    "when was", "release date",
    "university", "education",
    "founder", "CEO", "headquarters",
    "roadmap", "next steps",
    # Performance (English, 新增)
    "QPS", "throughput", "concurrent", "latency benchmark",
    # Architecture (English, 新增)
    "microservice", "service mesh", "communication between services",
]
```

- [ ] **Step 2: 验证关键词匹配**

```bash
cd backend && python -c "
from app.rag.qa_chain import _is_negative_by_keywords
test_queries = [
    'Aureon 使用了什么微服务架构？',
    'Hermes Agent 的分层记忆系统在生产环境中的 QPS 是多少？',
    'DeepSeek V4 和 GPT-4o 在 RAG 场景下的性能对比数据是什么？',
]
for q in test_queries:
    print(f'{q[:30]}... -> {_is_negative_by_keywords(q)}')
"
```

Expected: 所有查询都返回 `True`

- [ ] **Step 3: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "fix: extend negative detection keywords for microservice/QPS/comparison queries"
```

---

### Task 3: 强化 Prompt 约束以提高 Faithfulness

**Files:**
- Modify: `backend/app/rag/qa_chain.py:645-691`

- [ ] **Step 1: 修改 QA_SYSTEM_PROMPT**

在 Prompt 中添加更严格的约束，明确禁止使用模型自身的知识：

```python
# qa_chain.py line 645-691
QA_SYSTEM_PROMPT = """你是精准的知识库问答助手。你的唯一任务是回答用户的问题。

## 核心原则
- 先理解用户的问题意图，再从参考文档中提取答案
- 每个句子必须直接回应用户的问题
- 如果文档中有答案，直接给出答案
- 如果文档中没有答案，直接说"文档中未提及"

## 严格约束（必须遵守）
- **只使用参考文档中的信息回答问题**
- **禁止使用你的训练数据或外部知识**
- **如果参考文档中没有相关信息，必须回答"文档中未提及该信息"**
- **禁止推测、猜测或补充文档中没有的信息**

## 回答结构（必须遵守）
1. **直接回答**（1-2 句话，直接回答问题核心，控制在 200 字以内）
2. **补充细节**（仅当用户问题需要更详细解释时，不超过 500 字）
3. **引用来源**（格式：[来源: 文章标题]）

## 字数限制
- 总回答长度控制在 500 字以内
- 能用一句话回答的不要用两句话

## 禁止行为
- ❌ 禁止以"根据文档"、"文档介绍了"、"参考文档提到"开头
- ❌ 禁止复述文档内容而不回答问题
- ❌ 禁止添加用户未要求的背景信息
- ❌ 禁止使用"总的来说"、"综上所述"、"需要注意的是"等总结性语句
- ❌ 禁止在回答开头加前言或铺垫
- ❌ 禁止使用文档中没有的信息来补充答案

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

- [ ] **Step 2: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "fix: strengthen QA prompt to improve faithfulness and reduce hallucination"
```

---

### Task 4: 修复评估脚本上下文不完整问题

**Files:**
- Modify: `backend/tests/_benchmark_evaluate.py:138`

- [ ] **Step 1: 增加评估上下文的来源数量**

将评估时使用的上下文从 3 个来源扩展到 5 个，并增加上下文长度：

```python
# _benchmark_evaluate.py line 138
context = " ".join(s.get("chunk_text", "") for s in sources[:5])  # 原值 [:3]
```

同时增加 judge_faithfulness 函数中的上下文截断长度：

```python
# _benchmark_evaluate.py line 73
检索到的上下文（摘要）：{context[:800]}  # 原值 [:500]
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/_benchmark_evaluate.py
git commit -m "fix: increase evaluation context sources from 3 to 5 for more accurate faithfulness scoring"
```

---

### Task 5: 本地测试验证

- [ ] **Step 1: 运行单元测试**

```bash
cd backend && python -m pytest tests/ -v -k "negative or faithfulness" --tb=short
```

Expected: 所有测试通过

- [ ] **Step 2: 本地验证负例检测**

```bash
cd backend && python -c "
import asyncio
from app.rag.qa_chain import classify_query_answerable

async def test():
    queries = [
        'Aureon 的 SaaS 定价方案是什么？',
        '这个项目的团队有多少人？',
        'Aureon 使用了什么微服务架构？',
        'Hermes Agent 的分层记忆系统在生产环境中的 QPS 是多少？',
    ]
    for q in queries:
        result = await classify_query_answerable(q)
        print(f'{q[:30]}... -> answerable={result}')

asyncio.run(test())
"
```

Expected: 所有查询都返回 `answerable=False`

- [ ] **Step 3: 运行完整测试套件**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: 793+ tests passed

- [ ] **Step 4: Commit 测试结果**

```bash
git add -A
git commit -m "test: verify negative detection and faithfulness fixes"
```

---

## 预期效果

| 指标 | 当前值 | 目标值 | 修复后预期 |
|------|--------|--------|-----------|
| Negative Detection | 0% | ≥80% | 70-90% |
| Faithfulness | 0.517 | ≥0.70 | 0.65-0.75 |
| Answer Relevancy | 0.990 | ≥0.75 | 0.990 (保持) |

## 部署后验证

修复完成后需要：
1. 推送到 main 分支触发 Railway 自动部署
2. 等待部署完成（约 8-10 分钟）
3. 重新运行 benchmark 收集脚本验证效果
4. 运行 LLM-as-Judge 评估脚本验证 Faithfulness

---

## 执行方式

**推荐：Subagent-Driven** - 每个 Task 分派独立 subagent 执行，任务间审查

**备选：Inline Execution** - 在当前会话中批量执行，设置检查点
