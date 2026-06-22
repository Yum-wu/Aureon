/**
 * useAdminViewStore — Admin 页面 UI 状态持久化
 *
 * 职责：管理 Admin 各 Tab 的本地筛选/输入状态，刷新或切走再回来都保留。
 * 设计：独立于 useViewStore，避免污染通用 ViewState。
 *
 * 持久化字段：
 * - activeTab              当前激活的 Tab
 * - sidebarCollapsed       侧边栏折叠状态
 * - auditFilters           审计日志筛选（日期范围/用户/操作类型/级别）
 * - userSearchQuery        用户管理的搜索词
 * - rolePermissions        角色权限勾选状态
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { safeStorage } from './safeStorage';

export type AdminTab = 'overview' | 'users' | 'roles' | 'workspaces' | 'audit' | 'flags' | 'sso';

export interface AuditFilters {
  dateFrom: string;
  dateTo: string;
  user: string;
  actionType: string;
  severity: string;
}

/** 角色权限矩阵：role -> 已授予权限 key 数组 */
export type RolePermissions = Record<string, string[]>;

const DEFAULT_AUDIT_FILTERS: AuditFilters = {
  dateFrom: '',
  dateTo: '',
  user: '',
  actionType: '',
  severity: '',
};

interface AdminViewState {
  activeTab: AdminTab;
  sidebarCollapsed: boolean;
  auditFilters: AuditFilters;
  userSearchQuery: string;
  rolePermissions: RolePermissions | null;

  setActiveTab: (tab: AdminTab) => void;
  setSidebarCollapsed: (v: boolean) => void;
  setAuditFilters: (f: Partial<AuditFilters>) => void;
  resetAuditFilters: () => void;
  setUserSearchQuery: (q: string) => void;
  setRolePermissions: (p: RolePermissions) => void;
}

export const useAdminViewStore = create<AdminViewState>()(
  persist(
    (set) => ({
      activeTab: 'overview',
      sidebarCollapsed: false,
      auditFilters: DEFAULT_AUDIT_FILTERS,
      userSearchQuery: '',
      rolePermissions: null,

      setActiveTab: (tab) => set({ activeTab: tab }),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      setAuditFilters: (f) =>
        set((s) => ({ auditFilters: { ...s.auditFilters, ...f } })),
      resetAuditFilters: () => set({ auditFilters: DEFAULT_AUDIT_FILTERS }),
      setUserSearchQuery: (q) => set({ userSearchQuery: q }),
      setRolePermissions: (p) => set({ rolePermissions: p }),
    }),
    {
      name: 'aureon:admin:viewstate',
      storage: createJSONStorage(() => safeStorage),
      version: 1,
      // 仅持久化数据字段，不持久化 action 函数
      partialize: (s) => ({
        activeTab: s.activeTab,
        sidebarCollapsed: s.sidebarCollapsed,
        auditFilters: s.auditFilters,
        userSearchQuery: s.userSearchQuery,
        rolePermissions: s.rolePermissions,
      }),
    },
  ),
);
