# 控制台体验与数据治理设计 Spec

> **日期**: 2026-06-20
> **状态**: 待审阅
> **范围**: 四规范合一（对比度治理 + 状态持久化 + Onboarding 引导 + Tooltip 边界穿透）

---

## 1. 背景与问题定义

Aureon 控制台存在四类体验硬伤，阻碍信息高效传达：

| # | 规范 | 核心问题 | 严重度 |
|---|------|---------|--------|
| 一 | 信息可读性治理 | 辅助文本 `#5C5C6A` 在 `#1F2022` 上对比度仅 2.3:1（WCAG AA 要求 4.5:1）；Analytics.tsx 全页硬编码 Tailwind 色值脱离 Design Token 体系 | 高 |
| 二 | 数据活性与状态一致性 | 三个页面 `timeRange` 都是组件内 `useState`，刷新即丢失；`useUIStore` 裸调 `localStorage` 无降级 | 高 |
| 三 | 无门槛认知引导 | 全项目零 onboarding 机制，非技术用户决策瘫痪 | 中 |
| 四 | 辅助释义浮层边界穿透 | `Tooltip` 用 `absolute` 定位在父容器内，`Card` 的 `overflow-hidden` 必然裁剪浮层；无碰撞检测；`pointer-events-none` 导致热区不连续 | 高 |

---

## 2. 设计目标

- **零认知门槛**：核心数据指标一目了然，辅助文本高对比度可读
- **状态确定性**：用户离开后回来，界面即"离开时的模样"
- **零布局侵入**：所有改动不触发父容器重排，不改变页面滚动条
- **优雅降级**：存储不可用时静默降级，不中断 JS 执行

---

## 3. 架构总览

### 3.1 四层推进架构

```
┌─────────────────────────────────────────────────────────────┐
│  阶段 4：验收层                                              │
│  · WCAG AA 对比度逐页扫描  · 浮层穿透 E2E  · 降级手动测试    │
├─────────────────────────────────────────────────────────────┤
│  阶段 3：交互层                                              │
│  · Dashboard/Analytics/Cost 状态恢复接入（规范二接入）        │
│  · 浮层碰撞检测 + 方位翻转 + 热区桥接（规范四完善）           │
│  · Onboarding Coach Mark 引导流（规范三）                    │
├─────────────────────────────────────────────────────────────┤
│  阶段 2：渲染层                                              │
│  · Design Token 对比度治理（规范一）                         │
│  · Analytics.tsx 硬编码色值迁移（规范一）                    │
│  · Tooltip → Floating UI Portal 重写（规范四）               │
├─────────────────────────────────────────────────────────────┤
│  阶段 1：基础设施层（零 UI 变化）                             │
│  · SafeStorage 适配器（规范二降级逻辑）                      │
│  · useViewStore（zustand persist + SafeStorage）             │
│  · 安装 @floating-ui/react（规范四依赖）                     │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 规范间依赖图

```
规范一（对比度）──独立，可最先做──┐
                                │
规范四（Tooltip）──依赖 @floating-ui ──┤──→ 阶段 1 先安装依赖
                                │
规范二（状态持久化）──依赖 SafeStorage ──┘

规范三（Onboarding）──依赖规范二的 useViewStore（标记 completed）
                 └──依赖规范四的 Floating UI（Coach Mark 定位）
