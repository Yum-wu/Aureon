# 控制台体验与数据治理实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Aureon 控制台四类体验硬伤——对比度不达标、状态刷新丢失、零引导、Tooltip 被裁剪。

**Architecture:** 四阶段推进（基础先行）：阶段 1 建 SafeStorage + useViewStore + 安装 Floating UI；阶段 2 改 Design Token + 重写 Tooltip；阶段 3 接入状态恢复 + Coach Mark 引导；阶段 4 验收。所有浮层用 Portal 脱离文档流，状态用 zustand persist + SafeStorage 三级降级。

**Tech Stack:** React 19, Zustand 5, @floating-ui/react, Tailwind CSS 4, react-i18next, sonner (toast)

---

## 文件结构

### 新增文件
| 文件 | 职责 |
|------|------|
| `src/stores/safeStorage.ts` | SafeStorage 适配器：localStorage → sessionStorage → 内存 Map 三级降级 |
| `src/stores/useViewStore.ts` | 用户意图快照 store（timeRange + onboardingCompleted），zustand persist |
| `src/components/onboarding/CoachMark.tsx` | 聚光灯遮罩 + 浮动说明卡组件 |
| `src/components/onboarding/OnboardingProvider.tsx` | 引导状态 Context Provider |
| `src/components/onboarding/steps.ts` | 步骤配置数组（纯数据） |
| `src/components/onboarding/StepAnchor.tsx` | 声明式锚点组件，标记引导位置 |

### 修改文件
| 文件 | 变更 |
|------|------|
| `src/index.css` | `--text-tertiary` 提亮至 `#8B8B99` |
| `src/components/ui/Tooltip.tsx` | 完全重写：Portal + Floating UI |
| `src/stores/useUIStore.ts` | 迁移裸调 localStorage → zustand persist + SafeStorage |
| `src/pages/Analytics.tsx` | 硬编码色值迁移至 Design Token |
| `src/pages/Benchmark.tsx` | 移除 opacity-75/opacity-90 |
| `src/pages/Dashboard.tsx` | timeRange 接入 useViewStore + 添加 StepAnchor |
| `src/pages/CostGovernance.tsx` | timeRange 接入 useViewStore |
| `src/pages/Search.tsx` | 添加 StepAnchor |
| `src/App.tsx` | 挂载 OnboardingProvider |
| `src/i18n/zh.json` | 新增 onboarding 键值 |
| `src/i18n/en.json` | 新增 onboarding 键值 |
| `package.json` | 新增 @floating-ui/react 依赖 |

---

## 阶段 1：基础设施层

### Task 1: 安装 @floating-ui/react

**Files:**
- Modify: `package.json`

- [ ] **Step 1: 安装依赖**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npm install @floating-ui/react
```

- [ ] **Step 2: 验证安装成功**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && node -e "const f = require('@floating-ui/react'); console.log('Floating UI version:', Object.keys(f).length, 'exports')"
```
Expected: 输出 exports 数量，无报错

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add package.json package-lock.json && git commit -m "deps: add @floating-ui/react for tooltip positioning"
```

---

### Task 2: 创建 SafeStorage 适配器

**Files:**
- Create: `src/stores/safeStorage.ts`

- [ ] **Step 1: 创建 SafeStorage 适配器**

```typescript
// src/stores/safeStorage.ts
/**
 * SafeStorage — 三级降级存储适配器
 * localStorage → sessionStorage → 内存 Map
 * 所有访问包裹 try-catch，永不抛出 SecurityError
 */

import type { StateStorage } from 'zustand/middleware';

type StorageBackend = 'localStorage' | 'sessionStorage' | 'memory';

class SafeStorageAdapter implements StateStorage {
  private backend: StorageBackend;
  private memory = new Map<string, string>();
  private notified = false;

  constructor() {
    this.backend = this.detect();
  }

  /** 检测可用的最高优先级存储后端 */
  private detect(): StorageBackend {
    try {
      const k = '__safe_storage_test__';
      localStorage.setItem(k, '1');
      localStorage.removeItem(k);
      return 'localStorage';
    } catch {
      // pass
    }
    try {
      const k = '__safe_storage_test__';
      sessionStorage.setItem(k, '1');
      sessionStorage.removeItem(k);
      return 'sessionStorage';
    } catch {
      // pass
    }
    return 'memory';
  }

  /** 当前使用的存储后端名称 */
  getBackend(): StorageBackend {
    return this.backend;
  }

  /** 是否降级到了非 localStorage */
  isDegraded(): boolean {
    return this.backend !== 'localStorage';
  }

  getItem(name: string): string | null {
    try {
      if (this.backend === 'memory') {
        return this.memory.get(name) ?? null;
      }
      const storage = this.backend === 'localStorage' ? localStorage : sessionStorage;
      return storage.getItem(name);
    } catch {
      return this.memory.get(name) ?? null;
    }
  }

