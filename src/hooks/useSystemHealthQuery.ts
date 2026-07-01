/**
 * useSystemHealthQuery — TanStack Query 版本
 * 替代原 useSystemHealth（useEffect + setInterval 模式）
 */

import { useQuery } from '@tanstack/react-query';
import { authFetch } from '../services/authFetch';

interface ServiceHealth {
  name: string;
  healthy: boolean;
  responseTime: number;
  details?: string;
}

interface SystemHealthData {
  services: ServiceHealth[];
  overallHealthy: boolean;
  lastChecked: Date;
}

async function fetchSystemHealth(): Promise<SystemHealthData> {
  const start = performance.now();
  const res = await authFetch('/api/health');
  const elapsed = Math.round(performance.now() - start);
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status}`);
  }
  const data = await res.json();

  // Parse health response into services
  const services: ServiceHealth[] = [
    {
      name: 'API Server',
      healthy: data.status === 'ok',
      responseTime: elapsed,
      details: data.model,
    },
    {
      name: 'Index',
      healthy: data.index_ready === true,
      responseTime: elapsed,
      details: data.index_ready ? 'Ready' : 'Not ready',
    },
    {
      name: 'Tools',
      healthy: Array.isArray(data.tools) && data.tools.length > 0,
      responseTime: elapsed,
      details: `${data.tools?.length || 0} tools available`,
    },
  ];

  return {
    services,
    overallHealthy: services.every((s) => s.healthy),
    lastChecked: new Date(),
  };
}

export function useSystemHealthQuery() {
  return useQuery({
    queryKey: ['system-health'],
    queryFn: fetchSystemHealth,
    staleTime: 30_000, // 30 seconds
    refetchInterval: 60_000, // Refresh every minute
    refetchOnWindowFocus: true,
    retry: 2,
  });
}
