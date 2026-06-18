/**
 * Admin 布局组件
 * 左侧导航 + 面包屑 + 内容区，响应式侧边栏
 */

import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

/** Admin 标签页类型 */
export type AdminTab = 'overview' | 'users' | 'roles' | 'workspaces' | 'audit' | 'flags' | 'sso';

interface AdminLayoutProps {
  children: ReactNode;
  /** 当前激活的标签页 */
  activeTab: AdminTab;
  /** 标签页切换回调 */
  onTabChange: (tab: AdminTab) => void;
}

/** 标签页配置 */
const TAB_CONFIG: { key: AdminTab; icon: string }[] = [
  { key: 'overview', icon: '◉' },
  { key: 'users', icon: '👤' },
  { key: 'roles', icon: '🛡' },
  { key: 'workspaces', icon: '📁' },
  { key: 'audit', icon: '📋' },
  { key: 'flags', icon: '🚩' },
  { key: 'sso', icon: '🔑' },
];

export function AdminLayout({ children, activeTab, onTabChange }: AdminLayoutProps) {
  const { t } = useTranslation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="flex h-full min-h-0">
      {/* 侧边栏 */}
      <aside
        className={`shrink-0 border-r border-[var(--border)] bg-[var(--bg-secondary)] transition-all duration-200 ${
          sidebarCollapsed ? 'w-14' : 'w-52'
        }`}
      >
        {/* 折叠按钮 */}
        <div className="flex items-center justify-end p-2">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-1.5 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-white/[0.05] transition-colors"
            aria-label={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {sidebarCollapsed ? '→' : '←'}
          </button>
        </div>

        {/* 导航列表 */}
        <nav className="px-2 space-y-0.5">
          {TAB_CONFIG.map(({ key, icon }) => (
            <button
              key={key}
              onClick={() => onTabChange(key)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                activeTab === key
                  ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-medium'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-white/[0.03]'
              }`}
              title={t(`admin.tabs.${key}`)}
            >
              <span className="text-base leading-none shrink-0">{icon}</span>
              {!sidebarCollapsed && <span>{t(`admin.tabs.${key}`)}</span>}
            </button>
          ))}
        </nav>
      </aside>

      {/* 主内容区 */}
      <main className="flex-1 min-w-0 flex flex-col">
        {/* 面包屑 */}
        <div className="flex items-center gap-2 px-6 py-3 border-b border-[var(--border)] bg-[var(--bg-primary)]">
          <span className="text-xs text-[var(--text-tertiary)]">{t('admin.title')}</span>
          <span className="text-xs text-[var(--text-tertiary)]">/</span>
          <span className="text-xs text-[var(--text-secondary)] font-medium">
            {t(`admin.tabs.${activeTab}`)}
          </span>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-auto p-6">{children}</div>
      </main>
    </div>
  );
}