  setItem(name: string, value: string): void {
    try {
      if (this.backend === 'memory') {
        this.memory.set(name, value);
        return;
      }
      const storage = this.backend === 'localStorage' ? localStorage : sessionStorage;
      storage.setItem(name, value);
    } catch {
      this.memory.set(name, value);
    }
  }

  removeItem(name: string): void {
    try {
      if (this.backend === 'memory') {
        this.memory.delete(name);
        return;
      }
      const storage = this.backend === 'localStorage' ? localStorage : sessionStorage;
      storage.removeItem(name);
    } catch {
      this.memory.delete(name);
    }
  }
}

export const safeStorage = new SafeStorageAdapter();
```

- [ ] **Step 2: 验证无编译错误**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit src/stores/safeStorage.ts 2>&1 | head -10
```
Expected: 无输出（无错误）

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/stores/safeStorage.ts && git commit -m "feat: add SafeStorage adapter with localStorage/sessionStorage/memory fallback"
```

---

### Task 3: 创建 useViewStore（用户意图快照）

**Files:**
- Create: `src/stores/useViewStore.ts`
- Modify: `src/stores/types.ts` (新增 ViewState 接口)

- [ ] **Step 1: 在 types.ts 中新增 ViewState 接口**

在 `src/stores/types.ts` 文件末尾（`UIState` 接口之后）追加：

```typescript
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
```

- [ ] **Step 2: 创建 useViewStore**

```typescript
// src/stores/useViewStore.ts
/**
 * useViewStore — 用户意图快照
 * 持久化 timeRange + onboardingCompleted 到 SafeStorage
 * 按用户身份隔离：aureon:viewstate:{userId}
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { safeStorage } from './safeStorage';
import { useAuthStore } from './useAuthStore';
import type { ViewState } from './types';

/** 从 auth 状态派生用户标识 */
function getUserId(): string {
  try {
    const { token, apiKey } = useAuthStore.getState();
    if (token) {
      // JWT payload decode（base64url）
      const parts = token.split('.');
      if (parts.length === 3) {
        const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
        return payload.sub || 'jwt_user';
      }
    }
    if (apiKey) {
      return `key_${apiKey.slice(0, 8)}`;
    }
  } catch {
    // decode 失败降级
  }
  return 'anonymous';
}

export const useViewStore = create<ViewState>()(
  persist(
    (set) => ({
      // 默认值
      dashboardTimeRange: '24h',
      analyticsTimeRange: '24h',
      costTimeRange: '30d',
      onboardingCompleted: false,

      // Actions
      setDashboardTimeRange: (range) => set({ dashboardTimeRange: range }),
      setAnalyticsTimeRange: (range) => set({ analyticsTimeRange: range }),
      setCostTimeRange: (range) => set({ costTimeRange: range }),
      completeOnboarding: () => set({ onboardingCompleted: true }),
      resetOnboarding: () => set({ onboardingCompleted: false }),
    }),
    {
      name: `aureon:viewstate:${getUserId()}`,
      storage: createJSONStorage(() => safeStorage),
      version: 1,
    }
  )
);
```

- [ ] **Step 3: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit src/stores/useViewStore.ts 2>&1 | head -10
```

- [ ] **Step 4: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/stores/types.ts src/stores/useViewStore.ts && git commit -m "feat: add useViewStore with zustand persist and user-scoped keys"
```

---

### Task 4: 迁移 useUIStore 到 SafeStorage

**Files:**
- Modify: `src/stores/useUIStore.ts`

- [ ] **Step 1: 重写 useUIStore 使用 zustand persist + SafeStorage**

将 `src/stores/useUIStore.ts` 整个文件替换为：

```typescript
/** UI 状态 Store（SafeStorage 持久化） */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { safeStorage } from './safeStorage';
import type { UIState } from './types';

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      mobileMenuOpen: false,
      aiDisclaimerEnabled: true,

      setMobileMenuOpen: (open: boolean) => {
        set({ mobileMenuOpen: open });
      },

      toggleAiDisclaimer: () => {
        set((state) => ({ aiDisclaimerEnabled: !state.aiDisclaimerEnabled }));
      },
    }),
    {
      name: 'aureon:ui',
      storage: createJSONStorage(() => safeStorage),
      // 只持久化 aiDisclaimerEnabled，mobileMenuOpen 是会话级状态
      partialize: (state) => ({
        aiDisclaimerEnabled: state.aiDisclaimerEnabled,
      }),
    }
  )
);
```

- [ ] **Step 2: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit 2>&1 | grep -i "useUIStore\|safeStorage" | head -5
```
Expected: 无输出（无错误）

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/stores/useUIStore.ts && git commit -m "refactor: migrate useUIStore from raw localStorage to zustand persist + SafeStorage"
```

---

## 阶段 2：渲染层

### Task 5: Design Token 对比度治理

**Files:**
- Modify: `src/index.css`

- [ ] **Step 1: 修改 --text-tertiary token**

在 `src/index.css` 中找到 `--text-tertiary: #5C5C6A;`（约第 15 行），替换为：

