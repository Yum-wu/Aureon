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
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      <div className="flex items-end gap-2 h-48">
        {safeData.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-[var(--text-tertiary)] text-sm">
            No data available
          </div>
        ) : (
          safeData.map((point, index) => (
            <div key={index} className="flex-1 flex flex-col items-center gap-2">
              <div className="w-full bg-[var(--accent)] rounded-t opacity-80 hover:opacity-100 transition-opacity"
                   style={{ height: `${(point.count / maxCount) * 100}%` }}
              />
              <span className="text-xs text-[var(--text-tertiary)]">
                {new Date(point.date).toLocaleDateString('en', { weekday: 'short' })}
              </span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
