import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAnalytics } from '../hooks/useAnalytics';

const Analytics = () => {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState('24h');
  const { usage, latency, tokens, cache, loading, error, refresh } = useAnalytics(timeRange);

  if (loading) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t('analytics.title')}</h1>
            <p className="text-gray-500 text-sm">{t('analytics.subtitle')}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-20 mb-3"></div>
              <div className="h-8 bg-gray-200 rounded w-16 mb-2"></div>
              <div className="h-3 bg-gray-200 rounded w-32"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <p className="text-red-600 mb-4">{t('analytics.error_loading')}</p>
          <button
            onClick={refresh}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
          >
            {t('analytics.retry')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t('analytics.title')}</h1>
          <p className="text-gray-500 text-sm">{t('analytics.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={refresh}
            className="px-3 py-2 text-gray-600 hover:text-gray-900 transition-colors"
            title={t('analytics.refresh')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="px-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="24h">{t('analytics.time_range.24h')}</option>
            <option value="7d">{t('analytics.time_range.7d')}</option>
            <option value="30d">{t('analytics.time_range.30d')}</option>
          </select>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {/* Latency */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="text-gray-500 text-sm mb-2">{t('analytics.avg_latency')}</div>
          <div className="text-3xl font-bold text-gray-900">{latency?.avg || 0}<span className="text-lg text-gray-500">ms</span></div>
          <div className="mt-3 text-xs text-gray-400">
            {t('analytics.latency.p95')}: {latency?.p95 || 0}ms · {t('analytics.latency.p99')}: {latency?.p99 || 0}ms
          </div>
        </div>

        {/* Tokens */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="text-gray-500 text-sm mb-2">{t('analytics.token_usage')}</div>
          <div className="text-3xl font-bold text-gray-900">{((tokens?.input || 0) / 1000).toFixed(0)}k</div>
          <div className="mt-3 text-xs text-gray-400">
            {t('analytics.output')}: {((tokens?.output || 0) / 1000).toFixed(0)}k · {t('analytics.cost')}: ${tokens?.cost || 0}
          </div>
        </div>

        {/* Queries */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="text-gray-500 text-sm mb-2">{t('analytics.total_queries')}</div>
          <div className="text-3xl font-bold text-gray-900">{usage?.total || 0}</div>
          <div className="mt-3 text-xs text-gray-400">
            {t('analytics.avg_per_hour', { count: usage?.perHour || 0 })}
          </div>
        </div>

        {/* Cache */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="text-gray-500 text-sm mb-2">{t('analytics.cache_hit_rate')}</div>
          <div className="text-3xl font-bold text-blue-600">{cache?.hitRate || 0}%</div>
          <div className="mt-3 text-xs text-gray-400">
            {t('analytics.saves', { count: cache?.saves || 0 })}
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Latency Chart */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold text-gray-900 mb-4">{t('analytics.latency.title')}</h3>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-600 w-12">{t('analytics.latency.avg')}</span>
              <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-green-500 rounded-full" style={{ width: `${Math.min((latency?.avg || 0) / 100 * 100, 100)}%` }} />
              </div>
              <span className="text-sm font-medium text-gray-900 w-16 text-right">{latency?.avg || 0}ms</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-600 w-12">{t('analytics.latency.p95')}</span>
              <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-yellow-500 rounded-full" style={{ width: `${Math.min((latency?.p95 || 0) / 100 * 100, 100)}%` }} />
              </div>
              <span className="text-sm font-medium text-gray-900 w-16 text-right">{latency?.p95 || 0}ms</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-600 w-12">{t('analytics.latency.p99')}</span>
              <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-red-500 rounded-full" style={{ width: `${Math.min((latency?.p99 || 0) / 100 * 100, 100)}%` }} />
              </div>
              <span className="text-sm font-medium text-gray-900 w-16 text-right">{latency?.p99 || 0}ms</span>
            </div>
          </div>
        </div>

        {/* Query Distribution */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold text-gray-900 mb-4">{t('analytics.queries.title')}</h3>
          <div className="space-y-3">
            {Object.entries(usage?.byIntent || {}).map(([intent, count], i) => {
              const colors = ['bg-blue-500', 'bg-purple-500', 'bg-cyan-500'];
              const percentage = usage?.total ? (count / usage.total) * 100 : 0;
              return (
                <div key={intent} className="flex items-center gap-3">
                  <span className="text-sm text-gray-600 w-20 truncate">{t(`analytics.intent.${intent}`, { defaultValue: intent })}</span>
                  <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full ${colors[i % colors.length]} rounded-full`} style={{ width: `${percentage}%` }} />
                  </div>
                  <span className="text-sm font-medium text-gray-900 w-12 text-right">{count}</span>
                </div>
              );
            })}
            {Object.keys(usage?.byIntent || {}).length === 0 && (
              <p className="text-gray-400 text-sm text-center py-4">{t('analytics.no_data')}</p>
            )}
          </div>
        </div>
      </div>

      {/* Token Usage Detail */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4">{t('analytics.tokens.title')}</h3>
        <div className="grid grid-cols-3 gap-8">
          <div>
            <div className="text-gray-500 text-sm mb-2">{t('analytics.tokens.input')}</div>
            <div className="text-2xl font-bold text-gray-900">{((tokens?.input || 0) / 1000).toFixed(1)}k</div>
            <div className="mt-2 h-2 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full" style={{ width: `${tokens?.total ? (tokens.input / tokens.total) * 100 : 0}%` }} />
            </div>
          </div>
          <div>
            <div className="text-gray-500 text-sm mb-2">{t('analytics.tokens.output')}</div>
            <div className="text-2xl font-bold text-gray-900">{((tokens?.output || 0) / 1000).toFixed(1)}k</div>
            <div className="mt-2 h-2 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full bg-purple-500 rounded-full" style={{ width: `${tokens?.total ? (tokens.output / tokens.total) * 100 : 0}%` }} />
            </div>
          </div>
          <div>
            <div className="text-gray-500 text-sm mb-2">{t('analytics.tokens.cost')}</div>
            <div className="text-2xl font-bold text-green-600">${tokens?.cost || 0}</div>
            <div className="mt-2 text-xs text-gray-400">{t('analytics.tokens.per_query', { cost: tokens?.costPerQuery || 0 })}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