```css
  --text-tertiary: #8B8B99;
```

- [ ] **Step 2: 验证对比度**

在浏览器开发者工具中检查 `--text-tertiary` 值是否为 `#8B8B99`，在 `bg-tertiary #1F2022` 上的对比度应为 4.5:1。

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/index.css && git commit -m "fix: increase --text-tertiary contrast to 4.5:1 (WCAG AA)"
```

---

### Task 6: Analytics.tsx 硬编码色值迁移

**Files:**
- Modify: `src/pages/Analytics.tsx`

- [ ] **Step 1: 全局替换硬编码色值**

在 `src/pages/Analytics.tsx` 中执行以下替换（按顺序）：

```bash
cd C:/Users/Yum/Desktop/Aureon-test && sed -i \
  -e 's/bg-white/bg-[var(--bg-secondary)]/g' \
  -e 's/text-gray-900/text-[var(--text-primary)]/g' \
  -e 's/text-gray-500/text-[var(--text-tertiary)]/g' \
  -e 's/text-gray-400/text-[var(--text-tertiary)]/g' \
  -e 's/text-gray-600/text-[var(--text-secondary)]/g' \
  -e 's/border-gray-200/border-[var(--border)]/g' \
  -e 's/bg-gray-100/bg-[var(--bg-tertiary)]/g' \
  -e 's/bg-gray-200/bg-[var(--bg-tertiary)]/g' \
  -e 's/text-blue-600/text-[var(--accent)]/g' \
  -e 's/text-green-600/text-[var(--success)]/g' \
  -e 's/bg-red-600/bg-[var(--error)]/g' \
  -e 's/text-red-600/text-[var(--error)]/g' \
  -e 's/hover:bg-red-700/hover:bg-[var(--error)]\/80/g' \
  -e 's/hover:text-gray-900/hover:text-[var(--text-primary)]/g' \
  src/pages/Analytics.tsx
```

- [ ] **Step 2: 验证零 gray-* 残留**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && grep -n "gray-" src/pages/Analytics.tsx
```
Expected: 无输出（零匹配）

- [ ] **Step 3: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit src/pages/Analytics.tsx 2>&1 | head -5
```

- [ ] **Step 4: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/pages/Analytics.tsx && git commit -m "refactor: migrate Analytics.tsx from hardcoded gray-* to design tokens"
```

---

### Task 7: Benchmark.tsx opacity 修复

**Files:**
- Modify: `src/pages/Benchmark.tsx`

- [ ] **Step 1: 移除文本元素上的 opacity 类**

在 `src/pages/Benchmark.tsx` 中找到以下两处（约第 56-57 行）：

```tsx
<div className="text-sm opacity-90 mt-1">
```

替换为：

```tsx
<div className="text-sm mt-1">
```

找到（约第 59 行）：

```tsx
<span className="ml-2 text-xs bg-white/20 px-2 py-0.5 rounded-full">优化中</span>
```

保持不变（这是装饰性 badge，非正文文本）。

找到架构图中的 detail 文本（约第 84 行）：

```tsx
<div className="text-xs opacity-75">{item.detail}</div>
```

替换为：

```tsx
<div className="text-xs text-[var(--text-tertiary)]">{item.detail}</div>
```

同时修复移动端版本中同样的问题（约第 95 行）：

```tsx
<div className="text-xs opacity-75">{item.detail}</div>
```

替换为：

```tsx
<div className="text-xs text-[var(--text-tertiary)]">{item.detail}</div>
```

- [ ] **Step 2: 验证无 opacity 文本残留**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && grep -n "opacity-[0-9]" src/pages/Benchmark.tsx | grep -v "bg-white/" | grep -v "animate"
```
Expected: 无输出（仅装饰性 opacity 允许保留）

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/pages/Benchmark.tsx && git commit -m "fix: remove opacity-75/opacity-90 from text elements in Benchmark.tsx"
```

---

### Task 8: Tooltip 组件重写（Floating UI Portal）

**Files:**
- Modify: `src/components/ui/Tooltip.tsx`

- [ ] **Step 1: 重写 Tooltip 组件**

将 `src/components/ui/Tooltip.tsx` 整个文件替换为：

