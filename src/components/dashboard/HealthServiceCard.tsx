import { useTranslation } from 'react-i18next';
import { StatusDot } from '../ui/StatusDot';
import type { ServiceHealth } from './types';

interface HealthServiceCardProps {
  service: ServiceHealth;
}

/** Health status card for a single service */
export function HealthServiceCard({ service }: HealthServiceCardProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg border" style={{ background: 'var(--surface-inset)', borderColor: 'var(--border-subtle)' }}>
      <StatusDot status={service.healthy ? 'success' : 'error'} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--fg)]">{service.name}</p>
        <p className="text-xs text-[var(--fg-tertiary)]">
          {service.healthy ? `${service.responseTime}ms` : '—'}
        </p>
      </div>
      <span className={`text-xs font-medium ${service.healthy ? 'text-[var(--success)]' : 'text-[var(--error)]'}`} aria-label={service.healthy ? t('dashboard.health.healthy') : t('dashboard.health.unhealthy')}>
        {service.healthy ? t('dashboard.health.healthy') : t('dashboard.health.unhealthy')}
      </span>
    </div>
  );
}
