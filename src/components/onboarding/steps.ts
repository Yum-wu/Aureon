/**
 * Onboarding 步骤配置（纯数据，不含 DOM 操作）
 * 使用 i18n key，运行时通过 t() 翻译
 *
 * 设计原则：
 * 1. 聚焦价值而非功能 — 帮助用户快速获得"第一次成功"
 * 2. 渐进式披露 — 不要一次性展示所有功能
 * 3. 角色感知 — 根据用户角色显示不同引导
 * 4. 可跳过 — 尊重老用户
 */

export interface OnboardingStep {
  /** 唯一标识 */
  id: string;
  /** 目标元素的 CSS 选择器 */
  anchor: string;
  /** i18n 键名（onboarding.steps.{id}.title） */
  titleKey: string;
  /** i18n 键名（onboarding.steps.{id}.description） */
  descriptionKey: string;
  /** 所在页面路径 */
  page: string;
  /** 允许的角色（空数组 = 所有角色） */
  roles?: string[];
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: 'dashboard-overview',
    anchor: '[data-onboarding="dashboard-metrics"]',
    titleKey: 'onboarding.steps.dashboard-overview.title',
    descriptionKey: 'onboarding.steps.dashboard-overview.description',
    page: '/dashboard',
    roles: ['VIEWER', 'EDITOR', 'ADMIN'],
  },
  {
    id: 'search-execute',
    anchor: '[data-onboarding="search-input"]',
    titleKey: 'onboarding.steps.search-execute.title',
    descriptionKey: 'onboarding.steps.search-execute.description',
    page: '/search',
    roles: ['VIEWER', 'EDITOR', 'ADMIN'],
  },
  {
    id: 'documents-upload',
    anchor: '[data-onboarding="documents-upload"]',
    titleKey: 'onboarding.steps.documents-upload.title',
    descriptionKey: 'onboarding.steps.documents-upload.description',
    page: '/documents',
    roles: ['EDITOR', 'ADMIN'], // 仅编辑者和管理员
  },
  {
    id: 'support-widget',
    anchor: '[data-onboarding="support-fab"]',
    titleKey: 'onboarding.steps.support-widget.title',
    descriptionKey: 'onboarding.steps.support-widget.description',
    page: '/dashboard',
    roles: ['VIEWER', 'EDITOR', 'ADMIN'],
  },
  {
    id: 'analytics-insight',
    anchor: '[data-onboarding="analytics-overview"]',
    titleKey: 'onboarding.steps.analytics-insight.title',
    descriptionKey: 'onboarding.steps.analytics-insight.description',
    page: '/analytics',
    roles: ['VIEWER', 'EDITOR', 'ADMIN'],
  },
];
