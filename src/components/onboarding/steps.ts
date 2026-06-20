/**
 * Onboarding 步骤配置（纯数据，不含 DOM 操作）
 * 使用 i18n key，运行时通过 t() 翻译
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
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: 'dashboard-overview',
    anchor: '[data-onboarding="dashboard-metrics"]',
    titleKey: 'onboarding.steps.dashboard-overview.title',
    descriptionKey: 'onboarding.steps.dashboard-overview.description',
    page: '/dashboard',
  },
  {
    id: 'dashboard-pipeline',
    anchor: '[data-onboarding="pipeline-breakdown"]',
    titleKey: 'onboarding.steps.dashboard-pipeline.title',
    descriptionKey: 'onboarding.steps.dashboard-pipeline.description',
    page: '/dashboard',
  },
  {
    id: 'search-execute',
    anchor: '[data-onboarding="search-input"]',
    titleKey: 'onboarding.steps.search-execute.title',
    descriptionKey: 'onboarding.steps.search-execute.description',
    page: '/search',
  },
  {
    id: 'analytics-insight',
    anchor: '[data-onboarding="analytics-overview"]',
    titleKey: 'onboarding.steps.analytics-insight.title',
    descriptionKey: 'onboarding.steps.analytics-insight.description',
    page: '/analytics',
  },
];
