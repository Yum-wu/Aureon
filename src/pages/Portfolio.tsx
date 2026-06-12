/**
 * Portfolio showcase page.
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
  { category: 'AI/ML', items: ['Qwen', 'OpenAI', 'Claude', 'BGE Embeddings'] },
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
          href="/architecture"
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