```

### 3.3 涉及文件清单

| 规范 | 新增文件 | 修改文件 |
|------|---------|---------|
| 一（对比度） | — | `src/index.css`（token）、`src/pages/Analytics.tsx`（迁移硬编码）、`src/pages/Benchmark.tsx`（opacity 修复） |
| 四（Tooltip） | `package.json`（+@floating-ui/react） | `src/components/ui/Tooltip.tsx`（完全重写） |
| 二（状态） | `src/stores/safeStorage.ts`、`src/stores/useViewStore.ts` | `src/stores/useUIStore.ts`（迁移裸调 localStorage）、`src/pages/Dashboard.tsx`、`src/pages/Analytics.tsx`、`src/pages/CostGovernance.tsx` |
| 三（引导） | `src/components/onboarding/CoachMark.tsx`、`src/components/onboarding/OnboardingProvider.tsx`、`src/components/onboarding/steps.ts` | `src/App.tsx`（挂载 Provider）、`src/i18n/zh.json`、`src/i18n/en.json` |

---

## 4. 规范一：对比度与排版层级治理

### 4.1 Token 变更方案

```
Token 变更前                          Token 变更后
──────────────────────               ──────────────────────
--text-primary:  #EDEDF0 (15.2:1)    --text-primary:  #EDEDF0  ← 不变
--text-secondary:#8B8B99 (4.5:1)     --text-secondary:#8B8B99  ← 不变
--text-tertiary: #5C5C6A (2.3:1) ❌  --text-tertiary: #8B8B99  ← 提亮至与 secondary 一致
```

层级感不再靠色差，改用排版梯度：
- **标签层**（大写标题）：11px / font-weight:500 / tracking-wider
- **说明层**（辅助文本）：12px / font-weight:400
- **数据层**（核心指标）：30px / font-weight:700 / tabular-nums

### 4.2 `opacity` 使用禁令

所有承载语义信息的文本元素，禁止使用 `opacity < 1`。`opacity` 仅允许用于装饰性元素（分割线、占位骨架、背景渐变）。

```css
/* 禁止：opacity 叠加降低对比度 */
.bad  { color: #5C5C6A; opacity: 0.75; }

/* 允许：仅对装饰性元素使用 opacity */
.good { color: rgba(255,255,255,0.04); }
```

### 4.3 Analytics.tsx 迁移映射

| 当前硬编码 | 迁移至 Design Token |
|-----------|-------------------|
| `bg-white` | `bg-[var(--bg-secondary)]` |
| `text-gray-900` | `text-[var(--text-primary)]` |
| `text-gray-500` | `text-[var(--text-tertiary)]` |
| `text-gray-400` | `text-[var(--text-tertiary)]` |
| `text-gray-600` | `text-[var(--text-secondary)]` |
| `border-gray-200` | `border-[var(--border)]` |
| `bg-gray-100` / `bg-gray-200` | `bg-[var(--bg-tertiary)]` |
| `text-blue-600` | `text-[var(--accent)]` |
| `text-green-600` | `text-[var(--success)]` |
| `bg-red-600` | `bg-[var(--error)]` |

### 4.4 验收标准

- [ ] 页面内所有文本在 `bg-secondary` 或 `bg-tertiary` 上对比度 ≥ 4.5:1
- [ ] `Benchmark.tsx` 的 `opacity-75` / `opacity-90` 全部移除
- [ ] `Analytics.tsx` 中零个 `gray-*` 硬编码色值（`grep` 验证）

---

## 5. 规范四：Tooltip 边界穿透与自适应定位

### 5.1 架构：Portal + Floating UI

```
当前（absolute 定位，被父容器裁剪）：
┌─── Card (overflow:hidden) ──────────────┐
│  ┌─── Tooltip ────────────┐              │
│  │  浮层内容（被裁剪）     │  ← 看不全   │
│  └─────────────────────────┘              │
│  <span>?</span>                           │
└──────────────────────────────────────────┘

改造后（Portal 渲染到 body，fixed 定位）：
<body>
  <div id="root">...</div>
  └── <span class="tooltip-trigger">?</span>  ← 触发器留在原位
  └── <div class="tooltip-portal">            ← 浮层脱离文档流
        浮层内容（基于视口定位，碰撞检测自动翻转）
      </div>
</body>
```

### 5.2 Floating UI 中间件配置

```typescript
useFloating({
  placement: 'top',
  middleware: [
    offset(8),
    flip({
      fallbackPlacements: ['bottom', 'right', 'left'],
      padding: 8,
    }),
    shift({ padding: 8 }),
    size({
      apply({ availableWidth, elements }) {
        elements.floating.style.maxWidth =
          `${Math.min(availableWidth - 16, window.innerWidth * 0.8)}px`;
      },
    }),
  ],
})
```

### 5.3 热区桥接

规范四要求"鼠标从问号图标移动至浮层表面的过程中，热区必须保持连续且无间隙"。

实现方式：Floating UI 的 `useInteractions` 提供 `getReferenceProps` + `getFloatingProps`，自动处理：
- 鼠标离开触发器 → 进入桥接区 → 进入浮层：浮层保持打开
- 鼠标离开浮层 → 离开桥接区：150ms 延迟后关闭

### 5.4 视觉呈现

- **箭头**：CSS 三角指向触发器（`FloatingArrow` 组件）
- **入场动画**：`opacity-0 → opacity-100` + `translate-y-1 → translate-y-0`，150ms ease-out
- **文本不截断**：`size()` 中间件确保浮层宽度足够放下全部文本；禁止 `text-overflow: ellipsis`

### 5.5 API 兼容性

`<Tooltip content="...">` 接口零修改，调用方（Dashboard、CostGovernance、Search）无需改动。

### 5.6 验收标准

- [ ] 在 `Card` 有 `overflow-hidden` 的场景下，Tooltip 内容完整可见
- [ ] 空间不足时自动翻转方位（top → bottom → right → left）
- [ ] 鼠标从 `?` 图标移动到浮层，浮层不闪烁、不消失
- [ ] 浮层展开/收起不触发父容器重排
- [ ] Tooltip 文本不出现省略号截断

---

## 6. 规范二：状态持久化与数据活性

### 6.1 SafeStorage 适配器

```typescript
// src/stores/safeStorage.ts
type StorageBackend = 'localStorage' | 'sessionStorage' | 'memory';

class SafeStorage implements StateStorage {
  private backend: StorageBackend;
  private memory = new Map<string, string>();

  constructor() {
    this.backend = this.detect();
  }

  private detect(): StorageBackend {
    try {
      const k = '__safe_storage_test__';
      localStorage.setItem(k, '1');
      localStorage.removeItem(k);
      return 'localStorage';
    } catch {
      try {
        const k = '__safe_storage_test__';
        sessionStorage.setItem(k, '1');
        sessionStorage.removeItem(k);
        return 'sessionStorage';
      } catch {
        return 'memory';
      }
    }
  }

  getItem(name: string): string | null {
    try {
      if (this.backend === 'memory') return this.memory.get(name) ?? null;
      return (this.backend === 'localStorage' ? localStorage : sessionStorage).getItem(name);
    } catch {
      return this.memory.get(name) ?? null;
    }
  }

  setItem(name: string, value: string): void {
    try {
      if (this.backend === 'memory') { this.memory.set(name, value); return; }
      (this.backend === 'localStorage' ? localStorage : sessionStorage).setItem(name, value);
    } catch {
      this.memory.set(name, value);
    }
  }

  removeItem(name: string): void {
    try {
      if (this.backend === 'memory') { this.memory.delete(name); return; }
      (this.backend === 'localStorage' ? localStorage : sessionStorage).removeItem(name);
    } catch {
      this.memory.delete(name);
    }
  }
}

export const safeStorage = new SafeStorage();
```

**降级提示**：当 `backend !== 'localStorage'` 时，首次降级触发一次性 toast 提示（不阻断页面）。

### 6.2 useViewStore（用户意图快照）

```typescript
// src/stores/useViewStore.ts
interface ViewState {
  dashboardTimeRange: '1h' | '6h' | '24h' | '7d';
  analyticsTimeRange: '24h' | '7d' | '30d';
  costTimeRange: '7d' | '30d' | '90d';
  onboardingCompleted: boolean;
}

function getUserId(): string {
  try {
    const { token, apiKey } = useAuthStore.getState();
    if (token) {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.sub || 'anonymous';
    }
    if (apiKey) return `key_${apiKey.slice(0, 8)}`;
  } catch {}
  return 'anonymous';
}

export const useViewStore = create<ViewState & { _hydrated: boolean }>()(
  persist(
    (set) => ({
      dashboardTimeRange: '24h',
      analyticsTimeRange: '24h',
      costTimeRange: '30d',
      onboardingCompleted: false,
      _hydrated: false,
    }),
    {
      name: `aureon:viewstate:${getUserId()}`,
      storage: createJSONStorage(() => safeStorage),
      onRehydrateStorage: () => (state) => { state?._hydrated = true; },
      version: 1,
    }
  )
);
```

### 6.3 页面接入模式

```typescript
// Before（Dashboard.tsx:255）
const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | '7d'>('24h');

// After
const timeRange = useViewStore((s) => s.dashboardTimeRange);
const setDashboardTimeRange = useViewStore((s) => s.setDashboardTimeRange);
```

**API 调用行为**：
- `timeRange` 变化 → hook `useEffect` 重新 fetch
- 页面挂载时从 store 恢复 timeRange，立即触发一次 fetch（不使用缓存快照）
- fetch 期间展示最后已知数据 + "刷新中"状态指示器（非阻塞）

### 6.4 数据新鲜度机制

| 数据类型 | 新鲜度阈值 | 过期行为 |
|---------|-----------|---------|
| Dashboard 指标 | 实时（WebSocket） | 自动更新，无感 |
| Analytics 统计 | 5 分钟 | 点击时间范围时强制重取 |
| Cost 治理 | 5 分钟 | 点击时间范围或刷新按钮时重取 |
| Benchmark 数据 | 手动 | 仅页面挂载时 fetch 一次 |

每个 hook 暴露 `lastUpdated: number | null`，页面右上角显示"数据更新于 HH:MM:SS"。

### 6.5 useUIStore 迁移

```typescript
// Before — 裸调 localStorage，无降级
aiDisclaimerEnabled: localStorage.getItem(AI_DISCLAIMER_KEY) !== "false",

// After — zustand persist + SafeStorage
export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      mobileMenuOpen: false,
      aiDisclaimerEnabled: true,
      setMobileMenuOpen: (open) => set({ mobileMenuOpen: open }),
      toggleAiDisclaimer: () => set((s) => ({ aiDisclaimerEnabled: !s.aiDisclaimerEnabled })),
    }),
    {
      name: 'aureon:ui',
      storage: createJSONStorage(() => safeStorage),
      partialize: (state) => ({ aiDisclaimerEnabled: state.aiDisclaimerEnabled }),
    }
  )
);
```

### 6.6 验收标准

- [ ] 刷新浏览器后，三个页面的时间范围恢复到上次选择值
- [ ] 隐私模式/禁用 localStorage 的浏览器中，页面正常加载，无 `SecurityError`
- [ ] 登出后切换 API Key，视图状态不串（key 隔离）
- [ ] 数据刷新期间页面可正常交互（非阻塞）

---

## 7. 规范三：Onboarding Coach Mark 引导系统

### 7.1 组件架构

```
App.tsx
└── <OnboardingProvider>
      └── <Router>
            ├── <Dashboard />     ← 挂载 <StepAnchor name="dashboard-metrics" />
            ├── <Analytics />
            └── ...
