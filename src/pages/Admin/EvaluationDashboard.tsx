import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  evaluationApi,
  type EvaluationSummary,
  type EvaluationMetric,
  type BenchmarkRun,
} from "../services/evaluation";

export default function EvaluationDashboard() {
  const { t } = useTranslation();
  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [metrics, setMetrics] = useState<EvaluationMetric[]>([]);
  const [benchmarks, setBenchmarks] = useState<BenchmarkRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [summaryData, metricsData, benchmarksData] = await Promise.all([
        evaluationApi.getSummary(),
        evaluationApi.listMetrics(),
        evaluationApi.listBenchmarks(),
      ]);
      setSummary(summaryData);
      setMetrics(metricsData);
      setBenchmarks(benchmarksData);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load evaluation data"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">{t("common.loading")}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {t("admin.evaluation.title")}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {t("admin.evaluation.description")}
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-800">{error}</p>
          <button
            onClick={() => setError(null)}
            className="mt-2 text-sm text-red-600 hover:text-red-800"
          >
            {t("common.dismiss")}
          </button>
        </div>
      )}

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">
              {t("admin.evaluation.recallAt3")}
            </div>
            <div className="mt-2 text-3xl font-bold text-green-600">
              {summary.latest_recall_at_3}%
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">
              {t("admin.evaluation.faithfulness")}
            </div>
            <div className="mt-2 text-3xl font-bold text-blue-600">
              {summary.latest_faithfulness}%
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">
              {t("admin.evaluation.hallucinationRate")}
            </div>
            <div className="mt-2 text-3xl font-bold text-orange-600">
              {summary.latest_hallucination_rate}%
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">
              {t("admin.evaluation.totalRuns")}
            </div>
            <div className="mt-2 text-3xl font-bold text-purple-600">
              {summary.total_runs}
            </div>
          </div>
        </div>
      )}

      {/* Metrics Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            {t("admin.evaluation.metrics")}
          </h2>
        </div>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.metricName")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.value")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.type")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.createdAt")}
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {metrics.slice(0, 10).map((metric) => (
              <tr key={metric.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {metric.metric_name}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {(metric.metric_value * 100).toFixed(2)}%
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {metric.metric_type}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {new Date(metric.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {metrics.length === 0 && (
          <div className="text-center py-12">
            <p className="text-gray-500">
              {t("admin.evaluation.noMetrics")}
            </p>
          </div>
        )}
      </div>

      {/* Benchmark Runs Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            {t("admin.evaluation.benchmarkRuns")}
          </h2>
        </div>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.runId")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.benchmarkSet")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.recallAt3")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.status")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.evaluation.startedAt")}
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {benchmarks.slice(0, 10).map((run) => (
              <tr key={run.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {run.run_id}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {run.benchmark_set}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {(run.recall_at_3 * 100).toFixed(2)}%
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span
                    className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                      run.status === "completed"
                        ? "bg-green-100 text-green-800"
                        : run.status === "running"
                          ? "bg-blue-100 text-blue-800"
                          : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    {run.status}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {run.started_at
                    ? new Date(run.started_at).toLocaleDateString()
                    : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {benchmarks.length === 0 && (
          <div className="text-center py-12">
            <p className="text-gray-500">
              {t("admin.evaluation.noBenchmarks")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
