# 架构与基准测试页合并 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `/architecture` 和 `/benchmark` 合并为一个页面，删除冗余路由，使用真实 R19 数据，移除内部指标模块

**Architecture:** 重写 `Architecture.tsx`：保留 ArchitectureFlow + OptimizationStory，新增 Hero 指标卡片、TTFT 进度条、检索准确率进度条、技术栈详情。侧边栏标题更新。删除 `Benchmark.tsx`。

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, react-i18next, react-router-dom

---

### Task 1: 重写 Architecture.tsx

**Files:**
- Modify: `src/pages/Architecture.tsx`

**变更说明：**
- 删除 MetricGrid 导入和使用
- 新增区块：Hero 卡片（从真实数据读取 priority 0-3 的 customer_facing 指标）、TTFT 优化进度条、检索准确率进度条、技术栈详情
- 使用 Design Token 变量体系（不引入 Benchmark 页的多彩渐变）
- 进度条使用 theme 标准色（green / amber）

```tsx
import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../hooks/useBenchmark';
import { ArchitectureFlow } from '../components/architecture/ArchitectureFlow';
import { OptimizationStory } from '../components/architecture/OptimizationStory';

export function Architecture() {
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const heroMetrics = (benchmark?.metrics ?? [])
    .filter((m) => m.customer_facing)
    .sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99))
    .slice(0, 4);

  const ttftP50 = benchmark?.metrics?.find(m => m.label === 'TTFT P50')?.value ?? '590ms';
  const ttftP95 = benchmark?.metrics?.find(m => m.label === 'TTFT P95')?.value ?? '1,866ms';
  const e2eP50 = benchmark?.metrics?.find(m => m.label === 'E2E P50')?.value ?? '856ms';
  const e2eP99 = benchmark?.metrics?.find(m => m.label === 'E2E P99')?.value ?? '2,263ms';

  const recall5 = benchmark?.metrics?.find(m => m.label === 'Recall@5')?.value ?? '100.0%';
  const mrr = benchmark?.metrics?.find(m => m.label === 'MRR')?.value ?? '0.968';

  const parseNum = (v: string | number) => parseFloat(String(v).replace(/[^0-9.]/g, ''));

  const ttftBars = [
    { label: 'TTFT P50', val: ttftP50, num: parseNum(ttftP50), color: 'green', div: 20 },
    { label: 'TTFT P95', val: ttftP95, num: parseNum(ttftP95), color: 'amber', div: 70 },
    { label: 'E2E P50', val: e2eP50, num: parseNum(e2eP50), color: 'green', div: 50 },
    { label: 'E2E P99', val: e2eP99, num: parseNum(e2eP99), color: 'amber', div: 200 },
  ];

  const accuracyBars = [
    { label: 'Recall@5', val: recall5, num: parseNum(recall5), color: 'blue', mul: 1 },
    { label: 'MRR', val: mrr, num: parseNum(mrr), color: 'green', mul: 100 },
  ];

  const services = benchmark?.services ?? {};

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2 text-[var(--text-primary)]">{t('architecture.title')}</h1>
          <p className="text-[var(--text-secondary)]">{t('architecture.subtitle')}</p>
        </div>

        <div className="space-y-12">
          {/* Hero cards */}
          <section>
            <h2 className="text-2xl font-semibold mb-6 text-[var(--text-primary)]">{t('architecture.runtime_metrics')}</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {heroMetrics.map((m) => (
                <div key={m.label} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
                  <div className="text-3xl font-bold text-[var(--text-primary)]">{m.value ?? '—'}</div>
                  <div className="text-sm text-[var(--text-secondary)] mt-1">
                    {m.label}
                    {m.status === 'optimizing' && (
                      <span className="ml-2 text-xs bg-[var(--accent-soft)] text-[var(--accent)] px-2 py-0.5 rounded-full">优化中</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* RAG Pipeline */}
          <section>
            <h2 className="text-2xl font-semibold mb-6 text-[var(--text-primary)]">{t('architecture.rag_pipeline')}</h2>
            <ArchitectureFlow />
          </section>

          {/* Latency & Accuracy */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* TTFT Optimization */}
            <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
              <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('architecture.ttft_optimization')}</h3>
              <div className="space-y-4">
                {ttftBars.map((item) => (
                  <div key={item.label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-[var(--text-secondary)]">{item.label}</span>
                      <span className={item.color === 'green' ? 'text-[var(--success)]' : 'text-amber-500'}>{item.val}</span>
                    </div>
                    <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${item.color === 'green' ? 'bg-[var(--success)]' : 'bg-amber-400'}`}
                        style={{ width: `${Math.min(100, item.num / item.div)}%` }} />
                    </div>
                  </div>
                ))}
                <div className="text-xs text-[var(--text-tertiary)] mt-3">
                  {t('benchmark.ttft_improvement_detail')}
                </div>
              </div>
            </div>

            {/* Retrieval Accuracy */}
            <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
              <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('architecture.retrieval_accuracy')}</h3>
              <div className="space-y-4">
                {accuracyBars.map((item) => (
                  <div key={item.label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-[var(--text-secondary)]">{item.label}</span>
                      <span className={item.color === 'blue' ? 'text-[var(--accent)]' : 'text-[var(--success)]'}>{item.val}</span>
                    </div>
                    <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${item.color === 'blue' ? 'bg-[var(--accent)]' : 'bg-[var(--success)]'}`}
                        style={{ width: `${item.num * item.mul}%` }} />
                    </div>
                  </div>
                ))}
                <div className="text-xs text-[var(--text-tertiary)] mt-3">
                  {t('benchmark.qa_benchmark_detail')}
                </div>
              </div>
            </div>
          </div>

          {/* Optimization Story */}
          <section>
            <h2 className="text-2xl font-semibold mb-6 text-[var(--text-primary)]">{t('architecture.optimization_story')}</h2>
            <OptimizationStory />
          </section>

          {/* Tech Stack */}
          <section>
            <h3 className="text-2xl font-semibold mb-4 text-[var(--text-primary)]">{t('architecture.tech_stack')}</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              {[
                { label: t('benchmark.vector_database', 'Vector DB'), value: services.vector_db?.split('(')[0]?.trim() ?? '—', sub: services.vector_db?.includes('HNSW') ? 'HNSW + Sparse Vectors' : '' },
                { label: 'Embedding', value: services.embedding?.split('+')[0]?.trim() ?? '—', sub: '1024d · DashScope API' },
                { label: t('benchmark.retrieval_strategy', 'Retrieval'), value: 'Hybrid Search', sub: services.hybrid_search?.split('→')[0]?.trim() ?? '—' },
                { label: t('benchmark.caching', 'Caching'), value: services.cache?.split('+')[0]?.trim() ?? '—', sub: services.cache?.includes('semantic') ? 'Semantic Cache' : '' },
              ].map((item) => (
                <div key={item.label} className="p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="font-medium text-[var(--text-primary)] mb-1">{item.label}</div>
                  <div className="text-[var(--text-secondary)]">{item.value}</div>
                  <div className="text-xs text-[var(--text-tertiary)]">{item.sub}</div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
```

### Task 2: 删除 Benchmark.tsx

**Files:**
- Delete: `src/pages/Benchmark.tsx`

```bash
Remove-Item -LiteralPath "src/pages/Benchmark.tsx"
```

### Task 3: 删除 /benchmark 和 /portfolio 路由

**Files:**
- Modify: `src/App.tsx:162-163`

删除两行：
```tsx
<Route path="/benchmark" element={<Benchmark />} />
<Route path="/portfolio" element={<Navigate to="/benchmark" replace />} />
```

同时移除文件顶部的 `Benchmark` 导入（如果存在）和 `Navigate` 导入（如果不再使用）。

### Task 4: 更新 Landing 页 BenchmarkSection 链接

**Files:**
- Modify: `src/components/landing/BenchmarkSection.tsx:42`

```tsx
// 改前：
onClick={() => navigate('/benchmark')}

// 改后：
onClick={() => navigate('/architecture')}
```

### Task 5: 更新侧边栏 i18n 标签

**Files:**
- Modify: `src/i18n/en.json:10`
- Modify: `src/i18n/zh.json:10`

```json
// en.json: "architecture": "Architecture" → "architecture": "Architecture & Performance",
// zh.json: "architecture": "架构" → "architecture": "架构与性能",
```

### Task 6: 添加缺失的 i18n 键

**Files:**
- Modify: `src/i18n/en.json`
- Modify: `src/i18n/zh.json`

在 `architecture` 段落（en.json ~603-617, zh.json ~602-616）添加两个新键：

```json
// en.json — 在 architecture 段落末尾（}, 行之前）插入:
    "ttft_optimization": "TTFT Optimization",
    "retrieval_accuracy": "Retrieval Accuracy"

// zh.json — 在 architecture 段落末尾插入:
    "ttft_optimization": "TTFT 优化",
    "retrieval_accuracy": "检索准确率"
```

### Task 7: 验证构建

- [ ] 运行 TypeScript 类型检查

```bash
npx tsc --noEmit
```

- [ ] 运行测试

```bash
npm test -- --run
```

- [ ] 构建生产版本

```bash
npm run build
```

预期：全部通过，没有类型错误，构建成功。
