import { useTranslation } from 'react-i18next';
import { Card } from '../ui/Card';
import { useBenchmark } from '../../hooks/useBenchmark';

interface PipelineStep {
  id: string;
  labelKey: string;
  descKey: string;
  latency: string;
}

const stepKeys: PipelineStep[] = [
  { id: 'query', labelKey: 'architecture.flow.user_query', descKey: 'architecture.flow.user_query_desc', latency: '0ms' },
  { id: 'intent', labelKey: 'architecture.flow.intent_classifier', descKey: 'architecture.flow.intent_classifier_desc', latency: '<1ms' },
  { id: 'retrieval', labelKey: 'architecture.flow.hybrid_retrieval', descKey: 'architecture.flow.hybrid_retrieval_desc', latency: '5.8ms' },
  { id: 'mmr', labelKey: 'architecture.flow.mmr_reranking', descKey: 'architecture.flow.mmr_reranking_desc', latency: '3ms' },
  { id: 'prompt', labelKey: 'architecture.flow.prompt_assembly', descKey: 'architecture.flow.prompt_assembly_desc', latency: '2ms' },
  { id: 'llm', labelKey: 'architecture.flow.llm_generation', descKey: 'architecture.flow.llm_generation_desc', latency: '~300ms' },
  { id: 'citation', labelKey: 'architecture.flow.citation_injection', descKey: 'architecture.flow.citation_injection_desc', latency: '5ms' },
  { id: 'sse', labelKey: 'architecture.flow.sse_streaming', descKey: 'architecture.flow.sse_streaming_desc', latency: '5ms' },
];

const fmtVal = (v: string | number | null, fallback: string) => {
  if (v === null) return fallback;
  const s = String(v);
  return s.includes('ms') || s.includes('%') || s.includes('$') ? s : s;
};

export function ArchitectureFlow() {
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const findMetric = (pat: string) =>
    benchmark?.metrics?.find((m: { label: string; value: string | number }) => m.label.includes(pat))?.value ?? null;

  const retrievalLatency = findMetric('Retrieval Latency');

  const pipelineSteps = stepKeys.map((step) => ({
    ...step,
    label: t(step.labelKey),
    description: t(step.descKey),
    latency: step.id === 'retrieval' ? fmtVal(retrievalLatency, step.latency) : step.latency,
  }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {pipelineSteps.map((step, index) => (
          <div key={step.id} className="relative">
            <Card hover className="h-full">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-6 h-6 flex items-center justify-center bg-[var(--accent-soft)] text-[var(--accent)] text-xs font-bold rounded">
                  {index + 1}
                </span>
                <h4 className="font-semibold text-sm">{step.label}</h4>
              </div>
              <p className="text-xs text-[var(--text-tertiary)] mb-2">{step.description}</p>
              <p className="text-xs font-mono text-[var(--accent)]">{step.latency}</p>
            </Card>
            {index < pipelineSteps.length - 1 && (
              <div className="hidden md:block absolute top-1/2 -right-2 transform -translate-y-1/2 text-[var(--text-tertiary)]">
                →
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