```tsx
/**
 * Tooltip — Floating UI Portal 版本
 * 渲染到 document.body，脱离父容器 overflow:hidden
 * 内置碰撞检测 + 方位翻转 + 热区桥接
 */

import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  useFloating,
  useInteractions,
  useHover,
  useFocus,
  useDismiss,
  offset,
  flip,
  shift,
  size,
  FloatingArrow,
  arrow,
  autoUpdate,
} from '@floating-ui/react';
import type { Placement } from '@floating-ui/react';

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  placement?: Placement;
}

export function Tooltip({ content, children, placement = 'top' }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const arrowRef = useRef<SVGSVGElement>(null);

  const { refs, context, floatingStyles } = useFloating({
    open,
    onOpenChange: setOpen,
    placement,
    middleware: [
      offset(8),
      flip({
        fallbackPlacements: ['bottom', 'right', 'left'],
        padding: 8,
      }),
      shift({
        padding: 8,
      }),
      size({
        apply({ availableWidth, elements }) {
          const maxWidth = Math.min(availableWidth - 16, window.innerWidth * 0.8);
          elements.floating.style.maxWidth = `${maxWidth}px`;
        },
      }),
      arrow({ element: arrowRef }),
    ],
    whileElementsMounted: autoUpdate,
  });

  const hover = useHover(context, {
    delay: { open: 200, close: 150 },
    move: false,
  });
  const focus = useFocus(context);
  const dismiss = useDismiss(context);

  const { getReferenceProps, getFloatingProps } = useInteractions([
    hover,
    focus,
    dismiss,
  ]);

  // ESC 键关闭
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  return (
    <>
      <span
        ref={refs.setReference}
        className="inline-flex items-center"
        {...getReferenceProps()}
      >
        {children}
      </span>
      {open &&
        createPortal(
          <div
            ref={refs.setFloating}
            role="tooltip"
            className="z-[9999] px-3 py-2 text-sm font-medium rounded-lg leading-snug animate-in fade-in-0 zoom-in-95 duration-150"
            style={{
              ...floatingStyles,
              background: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
              width: 'max-content',
            }}
            {...getFloatingProps()}
          >
            {content}
            <FloatingArrow
              ref={arrowRef}
              context={context}
              fill="var(--border)"
              stroke="var(--border)"
              strokeWidth={1}
              width={10}
              height={5}
            />
          </div>,
          document.body
        )}
    </>
  );
}
```

- [ ] **Step 2: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit src/components/ui/Tooltip.tsx 2>&1 | head -10
```

- [ ] **Step 3: 手动验证 Tooltip 在 overflow-hidden Card 中可见**

在浏览器中打开 Dashboard，hover Golden Signal 指标卡上的 `?` 图标，确认：
- 浮层完整可见，不被 Card 裁剪
- 空间不足时自动翻转方位
- 鼠标从 `?` 移到浮层，浮层不消失

- [ ] **Step 4: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/components/ui/Tooltip.tsx && git commit -m "feat: rewrite Tooltip with Floating UI portal for boundary-piercing positioning"
```

---

## 阶段 3：交互层

### Task 9: Dashboard 接入 useViewStore + 添加 StepAnchor

**Files:**
- Modify: `src/pages/Dashboard.tsx`

- [ ] **Step 1: 替换 timeRange 为 useViewStore**

在 `src/pages/Dashboard.tsx` 中，找到（约第 255 行）：

```tsx
  const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | '7d'>('24h');
```

替换为：

```tsx
  const timeRange = useViewStore((s) => s.dashboardTimeRange);
  const setDashboardTimeRange = useViewStore((s) => s.setDashboardTimeRange);
```

在文件顶部 import 区域添加：

```tsx
import { useViewStore } from '../stores/useViewStore';
```

找到 `<select>` 的 `onChange`（约第 366 行）：

```tsx
            onChange={(e) => setTimeRange(e.target.value as '1h' | '6h' | '24h' | '7d')}
```

替换为：

```tsx
            onChange={(e) => setDashboardTimeRange(e.target.value as '1h' | '6h' | '24h' | '7d')}
```

- [ ] **Step 2: 添加 StepAnchor data 属性**

找到 Golden Signals grid 的 `<div>`（约第 391 行）：

```tsx
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
```

替换为：

```tsx
            <div data-onboarding="dashboard-metrics" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
```

找到 Pipeline Breakdown 的 `<Card>`（约第 472 行）：

```tsx
              <Card>
```

替换为：

```tsx
              <Card data-onboarding="pipeline-breakdown">
```

- [ ] **Step 3: 移除未使用的 useState import**

如果 `useState` 不再被其他地方使用，从 import 中移除。检查文件中是否还有其他 `useState` 调用。

- [ ] **Step 4: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit 2>&1 | grep -i "Dashboard" | head -5
```

- [ ] **Step 5: 手动验证状态恢复**

1. 打开 Dashboard，选择 "7d" 时间范围
2. 刷新页面
3. 确认时间范围恢复为 "7d"

- [ ] **Step 6: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/pages/Dashboard.tsx && git commit -m "feat: persist Dashboard timeRange via useViewStore + add onboarding anchors"
```

---

