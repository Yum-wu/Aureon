/**
 * Onboarding 步骤配置（纯数据，不含 DOM 操作）
 * 使用 i18n key，运行时通过 t() 翻译
 *
 * 设计原则：
 * 1. 聚焦价值而非功能 — 先让用户看到核心价值
 * 2. 渐进式披露 — 不要一次性展示所有功能
 * 3. 角色感知 — 根据用户角色显示不同引导
 * 4. 可跳过 — 尊重老用户
 *
 * 理想用户流程：
 * 1. 搜索体验 → 展示核心价值
 * 2. 上传文档 → 让知识库个人化
 * 3. 搜索自己的数据 → Aha moment
 * 4. 仪表盘 → 系统状态（管理员）
 * 5. 分析 → 使用洞察（管理员）
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
  /** 自动预填的查询文本（仅搜索步骤） */
  autoFillQuery?: string;
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: 'search-first',
    anchor: '[data-onboarding="search-input"]',
    titleKey: 'onboarding.steps.search-first.title',
    descriptionKey: 'onboarding.steps.search-first.description',
    page: '/search',
    roles: ['VIEWER', 'EDITOR', 'ADMIN'],
    autoFillQuery: '这个平台能做什么？',
  },
  {
    id: 'documents-upload',
    anchor: '[data-onboarding="documents-upload"]',
    titleKey: 'onboarding.steps.documents-upload.title',
    descriptionKey: 'onboarding.steps.documents-upload.description',
    page: '/documents',
    roles: ['EDITOR', 'ADMIN'],
  },
  {
    id: 'search-own-data',
    anchor: '[data-onboarding="search-input"]',
    titleKey: 'onboarding.steps.search-own-data.title',
    descriptionKey: 'onboarding.steps.search-own-data.description',
    page: '/search',
    roles: ['EDITOR', 'ADMIN'],
  },
  {
    id: 'dashboard-overview',
    anchor: '[data-onboarding="dashboard-metrics"]',
    titleKey: 'onboarding.steps.dashboard-overview.title',
    descriptionKey: 'onboarding.steps.dashboard-overview.description',
    page: '/dashboard',
    roles: ['ADMIN'],
  },
  {
    id: 'analytics-insight',
    anchor: '[data-onboarding="analytics-overview"]',
    titleKey: 'onboarding.steps.analytics-insight.title',
    descriptionKey: 'onboarding.steps.analytics-insight.description',
    page: '/analytics',
    roles: ['ADMIN'],
  },
];