```

核心组件：
- `OnboardingProvider`：Context Provider，持有 `currentStep`、`completed`、`dismiss()`
- `CoachMark`：聚光灯遮罩 + 浮动说明卡（复用 Floating UI 定位）
- `StepAnchor`：声明式锚点组件，标记引导步骤在 DOM 中的位置
- `steps.ts`：步骤配置数组（纯数据）

### 7.2 步骤序列（总览 → 归因 → 执行）

```typescript
export const ONBOARDING_STEPS = [
  {
    id: 'dashboard-overview',
    anchor: '[data-onboarding="dashboard-metrics"]',
    title: '总览：实时健康指标',
    description: '这是系统的核心仪表盘。延迟、流量、错误率、饱和度四大 Golden Signal 一目了然。低于阈值为绿色，超过则变红。',
    page: '/dashboard',
  },
  {
    id: 'dashboard-pipeline',
    anchor: '[data-onboarding="pipeline-breakdown"]',
    title: '归因：延迟从哪来？',
    description: 'Pipeline 分解条展示每个环节（检索→重排序→CRAG→生成）的耗时占比。哪个环节慢，一目了然。',
    page: '/dashboard',
  },
  {
    id: 'search-execute',
    anchor: '[data-onboarding="search-input"]',
    title: '执行：开始检索',
    description: '在搜索框输入问题，系统会自动路由到最合适的检索策略（简单/中等/复杂），返回带来源引用的答案。',
    page: '/search',
  },
  {
    id: 'analytics-insight',
    anchor: '[data-onboarding="analytics-overview"]',
    title: '洞察：用量与成本',
    description: 'Analytics 帮你追踪查询量、延迟分布、Token 消耗。Cost 页面进一步展示预算执行率和按用户分解。',
    page: '/analytics',
  },
] as const;
```

**语境化提示规则**（业务术语而非技术术语）：
- ✅ "系统响应速度" → ❌ "TTFT P50"
- ✅ "每个环节的耗时占比" → ❌ "Pipeline stage latency distribution"
- ✅ "预算执行率" → ❌ "Budget burn rate"

### 7.3 Coach Mark 视觉设计

- **遮罩层**：`fixed inset-0`，`rgba(0,0,0,0.72)`，`z-index: 9998`
- **聚光灯区域**：目标元素周围 4px padding 的高亮框，`border: 2px solid var(--accent-500)`
- **说明卡**：`z-index: 9999`，`bg-secondary` + `border` + 阴影，用 Floating UI `useFloating` 定位
- **导航栏**：进度点（`●○○○`）+ "下一步" 按钮 + "跳过" 链接

### 7.4 移动端适配（<768px）

```typescript
const isMobile = useMediaQuery('(max-width: 767px)');

