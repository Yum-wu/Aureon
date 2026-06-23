/**
 * Admin 布局组件
 * 使用全局设计系统的面包屑 + 标签页模式
 * （全局侧边栏已处理导航，这里只需要面包屑和标签页）
 */

import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { LayoutDashboard, Users, Shield, Folder, ClipboardList, Flag, Key } from 'lucide-react';
import { Breadcrumb } from '../ui/Breadcrumb';
import { Tabs } from '../ui/Tabs';

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
const TAB_CONFIG: { key: AdminTab; icon: ReactNode; i18nKey: string }[] = [
  { key: 'overview', icon: <LayoutDashboard size={16} />, i18nKey: 'admin.tabs.overview' },
  { key: 'users', icon: <Users size={16} />, i18nKey: 'admin.tabs.users' },
  { key: 'roles', icon: <Shield size={16} />, i18nKey: 'admin.tabs.roles' },
  { key: 'workspaces', icon: <Folder size={16} />, i18nKey: 'admin.tabs.workspaces' },
  { key: 'audit', icon: <ClipboardList size={16} />, i18nKey: 'admin.tabs.audit' },
  { key: 'flags', icon: <Flag size={16} />, i18nKey: 'admin.tabs.flags' },
  { key: 'sso', icon: <Key size={16} />, i18nKey: 'admin.tabs.sso' },
];

export function AdminLayout({ children, activeTab, onTabChange }: AdminLayoutProps) {
  const { t } = useTranslation();

  const tabs = TAB_CONFIG.map(({ key, icon, i18nKey }) => ({
    id: key,
    label: t(i18nKey),
    icon,
  }));

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { label: 'Aureon', href: '/' },
          { label: t('admin.title'), href: '/admin' },
          { label: t(`admin.tabs.${activeTab}`) },
        ]}
      />

      {/* Header */}
      <div className="mt-4 mb-6">
        <h1
          className="text-2xl font-bold text-[var(--fg)] tracking-tight"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          {t('admin.title')}
        </h1>
        <p className="text-sm text-[var(--fg-tertiary)] mt-1">{t('admin.subtitle', 'Manage users, roles, and system settings')}</p>
      </div>

      {/* Tabs */}
      <Tabs
        tabs={tabs}
        activeTab={activeTab}
        onChange={(id) => onTabChange(id as AdminTab)}
        className="mb-6"
      />

      {/* Content */}
      <div>{children}</div>
    </div>
  );
}