### Task 10: Analytics 接入 useViewStore

**Files:**
- Modify: `src/pages/Analytics.tsx`

- [ ] **Step 1: 替换 timeRange 为 useViewStore**

在 `src/pages/Analytics.tsx` 中，找到（约第 7 行）：

```tsx
  const [timeRange, setTimeRange] = useState('24h');
```

替换为：

```tsx
  const timeRange = useViewStore((s) => s.analyticsTimeRange);
  const setAnalyticsTimeRange = useViewStore((s) => s.setAnalyticsTimeRange);
```

在文件顶部 import 区域添加：

```tsx
import { useViewStore } from '../stores/useViewStore';
```

找到 `<select>` 的 `onChange`（约第 68 行）：

```tsx
            onChange={(e) => setTimeRange(e.target.value)}
```

替换为：

```tsx
            onChange={(e) => setAnalyticsTimeRange(e.target.value as '24h' | '7d' | '30d')}
```

- [ ] **Step 2: 添加 StepAnchor data 属性**

找到 Metrics Grid 的 `<div>`（约第 79 行）：

```tsx
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
```

替换为：

```tsx
      <div data-onboarding="analytics-overview" className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
```

- [ ] **Step 3: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit 2>&1 | grep -i "Analytics" | head -5
```

- [ ] **Step 4: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/pages/Analytics.tsx && git commit -m "feat: persist Analytics timeRange via useViewStore + add onboarding anchor"
```

---

### Task 11: CostGovernance 接入 useViewStore

**Files:**
- Modify: `src/pages/CostGovernance.tsx`

- [ ] **Step 1: 替换 timeRange 为 useViewStore**

在 `src/pages/CostGovernance.tsx` 中，找到（约第 73 行）：

```tsx
  const [timeRange, setTimeRange] = useState<TimeRange>('30d');
```

替换为：

```tsx
  const timeRange = useViewStore((s) => s.costTimeRange);
  const setCostTimeRange = useViewStore((s) => s.setCostTimeRange);
```

在文件顶部 import 区域添加：

```tsx
import { useViewStore } from '../stores/useViewStore';
```

找到 `<select>` 的 `onChange`（约第 238 行）：

```tsx
              onChange={(e) => setTimeRange(e.target.value as TimeRange)}
```

替换为：

```tsx
              onChange={(e) => setCostTimeRange(e.target.value as '7d' | '30d' | '90d')}
```

- [ ] **Step 2: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit 2>&1 | grep -i "Cost" | head -5
```

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/pages/CostGovernance.tsx && git commit -m "feat: persist CostGovernance timeRange via useViewStore"
```

---

### Task 12: Search 添加 StepAnchor

**Files:**
- Modify: `src/pages/Search.tsx`

- [ ] **Step 1: 在搜索输入框添加 data 属性**

在 `src/pages/Search.tsx` 中找到搜索输入框的容器 `<div>` 或 `<input>`，添加：

```tsx
data-onboarding="search-input"
```

具体位置取决于 Search.tsx 的结构。搜索 `input` 或 `search` 关键词定位。

- [ ] **Step 2: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/pages/Search.tsx && git commit -m "feat: add onboarding anchor to Search input"
```

---

### Task 13: Onboarding 步骤配置

**Files:**
- Create: `src/components/onboarding/steps.ts`

- [ ] **Step 1: 创建步骤配置文件**

```typescript
// src/components/onboarding/steps.ts
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
```

- [ ] **Step 2: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/components/onboarding/steps.ts && git commit -m "feat: add onboarding steps configuration"
```

---

### Task 14: CoachMark 组件

**Files:**
- Create: `src/components/onboarding/CoachMark.tsx`

- [ ] **Step 1: 创建 CoachMark 组件**

