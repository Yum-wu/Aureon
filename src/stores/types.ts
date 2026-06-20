/** Zustand Store 公共类型定义 */

import type { Message } from "../types/message";

/** 认证状态接口 */
export interface AuthState {
  /** API Key（传统模式） */
  apiKey: string;
  /** JWT Token（SSO 模式） */
  token: string;
  /** 是否已认证 */
  isAuthenticated: boolean;
  /** 用户角色 */
  role: string | null;
  /** API Key 登录 */
  login: (key: string) => Promise<boolean>;
  /** JWT 登录 */
  loginWithJWT: (email: string, password: string) => Promise<boolean>;
  /** 登出 */
  logout: () => void;
}

/** 聊天状态接口 */
export interface ChatState {
  /** 消息列表 */
  messages: Message[];
  /** 是否正在加载 */
  isLoading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 发送消息 */
  sendMessage: (content: string) => Promise<void>;
  /** 清空聊天 */
  clearChat: () => void;
  /** 停止生成 */
  stopGeneration: () => void;
  /** 清除错误 */
  clearError: () => void;
}

/** 文档项接口 */
export interface DocumentItem {
  title: string;
  source: string;
  file_type: string;
  chunk_count: number;
  status: string;
}

/** 文档状态接口 */
export interface DocumentsState {
  /** 文档列表 */
  documents: DocumentItem[];
  /** 文档总数 */
  totalDocs: number;
  /** 分块总数 */
  totalChunks: number;
  /** 是否正在加载 */
  loading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 搜索过滤器 */
  filter: string;
  /** 获取文档列表 */
  fetchDocuments: () => Promise<void>;
  /** 重新获取 */
  refetch: () => void;
  /** 设置过滤器 */
  setFilter: (filter: string) => void;
}

/** UI 状态接口 */
export interface UIState {
  /** 移动端菜单是否打开 */
  mobileMenuOpen: boolean;
  /** AI 免责声明是否启用 */
  aiDisclaimerEnabled: boolean;
  /** 设置移动端菜单状态 */
  setMobileMenuOpen: (open: boolean) => void;
  /** 切换 AI 免责声明 */
  toggleAiDisclaimer: () => void;
}

/** 用户意图快照接口（持久化到 SafeStorage） */
export interface ViewState {
  /** Dashboard 时间范围 */
  dashboardTimeRange: '1h' | '6h' | '24h' | '7d';
  /** Analytics 时间范围 */
  analyticsTimeRange: '24h' | '7d' | '30d';
  /** Cost 时间范围 */
  costTimeRange: '7d' | '30d' | '90d';
  /** Onboarding 是否已完成 */
  onboardingCompleted: boolean;
  /** 设置 Dashboard 时间范围 */
  setDashboardTimeRange: (range: ViewState['dashboardTimeRange']) => void;
  /** 设置 Analytics 时间范围 */
  setAnalyticsTimeRange: (range: ViewState['analyticsTimeRange']) => void;
  /** 设置 Cost 时间范围 */
  setCostTimeRange: (range: ViewState['costTimeRange']) => void;
  /** 标记 Onboarding 完成 */
  completeOnboarding: () => void;
  /** 重置 Onboarding（用于手动召回） */
  resetOnboarding: () => void;
}
