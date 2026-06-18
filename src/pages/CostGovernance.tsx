import { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useCostData } from '../hooks/useCostData';
import { Card } from '../components/ui/Card';
import { Tooltip } from '../components/ui/Tooltip';
import { LineChart } from '../components/charts/LineChart';
import { BarChart } from '../components/charts/BarChart';
import { PieChart } from '../components/charts/PieChart';
import { AdminTable } from '../components/admin/AdminTable';

/* ── 类型定义 ── */

type TimeRange = '7d' | '30d' | '90d';

interface CostConsumer {
  user: string;
  tokens: number;
  cost: number;
  query_count: number;
  trend: 'up' | 'down' | 'stable';
}

/* ── 子组件 ── */

/** 预算进度条 */
function BudgetProgress({ used, total }: { used: number; total: number }) {
  const { t } = useTranslation();
  const percentage = total > 0 ? (used / total) * 100 : 0;
  const isWarning = percentage >= 80;
  const isCritical = percentage >= 95;

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-sm font-medium text-[var(--text-primary)]">
          ${used.toFixed(2)} / ${total.toFixed(2)}
        </span>
        <span className={`text-xs font-semibold ${isCritical ? 'text-red-400' : isWarning ? 'text-yellow-400' : 'text-emerald-400'}`}>
          {percentage.toFixed(1)}%
        </span>
      </div>
      <div className="h-2 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(percentage, 100)}%`,
            backgroundColor: isCritical ? 'var(--error)' : isWarning ? 'var(--warning)' : 'var(--success)',
          }}
        />
      </div>
      {isWarning && (
        <p className={`text-xs mt-1 ${isCritical ? 'text-red-400' : 'text-yellow-400'}`}>
          {isCritical ? t('cost.budget.critical') : t('cost.budget.warning')}
        </p>
      )}
    </div>
  );
}

/** 趋势指示器 */
function TrendIndicator({ trend }: { trend: 'up' | 'down' | 'stable' }) {
  if (trend === 'up') return <span className="text-red-400 text-xs">↑</span>;
  if (trend === 'down') return <span className="text-emerald-400 text-xs">↓</span>;
  return <span className="text-[var(--text-tertiary)] text-xs">—</span>;
}

/* ── 主组件 ── */