```tsx
/**
 * CoachMark — 聚光灯引导组件
 * 遮罩 + 高亮目标元素 + 浮动说明卡
 * 使用 Floating UI 定位说明卡
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  useFloating,
  offset,
  flip,
  shift,
  autoUpdate,
} from '@floating-ui/react';
import { useTranslation } from 'react-i18next';
import type { OnboardingStep } from './steps';

interface CoachMarkProps {
  step: OnboardingStep;
  current: number;
  total: number;
  onNext: () => void;
  onPrev: () => void;
  onSkip: () => void;
  onFinish: () => void;
}

export function CoachMark({
  step,
  current,
  total,
  onNext,
  onPrev,
  onSkip,
  onFinish,
}: CoachMarkProps) {
  const { t } = useTranslation();
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const isLast = current === total - 1;
  const isFirst = current === 0;

  // 定位说明卡
  const { refs, floatingStyles } = useFloating({
    placement: 'bottom',
    middleware: [
      offset(12),
      flip({ fallbackPlacements: ['top', 'right', 'left'], padding: 8 }),
      shift({ padding: 8 }),
    ],
    whileElementsMounted: autoUpdate,
  });

  // 监听目标元素位置
  useEffect(() => {
    const el = document.querySelector(step.anchor);
    if (!el) return;

    // 滚动到目标元素可见
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // 等待滚动完成后计算位置
    const timer = setTimeout(() => {
      const rect = el.getBoundingClientRect();
      setTargetRect(rect);
      refs.setReference({
        getBoundingClientRect: () => rect,
        contextElement: el as Element,
      });
    }, 300);

    return () => clearTimeout(timer);
  }, [step.anchor, refs]);

  // ESC 键关闭
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onSkip();
      } else if (e.key === 'ArrowRight' && !isLast) {
        onNext();
      } else if (e.key === 'ArrowLeft' && !isFirst) {
        onPrev();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onSkip, onNext, onPrev, isLast, isFirst]);

  const handleNext = useCallback(() => {
    if (isLast) {
      onFinish();
    } else {
      onNext();
    }
  }, [isLast, onFinish, onNext]);

  if (!targetRect) return null;

  const spotlightPadding = 4;

  return createPortal(
    <div className="fixed inset-0 z-[9998]" style={{ pointerEvents: 'auto' }}>
      {/* 遮罩层 — 使用 clip-path 挖出聚光灯孔 */}
      <div
        className="absolute inset-0"
        style={{
          background: 'rgba(0,0,0,0.72)',
          clipPath: `polygon(
            0% 0%, 100% 0%, 100% 100%, 0% 100%,
            0% ${targetRect.top - spotlightPadding}px,
            ${targetRect.left - spotlightPadding}px ${targetRect.top - spotlightPadding}px,
            ${targetRect.left - spotlightPadding}px ${targetRect.bottom + spotlightPadding}px,
            ${targetRect.right + spotlightPadding}px ${targetRect.bottom + spotlightPadding}px,
            ${targetRect.right + spotlightPadding}px ${targetRect.top - spotlightPadding}px,
            0% ${targetRect.top - spotlightPadding}px
          )`,
        }}
      />

      {/* 聚光灯高亮边框 */}
      <div
        className="absolute border-2 rounded-lg pointer-events-none"
        style={{
          top: targetRect.top - spotlightPadding,
          left: targetRect.left - spotlightPadding,
          width: targetRect.width + spotlightPadding * 2,
          height: targetRect.height + spotlightPadding * 2,
          borderColor: 'var(--accent-500)',
          boxShadow: '0 0 0 4px rgba(94,106,210,0.2)',
        }}
      />

      {/* 说明卡 */}
      <div
        ref={(node) => {
          cardRef.current = node;
          refs.setFloating(node);
        }}
        className="z-[9999] rounded-xl p-5 max-w-xs animate-in fade-in-0 zoom-in-95 duration-200"
        style={{
          ...floatingStyles,
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        }}
      >
        {/* 步骤标签 */}
        <div
          className="text-[10px] font-bold uppercase tracking-widest mb-2"
          style={{ color: 'var(--accent)' }}
        >
          {t('onboarding.step_label', {
            current: current + 1,
            total,
            title: t(step.titleKey),
          })}
        </div>

        {/* 描述 */}
        <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--text-primary)' }}>
          {t(step.descriptionKey)}
        </p>

        {/* 导航栏 */}
        <div className="flex items-center justify-between">
          {/* 跳过 */}
          <button
            onClick={onSkip}
            className="text-xs font-medium transition-colors hover:opacity-80"
            style={{ color: 'var(--text-tertiary)' }}
          >
            {t('onboarding.skip')}
          </button>

          {/* 进度点 */}
          <div className="flex gap-1.5">
            {Array.from({ length: total }).map((_, i) => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full transition-colors"
                style={{
                  background: i === current ? 'var(--accent)' : 'var(--bg-tertiary)',
                }}
              />
            ))}
          </div>

          {/* 下一步/完成 */}
          <button
            onClick={handleNext}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
            style={{
              background: 'var(--accent)',
              color: '#fff',
            }}
          >
            {isLast ? t('onboarding.finish') : t('onboarding.next')}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
```

- [ ] **Step 2: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit src/components/onboarding/CoachMark.tsx 2>&1 | head -10
```

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/components/onboarding/CoachMark.tsx && git commit -m "feat: add CoachMark spotlight component with Floating UI positioning"
```

---

### Task 15: OnboardingProvider

**Files:**
- Create: `src/components/onboarding/OnboardingProvider.tsx`

- [ ] **Step 1: 创建 OnboardingProvider**

