export interface StatsResponse {
  cache_hit_rate: number;
  query_count_24h: number;
  avg_retrieval_latency_ms: number;
  total_indexed_docs: number;
  total_chunks: number;
}

export interface RecentQuery {
  query: string;
  sources_count: number;
  latency_ms: number;
  timestamp: string;
}
