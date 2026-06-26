import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from '../utils/toast';
import { LanguageSwitcher } from '../i18n/LanguageSwitcher';
import { useAuth } from '../hooks/AuthContext';

const Login = () => {
  const { t } = useTranslation();
  const { loginWithJWT, loginAsDemo } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const success = await loginWithJWT(email, password);
      if (success) {
        toast.success(t('login.success'));
        navigate('/dashboard');
      } else {
        const msg = t('login.invalid_credentials');
        setError(msg);
        toast.error(msg);
      }
    } catch {
      const msg = t('login.network_error');
      setError(msg);
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute inset-0 opacity-[0.03]" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-[var(--accent)] rounded-full blur-[160px] opacity-[0.06]" />
        <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-[var(--accent-hover)] rounded-full blur-[140px] opacity-[0.04]" />
      </div>

      {/* Language switcher */}
      <div className="absolute top-4 right-4 z-10">
        <LanguageSwitcher />
      </div>

      {/* Login card */}
      <div className="relative bg-[var(--bg-tertiary)] backdrop-blur-xl border border-[var(--border)] rounded-2xl shadow-2xl p-8 md:p-12 w-full max-w-md">
        {/* Logo + title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-400 to-cyan-300 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold" style={{ color: 'var(--accent)' }}>Aureon</h1>
          </div>
          <p className="text-[var(--text-secondary)] text-sm">
            Enterprise AI Knowledge Base Platform
          </p>
        </div>

        {/* Error message */}
        {error && (
          <div className="mb-5 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleLogin} className="space-y-5">
          {/* Email */}
          <div>
            <label htmlFor="email" className="block text-[var(--text-secondary)] text-sm font-medium mb-2">
              {t('login.email')}
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setError(''); }}
              className="w-full px-4 py-3 bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-[var(--accent)] transition-all duration-200"
              placeholder="your@email.com"
              required
              aria-describedby="email-hint"
            />
            <p id="email-hint" className="mt-1 text-xs text-[var(--text-tertiary)]">
              {t('login.email_hint')}
            </p>
          </div>

          {/* Password */}
          <div>
            <label htmlFor="password" className="block text-[var(--text-secondary)] text-sm font-medium mb-2">
              {t('login.password')}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(''); }}
              className="w-full px-4 py-3 bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-[var(--accent)] transition-all duration-200"
              placeholder="••••••••"
              required
              minLength={8}
              aria-describedby="password-hint"
            />
            <p id="password-hint" className="mt-1 text-xs text-[var(--text-tertiary)]">
              {t('login.password_hint')}
            </p>
          </div>

          {/* Remember me + forgot password */}
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                className="w-4 h-4 rounded border-white/20 bg-[var(--bg-tertiary)] text-blue-500 focus:ring-[var(--accent)] focus:ring-offset-0"
              />
              <span className="text-[var(--text-secondary)] text-sm group-hover:text-[var(--text-secondary)] transition-colors">
                {t('login.remember_me')}
              </span>
            </label>
            <a
              href="#"
              className="text-sm text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors"
            >
              {t('login.forgot_password')}
            </a>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={isLoading}
            className="glow-btn w-full py-3 px-4 text-white font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>{t('login.logging_in')}</span>
              </>
            ) : (
              t('login.submit')
            )}
          </button>
        </form>

        {/* Divider */}
        <div className="relative my-8">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-[var(--border)]" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-4 bg-[var(--bg-primary)] text-[var(--text-tertiary)]">{t('login.or_use')}</span>
          </div>
        </div>

        {/* SSO buttons */}
        <div className="space-y-3">
          <button
            type="button"
            className="w-full py-2.5 px-4 bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)] border border-[var(--border)] text-[var(--text-primary)] rounded-lg transition-all duration-200 flex items-center justify-center gap-3"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            <span className="text-sm">{t('login.google')}</span>
          </button>

          <button
            type="button"
            className="w-full py-2.5 px-4 bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)] border border-[var(--border)] text-[var(--text-primary)] rounded-lg transition-all duration-200 flex items-center justify-center gap-3"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
            <span className="text-sm">{t('login.github')}</span>
          </button>
        </div>

        {/* Demo account */}
        <div className="mt-6 space-y-2">
          <button
            type="button"
            onClick={async () => {
              const success = await loginAsDemo();
              if (success) {
                toast.success(t('login.success'));
                navigate('/dashboard');
              } else {
                toast.error(t('login.invalid_credentials'));
              }
            }}
            className="w-full py-2.5 px-4 bg-[var(--accent-soft)] hover:bg-[var(--accent)]/20 border border-[var(--accent)]/30 text-[var(--accent)] rounded-lg transition-all duration-200 flex items-center justify-center gap-2 text-sm"
          >
            {t('login.demo_account')}
          </button>
          <p className="text-center text-xs text-[var(--text-tertiary)]">
            {t('login.demo_hint')}
          </p>
        </div>

        {/* Signup link */}
        <p className="mt-8 text-center text-sm text-[var(--text-secondary)]">
          {t('login.no_account')}{' '}
          <a href="#" className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors">
            {t('login.signup')}
          </a>
        </p>
      </div>

      {/* Footer */}
      <div className="absolute bottom-6 left-0 right-0 text-center text-xs text-[var(--text-tertiary)]">
        <p>Aureon — Enterprise AI Knowledge Base Platform</p>
      </div>
    </div>
  );
};

export default Login;
