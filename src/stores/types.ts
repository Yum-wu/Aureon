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