if (isMobile) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-[9999] bg-[var(--bg-secondary)]
                    rounded-t-2xl p-6 border-t border-[var(--border)]">
      <DragHandle />
      <StepContent />
      <NavigationButtons />
    </div>
  );
}
```

### 7.5 触发与召回机制

```typescript
// 自动触发
useEffect(() => {
  const completed = useViewStore.getState().onboardingCompleted;
  if (!completed && location.pathname === '/dashboard') {
    startOnboarding();
  }
}, []);

// 完成/跳过标记
const complete = () => {
  useViewStore.setState({ onboardingCompleted: true });
  setCurrentStep(-1);
};

// 手动召回
// 顶部导航栏 "?" 下拉菜单 → "重新查看引导" → resetOnboarding()
```

### 7.6 键盘可访问性

- **ESC 键**：关闭当前引导（等同"跳过"，标记 `onboardingCompleted: true`）
- **Tab 键**：在"下一步"和"跳过"按钮之间切换焦点
- **Enter 键**：触发当前焦点按钮
- **箭头键**（可选）：← 上一步 / → 下一步

### 7.7 跨页面导航行为

引导步骤跨 2 个页面（`/dashboard` 步骤 1-2，`/search` 步骤 3，`/analytics` 步骤 4）。当用户在步骤 2 点击"下一步"需要跳转到 `/search` 时：
- 自动调用 `navigate('/search')`
- 路由完成后（`useEffect` 检测 pathname 变化），自动渲染步骤 3 的聚光灯
- 跳转期间显示轻量 loading 状态（不阻断）

### 7.8 I18n 键值

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

### 7.9 验收标准

- [ ] 首次访问 `/dashboard` 自动触发引导，覆盖 4 个步骤
- [ ] 点击"跳过"或走完最后一步后，`onboardingCompleted: true` 持久化
- [ ] 刷新页面后不再自动触发
- [ ] "?" 菜单中可手动召回"重新查看引导"
- [ ] 遮罩层外点击不关闭引导
- [ ] `<768px` 视口下自动切换为底部抽屉模式

---

## 8. 边界条件清单

### 8.1 数据为空场景

| 场景 | 表现 |
|------|------|
| Dashboard 指标无数据 | 显示"—"替代值 + 橙色"演示模式"横幅 |
| Analytics 统计为空 | "暂无数据"居中文字 |
| Cost 趋势为空 | 图表区域显示空状态占位卡 |
| Benchmark 加载失败 | 骨架屏 → 超时后 ErrorState + 重试按钮 |
| Pipeline 数据为 demo | 保留橙色"demo data"标签 |

### 8.2 权限不足场景

| 场景 | 表现 |
|------|------|
| 未认证访问 `/dashboard` | 跳转 `/login`（AuthGuard） |
| Admin 页面权限不足 | "权限不足"提示 |
| API Key 模式访问 SSO 功能 | 功能入口隐藏 |

### 8.3 网络断开场景

| 场景 | 表现 |
|------|------|
| WebSocket 断开 | `LiveIndicator` 红灯 + "离线"；数据保持最后已知值 |
| API 超时 | ErrorState + 重试按钮；已有数据不清空 |
| localStorage 降级 | 一次性 toast："浏览器存储受限，视图设置仅当前会话有效" |
| 完全不可用 | SafeStorage 降级到内存 Map；无 JS 崩溃 |

### 8.4 视口极端缩放场景

| 场景 | 表现 |
|------|------|
| Tooltip 在屏幕边缘 | Floating UI `flip` 自动翻转；`shift` 平移 |
| Coach Mark 目标在屏幕外 | `scrollIntoView({ behavior: 'smooth', block: 'center' })` |
| 说明卡超出视口 | `size` 中间件限制最大宽度 80%；禁止滚动条 |
| 移动端 Coach Mark | `<768px` 自动切换底部抽屉 |
| 极窄视口（<320px） | 说明卡撑满屏幕，左右各留 8px |

---

## 9. 非功能性兜底声明

| 声明 | 保障 |
|------|------|
| **零布局侵入** | Tooltip 用 `position: fixed`（Portal），Coach Mark 用 `fixed`，均脱离文档流 |
| **滚动条不变** | 遮罩层用 `fixed inset-0`，不改变 `body` 的 `overflow` |
| **性能影响** | SafeStorage 初始化仅一次；useViewStore 仅在状态变更时写入；最大静默轮询间隔 5 分钟 |
| **降级路径** | localStorage → sessionStorage → 内存 Map；全程 try-catch；一次性非阻断 toast |

---

## 10. 验收总清单

| 编号 | 验收项 | 规范 |
|------|-------|------|
| V-01 | 所有文本对比度 ≥ 4.5:1（WCAG AA） | 一 |
| V-02 | Benchmark.tsx 零 opacity 文本 | 一 |
| V-03 | Analytics.tsx 零 gray-* 硬编码 | 一 |
| V-04 | 刷新后 timeRange 恢复 | 二 |
| V-05 | 隐私模式无 JS 崩溃 | 二 |
| V-06 | API Key 切换不串状态 | 二 |
| V-07 | 数据刷新非阻塞 | 二 |
| V-08 | 首次访问自动触发引导 | 三 |
| V-09 | 跳过/完成后不再触发 | 三 |
| V-10 | "?" 菜单可召回引导 | 三 |
| V-11 | 移动端底部抽屉模式 | 三 |
| V-11a | ESC 键可关闭引导 | 三 |
| V-11b | 跨页面步骤自动导航 | 三 |
| V-12 | overflow-hidden 下 Tooltip 完整可见 | 四 |
| V-13 | 方位自动翻转 | 四 |
| V-14 | 热区连续不闪烁 | 四 |
| V-15 | 浮层不触发父容器重排 | 四 |
| V-16 | 文本不截断 | 四 |