```tsx
/**
 * OnboardingProvider — 引导状态 Context Provider
 * 管理当前步骤、跨页面导航、完成/跳过标记
 */

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useViewStore } from '../../stores/useViewStore';
import { CoachMark } from './CoachMark';
import { ONBOARDING_STEPS, type OnboardingStep } from './steps';

interface OnboardingContextValue {
  /** 是否正在进行引导 */
  isActive: boolean;
  /** 当前步骤索引 */
  currentStep: number;
  /** 启动引导 */
  start: () => void;
  /** 重置引导（用于手动召回） */
  reset: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) {
    return { isActive: false, currentStep: -1, start: () => {}, reset: () => {} };
  }
  return ctx;
}

interface OnboardingProviderProps {
  children: ReactNode;
}

export function OnboardingProvider({ children }: OnboardingProviderProps) {
  const [currentStep, setCurrentStep] = useState(-1);
  const [isActive, setIsActive] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const onboardingCompleted = useViewStore((s) => s.onboardingCompleted);
  const completeOnboarding = useViewStore((s) => s.completeOnboarding);
  const resetOnboarding = useViewStore((s) => s.resetOnboarding);

  // 自动触发：首次访问 Dashboard
  useEffect(() => {
    if (!onboardingCompleted && location.pathname === '/dashboard' && !isActive) {
      // 延迟启动，等待页面渲染完成
      const timer = setTimeout(() => {
        setIsActive(true);
        setCurrentStep(0);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // 跨页面导航
  useEffect(() => {
    if (!isActive || currentStep < 0) return;
    const step = ONBOARDING_STEPS[currentStep];
    if (!step) return;

    // 如果当前步骤在另一个页面，自动导航
    if (step.page !== location.pathname) {
      navigate(step.page);
    }
  }, [isActive, currentStep, location.pathname, navigate]);

  const handleNext = useCallback(() => {
    setCurrentStep((prev) => prev + 1);
  }, []);

  const handlePrev = useCallback(() => {
    setCurrentStep((prev) => Math.max(0, prev - 1));
  }, []);

  const handleSkip = useCallback(() => {
    setIsActive(false);
    setCurrentStep(-1);
    completeOnboarding();
  }, [completeOnboarding]);

  const handleFinish = useCallback(() => {
    setIsActive(false);
    setCurrentStep(-1);
    completeOnboarding();
  }, [completeOnboarding]);

  const start = useCallback(() => {
    resetOnboarding();
    setIsActive(true);
    setCurrentStep(0);
  }, [resetOnboarding]);

  const reset = useCallback(() => {
    resetOnboarding();
    setIsActive(true);
    setCurrentStep(0);
  }, [resetOnboarding]);

  const currentStepData = isActive && currentStep >= 0 && currentStep < ONBOARDING_STEPS.length
    ? ONBOARDING_STEPS[currentStep]
    : null;

  return (
    <OnboardingContext.Provider value={{ isActive, currentStep, start, reset }}>
      {children}
      {currentStepData && location.pathname === currentStepData.page && (
        <CoachMark
          step={currentStepData}
          current={currentStep}
          total={ONBOARDING_STEPS.length}
          onNext={handleNext}
          onPrev={handlePrev}
          onSkip={handleSkip}
          onFinish={handleFinish}
        />
      )}
    </OnboardingContext.Provider>
  );
}
```

- [ ] **Step 2: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit src/components/onboarding/OnboardingProvider.tsx 2>&1 | head -10
```

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/components/onboarding/OnboardingProvider.tsx && git commit -m "feat: add OnboardingProvider with auto-trigger and cross-page navigation"
```

---

### Task 16: App.tsx 挂载 OnboardingProvider

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: 在 App.tsx 中挂载 OnboardingProvider**

在 `src/App.tsx` 的 import 区域添加：

```tsx
import { OnboardingProvider } from './components/onboarding/OnboardingProvider';
```

找到 `AuthProvider` 包裹 `AppLayout` 的位置（约第 246 行）：

```tsx
          <AuthProvider>
            <AppLayout />
          </AuthProvider>
```

替换为：

```tsx
          <AuthProvider>
            <OnboardingProvider>
              <AppLayout />
            </OnboardingProvider>
          </AuthProvider>
```

- [ ] **Step 2: 验证编译通过**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npx tsc --noEmit 2>&1 | grep -i "App.tsx\|Onboarding" | head -5
```

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/App.tsx && git commit -m "feat: mount OnboardingProvider in App.tsx"
```

---

### Task 17: I18n 键值

**Files:**
- Modify: `src/i18n/zh.json`
- Modify: `src/i18n/en.json`

- [ ] **Step 1: 在 zh.json 中添加 onboarding 键值**

在 `src/i18n/zh.json` 的顶层添加 `onboarding` 节点：

