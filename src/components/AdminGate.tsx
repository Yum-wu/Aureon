import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Shield } from 'lucide-react';
import { useAuth } from '../hooks/AuthContext';

export function AdminGate({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (isAuthenticated) {
    return <>{children}</>;
  }

  return (
    <div className="flex items-center justify-center h-full p-8">
      <div className="text-center max-w-md">
        <Shield size={48} className="mx-auto text-[var(--text-tertiary)] mb-4" />
        <h2 className="text-xl font-bold text-[var(--text-primary)] mb-2">
          {t('admin_required.title')}
        </h2>
        <p className="text-[var(--text-secondary)] mb-6">
          {t('admin_required.desc')}
        </p>
        <div className="flex flex-col gap-3">
          <button
            onClick={() => navigate('/login')}
            className="glow-btn py-2 px-4 rounded-lg text-sm"
          >
            {t('admin_required.login_demo')}
          </button>
          {!isAuthenticated && (
            <button
              onClick={() => navigate('/login')}
              className="text-sm text-[var(--accent)] hover:underline"
            >
              {t('admin_required.login')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
