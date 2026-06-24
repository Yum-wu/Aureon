import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/AuthContext';
import { AlertTriangle, LogIn, Sparkles } from 'lucide-react';

interface DashboardErrorProps {
  message: string;
  onRetry: () => void;
}

/** Error state with demo login fallback for auth errors */
export function DashboardError({ message, onRetry }: DashboardErrorProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { loginAsDemo } = useAuth();
  const [isDemoLoading, setIsDemoLoading] = useState(false);

  const isAuthError = /401|403|unauthor|forbidden|认证|权限|未登录|auth/i.test(message);

  const handleDemoLogin = async () => {
    setIsDemoLoading(true);
    try {
      const success = await loginAsDemo();
      if (success) {
        window.location.reload();
      }
    } finally {
      setIsDemoLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center py-16">
      {isAuthError ? (
        <>
          <AlertTriangle size={40} className="text-[var(--warning)] mb-4" />
          <p className="text-[var(--text-primary)] text-lg font-semibold mb-2">
            {t('dashboard.auth_failed_title', '认证已失效')}
          </p>
          <p className="text-[var(--text-tertiary)] text-sm mb-6 max-w-md text-center">
            {t('dashboard.auth_failed_desc', 'API Key 或登录凭证无效,请使用演示账号登录后查看数据。')}
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/login')}
              className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors text-sm font-medium inline-flex items-center gap-2"
            >
              <LogIn size={16} /> {t('dashboard.go_login', '去登录')}
            </button>
            <button
              onClick={handleDemoLogin}
              disabled={isDemoLoading}
              className="px-4 py-2 bg-[var(--accent-soft)] border border-[var(--accent)]/30 text-[var(--accent)] rounded-lg hover:bg-[var(--accent)]/20 transition-colors text-sm font-medium inline-flex items-center gap-2 disabled:opacity-50"
            >
              <Sparkles size={16} /> {isDemoLoading ? t('login.logging_in') : t('login.demo_account')}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="text-[var(--error)] text-lg mb-2">{t('dashboard.error_loading')}</p>
          <p className="text-[var(--text-tertiary)] text-sm mb-4">{message}</p>
          <button
            onClick={onRetry}
            className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors text-sm font-medium"
          >
            {t('dashboard.retry')}
          </button>
        </>
      )}
    </div>
  );
}
