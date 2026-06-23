/**
 * AppSidebar — 全局左侧边栏导航
 * Canvas 设计系统 .sidebar-demo 模式的 React 实现
 * 分组导航：Platform + Administration
 */

import { useMemo } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard,
  Search,
  FileText,
  BarChart3,
  Network,
  Shield,
  Wallet,
  PanelLeftClose,
  PanelLeftOpen,
  LogIn,
  User,
} from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';
import { LanguageSwitcher } from '../i18n/LanguageSwitcher';
import { useAuth } from '../hooks/AuthContext';

interface SidebarItem {
  path: string;
  labelKey: string;
  icon: React.ReactNode;
  preload?: () => Promise<unknown>;
}

interface SidebarGroup {
  labelKey: string;
  items: SidebarItem[];
}

interface AppSidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const ICON_SIZE = 18;

export function AppSidebar({ collapsed, onToggleCollapse }: AppSidebarProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, role } = useAuth();

  const groups: SidebarGroup[] = useMemo(() => [
    {
      labelKey: 'app.sidebar.platform',
      items: [
        { path: '/dashboard', labelKey: 'app.nav.dashboard', icon: <LayoutDashboard size={ICON_SIZE} /> },
        { path: '/search', labelKey: 'app.nav.search', icon: <Search size={ICON_SIZE} /> },
        { path: '/documents', labelKey: 'app.nav.documents', icon: <FileText size={ICON_SIZE} /> },
        { path: '/analytics', labelKey: 'app.nav.analytics', icon: <BarChart3 size={ICON_SIZE} /> },
      ],
    },
    {
      labelKey: 'app.sidebar.administration',
      items: [
        { path: '/architecture', labelKey: 'app.nav.architecture', icon: <Network size={ICON_SIZE} /> },
        { path: '/admin', labelKey: 'app.nav.admin', icon: <Shield size={ICON_SIZE} /> },
        { path: '/cost', labelKey: 'app.nav.cost', icon: <Wallet size={ICON_SIZE} /> },
      ],
    },
  ], []);

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <aside
      className="app-sidebar"
      data-collapsed={collapsed}
      style={{
        width: collapsed ? 56 : 208,
        borderRight: '1px solid var(--border)',
        background: 'var(--surface)',
        display: 'flex',
        flexDirection: 'column',
        height: '100dvh',
        maxHeight: '100vh',
        position: 'sticky',
        top: 0,
        flexShrink: 0,
        transition: `width var(--duration-normal) var(--ease-out)`,
        overflow: 'hidden',
      }}
    >
      {/* Brand */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          padding: collapsed ? 'var(--space-4) var(--space-2)' : 'var(--space-4) var(--space-4)',
          height: 56,
          flexShrink: 0,
        }}
      >
        {!collapsed && (
          <button
            onClick={() => navigate('/')}
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: 18,
              color: 'var(--seed-primary)',
              letterSpacing: '-0.02em',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            Aureon
          </button>
        )}
        <button
          onClick={onToggleCollapse}
          className="sidebar-collapse-btn"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 28,
            height: 28,
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            background: 'none',
            color: 'var(--fg-tertiary)',
            cursor: 'pointer',
            transition: 'all var(--duration-fast) var(--ease-out)',
          }}
          aria-label={collapsed ? t('app.sidebar.expand', '展开侧边栏') : t('app.sidebar.collapse', '收起侧边栏')}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      {/* Navigation Groups */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: collapsed ? 'var(--space-2) var(--space-2)' : 'var(--space-2) var(--space-3)' }}>
        {groups.map((group, gi) => (
          <div key={gi} style={{ marginTop: gi === 0 ? 0 : 'var(--space-3)' }}>
            {/* Group Label */}
            {!collapsed && (
              <div
                className="sidebar-section-label"
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: 'var(--fg-muted)',
                  padding: 'var(--space-2) var(--space-3)',
                  marginBottom: 'var(--space-1)',
                }}
              >
                {t(group.labelKey)}
              </div>
            )}
            {collapsed && gi > 0 && (
              <div style={{ height: 1, background: 'var(--border)', margin: 'var(--space-2) var(--space-1)' }} />
            )}

            {/* Items */}
            {group.items.map((item) => {
              const active = isActive(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  title={collapsed ? t(item.labelKey) : undefined}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-3)',
                    padding: collapsed
                      ? 'var(--space-2) 0'
                      : 'var(--space-2) var(--space-3)',
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: 14,
                    fontWeight: active ? 500 : 400,
                    color: active ? 'var(--seed-accent)' : 'var(--fg-secondary)',
                    background: active
                      ? 'color-mix(in srgb, var(--seed-accent) 10%, transparent)'
                      : 'transparent',
                    textDecoration: 'none',
                    transition: 'all var(--duration-fast) var(--ease-out)',
                    marginBottom: 2,
                    minHeight: 44,
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'var(--border-subtle)';
                      e.currentTarget.style.color = 'var(--fg)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'transparent';
                      e.currentTarget.style.color = 'var(--fg-secondary)';
                    }
                  }}
                  aria-current={active ? 'page' : undefined}
                >
                  <span
                    style={{
                      width: ICON_SIZE,
                      height: ICON_SIZE,
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: 4,
                      color: active ? 'var(--seed-accent)' : 'inherit',
                    }}
                  >
                    {item.icon}
                  </span>
                  {!collapsed && <span>{t(item.labelKey)}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Bottom: Theme + Language + User Info */}
      <div
        style={{
          flexShrink: 0,
          borderTop: '1px solid var(--border)',
          padding: collapsed ? 'var(--space-3) var(--space-2)' : 'var(--space-3) var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
        }}
      >
        {/* User Info */}
        {isAuthenticated && !collapsed && (
          <div
            data-testid="user-info"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-3)',
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface-inset)',
            }}
          >
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: 'var(--seed-accent)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <User size={16} style={{ color: 'white' }} />
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {t('app.user.demo', 'Demo User')}
              </p>
              <p style={{ fontSize: 11, color: 'var(--fg-muted)', margin: 0, textTransform: 'capitalize' }}>
                {role || 'viewer'}
              </p>
            </div>
          </div>
        )}

        {/* Theme + Language */}
        <div
          style={{
            display: 'flex',
            flexDirection: collapsed ? 'column' : 'row',
            alignItems: 'center',
            gap: 'var(--space-2)',
          }}
        >
          <ThemeToggle />
          {!collapsed && <LanguageSwitcher />}
          {!collapsed && (
            <button
              onClick={() => navigate('/login')}
              style={{
                marginLeft: 'auto',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                padding: 'var(--space-1) var(--space-3)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 13,
                fontWeight: 500,
                color: 'var(--fg-secondary)',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
                transition: 'all var(--duration-fast) var(--ease-out)',
              }}
            >
              <LogIn size={14} />
              <span>{t('app.nav.admin')}</span>
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