```json
{
  "onboarding": {
    "skip": "跳过",
    "next": "下一步 →",
    "back": "← 上一步",
    "finish": "完成 ✓",
    "step_label": "步骤 {{current}}/{{total}} · {{title}}",
    "recall_menu": "重新查看引导",
    "steps": {
      "dashboard-overview": {
        "title": "总览：实时健康指标",
        "description": "这是系统的核心仪表盘。延迟、流量、错误率、饱和度四大 Golden Signal 一目了然。低于阈值为绿色，超过则变红。"
      },
      "dashboard-pipeline": {
        "title": "归因：延迟从哪来？",
        "description": "Pipeline 分解条展示每个环节（检索→重排序→CRAG→生成）的耗时占比。哪个环节慢，一目了然。"
      },
      "search-execute": {
        "title": "执行：开始检索",
        "description": "在搜索框输入问题，系统会自动路由到最合适的检索策略（简单/中等/复杂），返回带来源引用的答案。"
      },
      "analytics-insight": {
        "title": "洞察：用量与成本",
        "description": "Analytics 帮你追踪查询量、延迟分布、Token 消耗。Cost 页面进一步展示预算执行率和按用户分解。"
      }
    }
  }
}
```

- [ ] **Step 2: 在 en.json 中添加 onboarding 键值**

在 `src/i18n/en.json` 的顶层添加 `onboarding` 节点：

```json
{
  "onboarding": {
    "skip": "Skip",
    "next": "Next →",
    "back": "← Back",
    "finish": "Done ✓",
    "step_label": "Step {{current}}/{{total}} · {{title}}",
    "recall_menu": "Restart tour",
    "steps": {
      "dashboard-overview": {
        "title": "Overview: Live Health Metrics",
        "description": "This is your system's command center. Latency, traffic, errors, and saturation — the four Golden Signals — at a glance. Green means healthy, red means attention needed."
      },
      "dashboard-pipeline": {
        "title": "Attribution: Where's the latency?",
        "description": "The pipeline breakdown shows time spent at each stage (retrieval → reranking → CRAG → generation). Spot bottlenecks instantly."
      },
      "search-execute": {
        "title": "Execute: Start searching",
        "description": "Type a question in the search box. The system auto-routes to the best retrieval strategy (simple/medium/complex) and returns answers with source citations."
      },
      "analytics-insight": {
        "title": "Insight: Usage & costs",
        "description": "Analytics tracks query volume, latency distribution, and token consumption. The Cost page goes further with budget execution rate and per-user breakdown."
      }
    }
  }
}
```

- [ ] **Step 3: 提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add src/i18n/zh.json src/i18n/en.json && git commit -m "i18n: add onboarding step translations (zh + en)"
```

---

## 阶段 4：验收

### Task 18: 全量验收

- [ ] **Step 1: WCAG AA 对比度验证**

在浏览器开发者工具中逐页检查所有文本元素的对比度：
- Dashboard：Golden Signal 标签、说明文本、图表轴标签
- Analytics：指标卡片标签、辅助文本
- Cost：预算进度条文本、表格数据
- Benchmark：指标卡片标签（无 opacity）、架构图说明

所有文本对比度 ≥ 4.5:1。

- [ ] **Step 2: Tooltip 边界穿透验证**

在 Dashboard 的 Golden Signal 指标卡（有 `overflow-hidden` 的 Card）上 hover `?` 图标：
- 浮层完整可见，不被裁剪
- 向下/向左/向右移动鼠标到屏幕边缘，Tooltip 自动翻转方位
- 鼠标从 `?` 移到浮层，浮层不闪烁

- [ ] **Step 3: 状态持久化验证**

1. Dashboard：选择 "7d" → 刷新 → 确认恢复为 "7d"
2. Analytics：选择 "30d" → 刷新 → 确认恢复为 "30d"
3. Cost：选择 "90d" → 刷新 → 确认恢复为 "90d"
4. 切换 API Key → 确认视图状态不串

- [ ] **Step 4: 降级路径验证**

在 Chrome DevTools → Application → Storage → 勾选 "Disable localStorage"：
1. 刷新页面
2. 确认页面正常加载，无 `SecurityError`
3. 确认一次性 toast 提示出现
4. 确认 timeRange 选择器可用（当前会话有效）

- [ ] **Step 5: Onboarding 引导验证**

1. 清除 localStorage 中的 `aureon:viewstate:*` 键
2. 访问 `/dashboard`
3. 确认引导自动触发，聚光灯高亮 Golden Signal 区域
4. 点击"下一步" → 到 Pipeline → 再下一步 → 自动跳转到 Search
5. 走完全部步骤 → 确认不再自动触发
6. 刷新 → 确认不再触发
7. 在 "?" 菜单点击"重新查看引导" → 确认重新触发

- [ ] **Step 6: 运行现有测试套件**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && npm test -- --run 2>&1 | tail -20
```
Expected: 全部通过，无回归

- [ ] **Step 7: 最终提交**

```bash
cd C:/Users/Yum/Desktop/Aureon-test && git add -A && git commit -m "feat: complete console experience governance (contrast, state persistence, onboarding, tooltip)"
```