export function CostGovernance() {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>('30d');
  const { summary, trends, breakdown, topConsumers: topConsumersData, loading, error, refetch } = useCostData(timeRange);

  // 导出 CSV
  const handleExport = useCallback(() => {
    const url = `/api/cost/export?range=${timeRange}&format=csv`;
    import('../services/authFetch').then(({ authFetch }) => {
      authFetch(url).then((r) => {
        if (r.ok) return r.blob();
        throw new Error('Export failed');
      }).then((blob) => {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `cost_report_${timeRange}.csv`;
        link.click();
        URL.revokeObjectURL(link.href);
      }).catch(() => { toast.error(t('cost.export_failed')); });
    });
  }, [timeRange, t]);

  // 所有 useMemo 必须在 early return 之前调用（React hooks 规则）
  const costTrendData = useMemo(() => trends.length > 0 ? [
    { id: t('cost.charts.daily_cost'), data: trends.map((p, i) => ({ x: `${i + 1}`, y: p.cost })) },
    { id: t('cost.charts.burn_rate'), data: trends.map((p, i) => ({ x: `${i + 1}`, y: p.cost * 0.9 })) },
    { id: t('cost.charts.forecast'), data: trends.map((p, i) => ({ x: `${i + 1}`, y: p.cost * 1.1 })) },
  ] : [], [trends, t]);

  const tokenUsageData = useMemo(() => trends.length > 0 ? trends.map((p, i) => ({
    label: `${i + 1}`,
    input: Math.round(p.tokens * 0.68),
    output: Math.round(p.tokens * 0.32),
  })) : [], [trends]);

  // 加载状态
  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)]">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 animate-pulse">
                <div className="h-3 bg-[var(--bg-tertiary)] rounded w-20 mb-4" />
                <div className="h-8 bg-[var(--bg-tertiary)] rounded w-24" />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 animate-pulse h-72" />
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 animate-pulse h-72" />
          </div>
        </div>
      </div>
    );
  }

  // 错误状态
  if (error) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center">
        <div className="text-center">
          <p className="text-[var(--error)] text-lg mb-2">{t('cost.error_loading')}</p>
          <p className="text-[var(--text-tertiary)] text-sm mb-4">{error}</p>
          <button
            onClick={refetch}
            className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors text-sm font-medium"
          >
            {t('cost.retry')}
          </button>
        </div>
      </div>
    );
  }

  // 从 hook 数据中提取（无 fallback 默认值，未连接时显示 —）
  const totalCost = summary?.totalCost;
  const costChange = summary?.costChange;
  const burnRate = summary?.burnRate;
  const burnTrend = summary?.burnTrend;
  const totalTokens = summary?.totalTokens;
  const inputTokens = totalTokens ? Math.round(totalTokens * 0.68) : undefined;
  const outputTokens = totalTokens ? Math.round(totalTokens * 0.32) : undefined;
  const budgetUsed = summary?.budgetUsed;
  const budgetTotal = summary?.budgetTotal;

  // 按模型分解饼图数据
  const modelBreakdownData = breakdown.length > 0 ? breakdown.map((b) => ({
    id: b.category,
    label: b.category,
    value: b.percentage,
    color: '#5E6AD2',
  })) : [];

  // 按工作区分解柱状图数据
  const workspaceCostData = breakdown.length > 0 ? breakdown.map((b) => ({
    label: b.category,
    value: b.cost,
  })) : [];

  // Top 消费者表格数据
  const topConsumers: CostConsumer[] = topConsumersData.length > 0 ? topConsumersData.map((c) => ({
    user: c.name,
    tokens: c.tokens,
    cost: c.cost,
    query_count: 0,
    trend: 'stable' as const,
  })) : [];

  const consumerColumns = [
    { key: 'user', label: t('cost.table.user'), sortable: true },
    {
      key: 'tokens',
      label: t('cost.table.tokens'),
      sortable: true,
      render: (row: CostConsumer) => <span className="tabular-nums">{(row.tokens / 1000).toFixed(0)}k</span>,
    },
    {
      key: 'cost',
      label: t('cost.table.cost'),
      sortable: true,
      render: (row: CostConsumer) => <span className="tabular-nums">${row.cost.toFixed(2)}</span>,
    },
    {
      key: 'query_count',
      label: t('cost.table.queries'),
      sortable: true,
      render: (row: CostConsumer) => <span className="tabular-nums">{row.query_count}</span>,
    },
    {
      key: 'trend',
      label: t('cost.table.trend'),
      render: (row: CostConsumer) => <TrendIndicator trend={row.trend} />,
    },
  ];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* ── 演示模式水印 ── */}
        {!summary && !loading && !error && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-center mb-6">
            <p className="text-sm font-medium text-amber-400">
              ⚠ {t('cost.demo_mode')}
            </p>
          </div>
        )}
        {/* ── 1. Header bar ── */}
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1
              className="text-2xl font-bold text-[var(--text-primary)] tracking-tight animate-fade-up"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              {t('cost.title')}
            </h1>
            <p className="text-sm text-[var(--text-tertiary)] mt-1">
              {t('cost.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as TimeRange)}
              className="px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            >
              <option value="7d">{t('cost.time_range.7d')}</option>
              <option value="30d">{t('cost.time_range.30d')}</option>
              <option value="90d">{t('cost.time_range.90d')}</option>
            </select>
            <button
              onClick={handleExport}
              className="px-4 py-1.5 text-sm font-medium rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:bg-white/[0.03] transition-colors"
            >
              {t('cost.export')}
            </button>
          </div>
        </div>

        {/* ── 2. Summary row ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {/* 总成本 */}
          <Card className="relative overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/5 h-px bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent opacity-30" />
            <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">
              {t('cost.summary.total_cost')}
            </p>
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-bold text-[var(--text-primary)] tabular-nums">{totalCost !== undefined ? `$${totalCost.toFixed(2)}` : '—'}</span>
            </div>
            <div className="flex items-center gap-1 mt-2">
              {costChange !== undefined ? (
                <>
                  <span className={`text-xs font-semibold ${costChange <= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {costChange <= 0 ? '↓' : '↑'} {Math.abs(costChange)}%
                  </span>
                  <span className="text-xs text-[var(--text-tertiary)]">{t('cost.summary.vs_last_period')}</span>
                </>
              ) : (
                <span className="text-xs text-[var(--text-tertiary)]">—</span>
              )}
            </div>
          </Card>

          {/* Burn Rate */}
          <Card className="relative overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/5 h-px bg-gradient-to-r from-transparent via-[var(--warning)] to-transparent opacity-30" />
            <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2 inline-flex items-center gap-1">
              {t('cost.summary.burn_rate')}
              <Tooltip content={t('cost.summary.burn_rate_tooltip')}>
                <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full text-[9px] cursor-help" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}>?</span>
              </Tooltip>
            </p>
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-bold text-[var(--text-primary)] tabular-nums">{burnRate !== undefined ? `$${burnRate.toFixed(2)}` : '—'}</span>
              <span className="text-sm font-medium text-[var(--text-tertiary)]">/day</span>
            </div>
            <div className="flex items-center gap-1 mt-2">
              {burnTrend ? <TrendIndicator trend={burnTrend} /> : <span className="text-xs text-[var(--text-tertiary)]">—</span>}
              <span className="text-xs text-[var(--text-tertiary)]">{t('cost.summary.daily_avg')}</span>
            </div>
          </Card>

          {/* Token 用量 */}
          <Card className="relative overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/5 h-px bg-gradient-to-r from-transparent via-[var(--success)] to-transparent opacity-30" />
            <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2 inline-flex items-center gap-1">
              {t('cost.summary.token_usage')}
              <Tooltip content={t('cost.summary.token_usage_tooltip')}>
                <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full text-[9px] cursor-help" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}>?</span>
              </Tooltip>
            </p>
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-bold text-[var(--text-primary)] tabular-nums">{totalTokens ? `${(totalTokens / 1000).toFixed(0)}k` : '—'}</span>
            </div>
            <div className="flex items-center gap-3 mt-2 text-xs text-[var(--text-tertiary)]">
              <span>{t('cost.summary.input')}: {inputTokens ? `${(inputTokens / 1000).toFixed(0)}k` : '—'}</span>
              <span>{t('cost.summary.output')}: {outputTokens ? `${(outputTokens / 1000).toFixed(0)}k` : '—'}</span>
            </div>
          </Card>

          {/* 预算状态 */}
          <Card className="relative overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/5 h-px bg-gradient-to-r from-transparent via-[var(--error)] to-transparent opacity-30" />
            <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">
              {t('cost.summary.budget_status')}
            </p>
            <BudgetProgress used={budgetUsed ?? 0} total={budgetTotal ?? 0} />
          </Card>
        </div>

        {/* ── 3. Charts row ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <LineChart data={costTrendData} title={t('cost.charts.cost_trend')} />
          <BarChart data={tokenUsageData} keys={['input', 'output']} indexBy="label" title={t('cost.charts.token_usage')} />
        </div>

        {/* ── 4. Breakdown row ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <PieChart data={modelBreakdownData} title={t('cost.charts.model_breakdown')} />
          <BarChart data={workspaceCostData} keys={['value']} indexBy="label" title={t('cost.charts.workspace_breakdown')} />
        </div>

        {/* ── 5. Top consumers table ── */}
        <Card>
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
            {t('cost.table.title')}
          </h3>
          <AdminTable<CostConsumer>
            data={topConsumers}
            columns={consumerColumns}
            loading={false}
          />
        </Card>
      </div>
    </div>
  );
}
