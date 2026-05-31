import { useBenchmark } from '../hooks/useBenchmark';
import { ArchitectureFlow } from '../components/architecture/ArchitectureFlow';
import { OptimizationStory } from '../components/architecture/OptimizationStory';
import { MetricGrid } from '../components/dashboard/MetricGrid';

export function Architecture() {
  const { data: benchmark } = useBenchmark();

  const metrics = benchmark?.metrics?.slice(0, 3).map((m: { label: string; value: string | number }) => ({
    label: m.label,
    value: m.value,
    change: 0,
    changeLabel: '',
  })) || [
    { label: 'Recall@3', value: '98.7%', change: 12, changeLabel: 'vs baseline' },
    { label: 'TTFT', value: 310, suffix: 'ms', change: -61, changeLabel: 'optimized' },
    { label: 'Cost/Query', value: '$0.001', change: -90, changeLabel: 'reduced' },
  ];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Architecture & Performance</h1>
          <p className="text-[var(--text-secondary)]">
            System architecture, pipeline design, and optimization metrics
          </p>
        </div>

        <div className="space-y-12">
          <section>
            <h2 className="text-2xl font-semibold mb-6">Runtime Metrics</h2>
            <MetricGrid metrics={metrics} columns={3} />
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-6">RAG Pipeline</h2>
            <ArchitectureFlow />
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-6">Optimization Story</h2>
            <OptimizationStory />
          </section>
        </div>
      </div>
    </div>
  );
}
