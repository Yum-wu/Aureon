import { useTranslation } from 'react-i18next';
import { Card } from '../ui/Card';
import { LineChart } from '../charts/LineChart';
import { BarChart } from '../charts/BarChart';

/* ── Types ── */

interface ChartSeries {
  id: string;
  data: { x: string; y: number }[];
}

interface QueryVolumeItem {
  label: string;
  value: number;
}

interface PipelineStage {
  name: string;
  ms: number;
  color: string;
}

interface DashboardChartsProps {
  latencyChartData: ChartSeries[];
  queryVolumeChartData: QueryVolumeItem[];
  isLoadingVolume: boolean;
  pipelineStages: PipelineStage[];
  cacheTrendData: ChartSeries[];
}

/* ── Helper components ── */

function PipelineBreakdown({ stages }: { stages: PipelineStage[] }) {
  const total = stages.reduce((sum, s) => sum + s.ms, 0) || 1;
  return (
    <div>
      <div className="flex h-8 rounded-lg overflow-hidden border border-[var(--border)]">
        {stages.map((stage) => (
          <div
            key={stage.name}
            className="flex items-center justify-center text-xs font-medium text-white transition-all duration-300"
            style={{ width: `${(stage.ms / total) * 100}%`, backgroundColor: stage.color, minWidth: stage.ms > 0 ? '24px' : '0' }}
            title={`${stage.name}: ${stage.ms}ms`}
          >
            {stage.ms > 0 ? `${stage.ms}ms` : ''}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-3 mt-3">
        {stages.map((stage) => (
          <div key={stage.name} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: stage.color }} />
            <span className="text-xs text-[var(--text-tertiary)]">{stage.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function NoDataPlaceholder() {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px] text-[var(--text-tertiary)] text-sm">
      {t('dashboard.no_data', '暂无数据')}
    </div>
  );
}

/* ── Main component ── */

/** Dashboard charts area: latency, query volume, pipeline, cache hit rate */
export function DashboardCharts({
  latencyChartData,
  queryVolumeChartData,
  isLoadingVolume,
  pipelineStages,
  cacheTrendData,
}: DashboardChartsProps) {
  const { t } = useTranslation();

  return (
    <>
      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {latencyChartData.some((s) => s.data.length > 0) ? (
          <LineChart data={latencyChartData} title={t('dashboard.charts.latency_trend')} />
        ) : (
          <NoDataPlaceholder />
        )}
        {isLoadingVolume && queryVolumeChartData.length === 0 ? (
          <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px]">
            <div className="animate-pulse h-4 w-24 bg-[var(--bg-tertiary)] rounded" />
          </div>
        ) : queryVolumeChartData.length > 0 ? (
          <BarChart data={queryVolumeChartData as any} keys={['value']} indexBy="label" title={t('dashboard.charts.query_volume')} />
        ) : (
          <NoDataPlaceholder />
        )}
      </div>

      {/* Pipeline + Cache row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card data-testid="rag-pipeline" data-onboarding="pipeline-breakdown">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              {t('dashboard.pipeline.title')}
            </h3>
          </div>
          {pipelineStages.length > 0 ? (
            <PipelineBreakdown stages={pipelineStages} />
          ) : (
            <div className="flex flex-col items-center justify-center h-[100px] text-[var(--text-tertiary)] text-sm">
              <p>{t('dashboard.no_data')}</p>
              <p className="text-xs mt-1">{t('dashboard.waiting_for_data', 'Waiting for WebSocket data...')}</p>
            </div>
          )}
        </Card>
        {cacheTrendData.some((s) => s.data.length > 0) ? (
          <LineChart data={cacheTrendData} title={t('dashboard.charts.cache_hit_rate', '缓存命中率')} />
        ) : (
          <NoDataPlaceholder />
        )}
      </div>
    </>
  );
}
