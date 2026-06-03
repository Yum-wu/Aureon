import { Card } from '../ui/Card';

interface DataPoint {
  date: string;
  count: number;
}

interface QueryVolumeChartProps {
  data: DataPoint[];
  title?: string;
}

export function QueryVolumeChart({ data = [], title = 'Query Volume' }: QueryVolumeChartProps) {
  const safeData = Array.isArray(data) ? data : [];
  const maxCount = safeData.length > 0 ? Math.max(...safeData.map(d => d.count)) : 1;

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          {title}
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          {safeData.length} data points
        </span>
      </div>
      <div className="flex items-end gap-1.5 h-44">
        {safeData.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-[var(--text-tertiary)] text-sm">
            No data available
          </div>
        ) : (
          safeData.map((point, index) => (
            <div key={index} className="flex-1 flex flex-col items-center gap-2 group">
              <div className="relative w-full">
                <div
                  className="w-full rounded-sm bg-[var(--accent)]/60 group-hover:bg-[var(--accent)] transition-colors duration-150"
                  style={{ height: `${Math.max((point.count / maxCount) * 100, 4)}%` }}
                />
              </div>
              <span className="text-[10px] text-[var(--text-tertiary)] whitespace-nowrap">
                {new Date(point.date).toLocaleDateString('en', { weekday: 'short' })}
              </span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
