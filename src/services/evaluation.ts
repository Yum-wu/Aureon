/**
 * Evaluation Dashboard Service
 * 管理评估指标和基准测试的 API 调用
 */

export interface EvaluationMetric {
  id: number;
  metric_name: string;
  metric_value: number;
  metric_type: string;
  benchmark_set: string | null;
  model_version: string | null;
  created_at: string;
}

export interface BenchmarkRun {
  id: number;
  run_id: string;
  benchmark_set: string;
  total_queries: number;
  successful_queries: number;
  failed_queries: number;
  avg_latency_ms: number;
  recall_at_1: number;
  recall_at_3: number;
  recall_at_5: number;
  faithfulness_score: number;
  hallucination_rate: number;
  mrr: number;
  ndcg: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface EvaluationSummary {
  latest_recall_at_3: number;
  latest_faithfulness: number;
  latest_hallucination_rate: number;
  total_runs: number;
  successful_runs: number;
  success_rate: number;
}

const API_BASE = import.meta.env.VITE_API_URL || "/api";

export const evaluationApi = {
  /**
   * 获取评估摘要
   */
  async getSummary(): Promise<EvaluationSummary> {
    const response = await fetch(`${API_BASE}/evaluation/summary`);
    if (!response.ok) {
      throw new Error("Failed to fetch evaluation summary");
    }
    return response.json();
  },

  /**
   * 获取评估指标列表
   */
  async listMetrics(metricType?: string): Promise<EvaluationMetric[]> {
    const url = metricType
      ? `${API_BASE}/evaluation/metrics?metric_type=${metricType}`
      : `${API_BASE}/evaluation/metrics`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error("Failed to fetch evaluation metrics");
    }
    const data = await response.json();
    return data.metrics;
  },

  /**
   * 获取基准测试运行列表
   */
  async listBenchmarks(
    benchmarkSet?: string,
    limit?: number
  ): Promise<BenchmarkRun[]> {
    const params = new URLSearchParams();
    if (benchmarkSet) params.append("benchmark_set", benchmarkSet);
    if (limit) params.append("limit", limit.toString());

    const response = await fetch(
      `${API_BASE}/evaluation/benchmarks?${params.toString()}`
    );
    if (!response.ok) {
      throw new Error("Failed to fetch benchmark runs");
    }
    const data = await response.json();
    return data.runs;
  },
};
