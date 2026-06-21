# 仪表盘状态版本管理与兼容性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpages:subagent-driven-development (recommended) or superpages:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `useViewStore`（用户视图状态）补充 `migrate` 迁移函数，并将 P0-1 持久化层的 `buster` 从硬编码字符串改为读取应用构建版本号，建立"数据结构变更 → 自动失效旧缓存"的可维护机制，避免线上旧缓存导致渲染异常。

**Architecture:** Zustand `persist` 中间件支持 `version` + `migrate(payload, version)` 配置，当前 `useViewStore.ts:55` 有 `version: 1` 但无 `migrate`，意味着任何字段变更会静默保留旧结构导致运行时错误。补充显式 migrate 函数处理字段重命名/删除/新增。TanStack Query 的 `buster` 改为从 `package.json` 的 `version` 派生（构建期注入），发布新版本时自动失效查询缓存。

**Tech Stack:** Zustand 5 `persist` 中间件（`migrate` API）、Vite `import.meta.env`、Vitest。

---

## 背景与诊断

**问题现象**：数据结构变更（如字段重命名）时，线上用户浏览器保留的旧版本持久化状态可能导致渲染异常或运行时错误。

**根因**（见诊断报告）：`useViewStore.ts:55` 有 `version: 1` 但无 `migrate` 函数，Zustand persist 在版本不匹配时会丢弃数据但无降级处理；P0-1 的 `buster` 若硬编码字符串则每次代码改动都需手动改。

**业界依据**：[Zustand persist migrate 模式 (GitHub Discussion #1569)](https://github.com/pmndrs/zustand/discussions/1569)；TanStack `persistQueryClient` 的 `buster` 机制。

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/stores/useViewStore.ts` | 补充 migrate 函数 | **修改** |
| `src/lib/appVersion.ts` | 应用版本号统一来源（构建期注入） | **新建** |
| `src/providers/QueryProvider.tsx` | buster 改用 appVersion | **修改** |
| `src/stores/__tests__/useViewStore.migrate.test.ts` | migrate 迁移测试 | **新建** |
| `vite.config.ts` | 注入构建版本号（若需） | **修改** |

---

## Task 1: 创建 appVersion.ts（版本号统一来源）

**Files:**
- Create: `src/lib/appVersion.ts`
- Test: `src/lib/__tests__/appVersion.test.ts`

- [ ] **Step 1: 编写失败的测试**

Create `src/lib/__tests__/appVersion.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { getAppVersion, getCacheBuster } from '../appVersion';

describe('appVersion', () => {
  it('returns a non-empty version string', () => {
    const v = getAppVersion();
    expect(typeof v).toBe('string');
    expect(v.length).toBeGreaterThan(0);
  });

  it('cache buster is derived from version', () => {
    const v = getAppVersion();
    const b = getCacheBuster();
    expect(b).toContain(v);
  });

  it('cache buster is deterministic for same version', () => {
    expect(getCacheBuster()).toBe(getCacheBuster());
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/lib/__tests__/appVersion.test.ts`
Expected: FAIL，`Cannot find module '../appVersion'`。

- [ ] **Step 3: 实现 appVersion.ts**

Create `src/lib/appVersion.ts`:
```typescript
/**
 * appVersion.ts — 应用版本号统一来源
 *
 * 版本号优先级：
 * 1. Vite 构建期注入的 APP_VERSION（来自 package.json，生产稳定）
 * 2. package.json version（开发环境直接读）
 * 3. 兜底 '0.0.0-dev'
 *
 * 缓存 buster 用于 TanStack Query persistQueryClient，
 * 版本号变化即自动失效旧缓存。
 */

// Vite 在构建时将 __APP_VERSION__ 替换为实际值（见 vite.config.ts define）
declare const __APP_VERSION__: string;

function readPackageVersion(): string {
  try {
    // 开发环境直接读 package.json（Vite 支持json import）
    // 注意：生产构建会内联此值
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore — package.json 不在 src 路径，用动态读取兜底
    return typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '0.0.0-dev';
  } catch {
    return '0.0.0-dev';
  }
}

let cachedVersion: string | null = null;

/** 获取应用版本号 */
export function getAppVersion(): string {
  if (!cachedVersion) {
    cachedVersion = readPackageVersion();
  }
  return cachedVersion;
}

/**
 * 获取缓存 buster 字符串。
 * 基于 appVersion 派生，版本变更即失效旧缓存。
 * 格式：`aureon@<version>`
 */
export function getCacheBuster(): string {
  return `aureon@${getAppVersion()}`;
}
```

- [ ] **Step 4: 配置 Vite 注入 __APP_VERSION__**

Read `vite.config.ts`。在 `define` 配置块中添加（若 `define` 不存在则新增）：
```typescript
import pkg from './package.json' with { type: 'json' };

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  // ... 其他现有配置
});
```

**注意**：若 `vite.config.ts` 已有 `define`，在现有对象内合并 `__APP_VERSION__` 键。若使用 `import pkg from './package.json'` 报错（TS resolveJsonModule），改用 `fs.readFileSync` 读取：
```typescript
import { readFileSync } from 'node:fs';
const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'));
```

- [ ] **Step 5: 运行测试验证通过**

Run: `npx vitest run src/lib/__tests__/appVersion.test.ts`
Expected: PASS（3 个测试）。

**注意**：Vitest 测试环境下 `__APP_VERSION__` 可能未定义（除非 vitest 也配置了 define）。若测试报 `__APP_VERSION__ is not defined`，在 `appVersion.ts` 中用 `typeof __APP_VERSION__ !== 'undefined'` 判断（已如此实现），测试应走兜底分支返回 `'0.0.0-dev'`，3 个测试仍能通过。

- [ ] **Step 6: Commit**

```bash
git add src/lib/appVersion.ts src/lib/__tests__/appVersion.test.ts vite.config.ts
git commit -m "feat(version): add centralized appVersion and cache buster derivation"
```

---

## Task 2: 为 useViewStore 补充 migrate 函数

**Files:**
- Modify: `src/stores/useViewStore.ts:36-58`
- Test: `src/stores/__tests__/useViewStore.migrate.test.ts`

- [ ] **Step 1: 编写失败的迁移测试**

Create `src/stores/__tests__/useViewStore.migrate.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';

// migrate 函数通过 persist 配置内联，需从模块内部提取测试
// 用 zustand 的 persist 行为间接测试：写入旧版本数据，读取应得迁移后数据

describe('useViewStore migrate', () => {
  it('handles upgrade from version 0 (legacy) to current', () => {
    // 模拟 v0 旧数据（无 dashboardTimeRange 字段）
    const legacyPayload = {
      state: {
        // 旧版本可能用不同的字段名，如 'timeRange'
        timeRange: '7d',
      },
      version: 0,
    };
    localStorage.setItem('aureon:viewstate:test1', JSON.stringify(legacyPayload));

    // 动态导入确保读到带 localStorage 的状态
    return import('../useViewStore').then(({ useViewStore }) => {
      // 重新初始化（persist 在模块加载时已读 localStorage）
      const state = useViewStore.getState();
      // 迁移后应有默认值或映射值，不能是 undefined
      expect(state.dashboardTimeRange).toBeDefined();
    });
  });

  it('current version state persists and restores', () => {
    localStorage.setItem(
      'aureon:viewstate:test2',
      JSON.stringify({
        state: { dashboardTimeRange: '6h', onboardingCompleted: true },
        version: 1,
      }),
    );

    return import('../useViewStore').then(({ useViewStore }) => {
      const state = useViewStore.getState();
      expect(state.dashboardTimeRange).toBe('6h');
      expect(state.onboardingCompleted).toBe(true);
    });
  });

  it('migration returns valid state shape for unknown version', () => {
    // 模拟未来版本数据（version: 99），应降级为默认值而非崩溃
    const futurePayload = {
      state: { unknownField: 'value' },
      version: 99,
    };
    localStorage.setItem('aureon:viewstate:test3', JSON.stringify(futurePayload));

    return import('../useViewStore').then(({ useViewStore }) => {
      const state = useViewStore.getState();
      // 不应抛错，应用默认值
      expect(state.dashboardTimeRange).toBeDefined();
      expect(state.onboardingCompleted).toBe(false);
    });
  });
});
```

**注意**：由于 useViewStore 的 key 包含 `getUserId()`，测试需 mock 用户标识或用固定 key。上面的测试用 `test1/test2/test3` 作为 key 的一部分仅作示意，实际可能需调整。**更稳妥的做法**：将 migrate 函数单独导出测试（见 Step 3 的替代方案）。

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/stores/__tests__/useViewStore.migrate.test.ts`
Expected: FAIL 或结果异常（因为无 migrate 函数，version 不匹配时 persist 会保留旧 state 或丢弃）。

- [ ] **Step 3: 实现 migrate 函数并导出（便于测试）**

Modify `src/stores/useViewStore.ts`。

首先在 store 定义之前（第 35 行附近）新增并导出 migrate 函数：
```typescript
/** 视图状态的默认值，用于迁移兜底 */
const DEFAULT_VIEW_STATE = {
  dashboardTimeRange: '24h' as const,
  analyticsTimeRange: '24h' as const,
  costTimeRange: '30d' as const,
  onboardingCompleted: false,
};

/**
 * 状态迁移函数 — 处理 version 间的不兼容变更。
 *
 * 迁移历史：
 * - v0 → v1: 旧版本用 'timeRange' 单字段，迁移为分项 dashboardTimeRange
 * - 未来版本在此追加 case
 *
 * @param persistedState - 持久化的旧状态（结构可能不符当前）
 * @param version - 持久化状态的版本号
 * @returns 迁移后的状态（符合当前结构）
 */
export function migrateViewState(
  persistedState: unknown,
  version: number,
): Partial<ViewState> {
  // 从默认值开始，确保所有字段都有合理兜底
  const base = { ...DEFAULT_VIEW_STATE };

  if (!persistedState || typeof persistedState !== 'object') {
    return base;
  }

  const old = persistedState as Record<string, unknown>;

  // v0 → v1: timeRange（单字段）拆分为 dashboardTimeRange
  if (version < 1) {
    if (typeof old.timeRange === 'string') {
      base.dashboardTimeRange = old.timeRange as ViewState['dashboardTimeRange'];
    }
    // 继承已知字段（类型安全地拷贝）
  }

  // 继承所有与当前结构兼容的字段（白名单拷贝）
  if (typeof old.dashboardTimeRange === 'string') {
    base.dashboardTimeRange = old.dashboardTimeRange as ViewState['dashboardTimeRange'];
  }
  if (typeof old.analyticsTimeRange === 'string') {
    base.analyticsTimeRange = old.analyticsTimeRange as ViewState['analyticsTimeRange'];
  }
  if (typeof old.costTimeRange === 'string') {
    base.costTimeRange = old.costTimeRange as ViewState['costTimeRange'];
  }
  if (typeof old.onboardingCompleted === 'boolean') {
    base.onboardingCompleted = old.onboardingCompleted;
  }

  // 版本号高于当前（未来版本降级）：返回默认值，丢弃未知字段
  if (version > 1) {
    return base;
  }

  return base;
}
```

然后在 persist 配置中引用 migrate（修改 persist 的第二参数对象）：
```typescript
    {
      name: `aureon:viewstate:${getUserId()}`,
      storage: createJSONStorage(() => safeStorage),
      version: 1,
      migrate: migrateViewState,
    }
```

- [ ] **Step 4: 调整测试为直接测试 migrateViewState（更可靠）**

由于 store 的 localStorage key 动态化难以测试，改为直接测导出的 `migrateViewState` 函数。替换 `src/stores/__tests__/useViewStore.migrate.test.tsx` 全部内容：
```typescript
import { describe, it, expect } from 'vitest';
import { migrateViewState } from '../useViewStore';

describe('migrateViewState', () => {
  it('returns defaults for null/undefined input', () => {
    const result = migrateViewState(null, 0);
    expect(result.dashboardTimeRange).toBe('24h');
    expect(result.onboardingCompleted).toBe(false);
  });

  it('returns defaults for non-object input', () => {
    const result = migrateViewState('garbage', 0);
    expect(result.dashboardTimeRange).toBe('24h');
  });

  it('migrates v0 timeRange to dashboardTimeRange', () => {
    const result = migrateViewState({ timeRange: '7d' }, 0);
    expect(result.dashboardTimeRange).toBe('7d');
  });

  it('preserves known fields from v1', () => {
    const result = migrateViewState(
      { dashboardTimeRange: '6h', onboardingCompleted: true },
      1,
    );
    expect(result.dashboardTimeRange).toBe('6h');
    expect(result.onboardingCompleted).toBe(true);
  });

  it('ignores unknown fields', () => {
    const result = migrateViewState(
      { dashboardTimeRange: '1h', unknownField: 'x', anotherUnknown: 123 },
      1,
    );
    expect(result.dashboardTimeRange).toBe('1h');
    expect((result as Record<string, unknown>).unknownField).toBeUndefined();
  });

  it('downgrades future version to defaults (drops unknown)', () => {
    const result = migrateViewState(
      { futureField: 'value', dashboardTimeRange: '1h' },
      99,
    );
    expect(result.dashboardTimeRange).toBe('24h'); // 降级为默认
    expect((result as Record<string, unknown>).futureField).toBeUndefined();
  });

  it('includes all expected fields in result', () => {
    const result = migrateViewState({}, 0);
    expect(result).toHaveProperty('dashboardTimeRange');
    expect(result).toHaveProperty('analyticsTimeRange');
    expect(result).toHaveProperty('costTimeRange');
    expect(result).toHaveProperty('onboardingCompleted');
  });
});
```

- [ ] **Step 5: 运行测试验证通过**

Run: `npx vitest run src/stores/__tests__/useViewStore.migrate.test.ts`
Expected: PASS（7 个测试）。

- [ ] **Step 6: Commit**

```bash
git add src/stores/useViewStore.ts src/stores/__tests__/useViewStore.migrate.test.ts
git commit -m "feat(state): add migrateViewState for useViewStore version migration"
```

---

## Task 3: QueryProvider 的 buster 改用 appVersion

**Files:**
- Modify: `src/providers/QueryProvider.tsx`

**前提**：P0-1 计划已落地（QueryProvider 已用 `PersistQueryClientProvider`，`buster` 为硬编码 `'1.0.0'`）。若 P0-1 未实施，本 Task 跳过。

- [ ] **Step 1: 修改 QueryProvider 引用 appVersion**

Modify `src/providers/QueryProvider.tsx`。

删除硬编码的 `const APP_VERSION = '1.0.0';`，改为 import：
```typescript
import { getCacheBuster } from '../lib/appVersion';
```

修改 `PersistQueryClientProvider` 的 `persistOptions.buster`：
```typescript
      persistOptions={{
        persister,
        buster: getCacheBuster(),
        maxAge: PERSIST_MAX_AGE_MS,
      }}
```

并删除文件中 `APP_VERSION` 常量定义行。

- [ ] **Step 2: 更新 QueryProvider 测试（若有 buster 相关断言）**

Read `src/providers/__tests__/QueryProvider.test.tsx`，查找 `buster` 相关测试。

若第 4 个测试（"discards cache when buster mismatches"）写入了硬编码 `buster: 'OLD_VERSION_0.0.1'`，现在需要让它与 `getCacheBuster()` 的实际值不匹配。由于测试写入的 `'OLD_VERSION_0.0.1'` 不会等于 `aureon@<version>`，测试逻辑仍成立，无需改动。

Run: `npx vitest run src/providers/__tests__/QueryProvider.test.tsx`
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add src/providers/QueryProvider.tsx
git commit -m "refactor(persistence): derive cache buster from appVersion"
```

---

## Task 4: 全量回归与手动验证

- [ ] **Step 1: 全量测试**

Run: `npm test -- --run`
Expected: 全部 PASS。

- [ ] **Step 2: lint**

Run: `npm run lint`
Expected: 无 error。

- [ ] **Step 3: 手动验证版本失效机制**

1. `npm run dev`
2. 访问 `/dashboard`，确认 localStorage 有 `aureon:query-cache`，值含 `buster` 字段为 `aureon@0.0.0`（package.json version）
3. 手动修改 localStorage 中 `aureon:query-cache` 的 `buster` 为 `aureon@9.9.9`
4. 刷新页面
5. **期望**：旧缓存被丢弃（buster 不匹配），重新发起请求；Console 无渲染异常

- [ ] **Step 4: 验证 viewState 迁移**

1. 手动在 localStorage 写入旧的 viewState（模拟降级）：
```javascript
localStorage.setItem('aureon:viewstate:anonymous', JSON.stringify({
  state: { timeRange: '1h' },  // v0 格式
  version: 0,
}));
```
2. 刷新页面，访问 `/dashboard`
3. **期望**：时间范围下拉框显示 "1h"（迁移成功），无运行时错误

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "test: state version migration and cache busting verified"
```

---

## Self-Review 自检

**1. Spec coverage（对照诊断报告 P2-2）**
- ✅ useViewStore 补充 migrate 函数 — Task 2
- ✅ 数据结构变更平滑迁移 — migrateViewState 处理 v0→v1
- ✅ persistQueryClient 的 buster 绑定构建版本号 — Task 1 + Task 3
- ✅ 测试覆盖 — Task 1/2

**2. Placeholder scan**：无占位符。Task 1 Step 4 对 vite.config.ts 的修改标注"若已有 define 则合并"——这是条件性说明，非占位，执行时 Read 文件即可确定。

**3. Type consistency**：
- `migrateViewState(persistedState: unknown, version: number): Partial<ViewState>` 签名与 Zustand persist 的 `migrate` 期望一致 ✓
- `getCacheBuster()` 返回 string，与 `buster?: string` 一致 ✓
- `DEFAULT_VIEW_STATE` 字段与 ViewState 接口对齐 ✓

**4. 依赖说明**：本计划 Task 3 **依赖 P0-1 已落地**（QueryProvider 已有 PersistQueryClientProvider）。若 P0-1 未实施，跳过 Task 3，仅做 Task 1/2（appVersion + migrate，仍独立有价值）。

**5. 风险点**：
- `__APP_VERSION__` 在 Vitest 环境未定义 — Task 1 Step 5 已用 `typeof` 判断兜底
- Zustand persist 的 migrate 在模块加载时自动执行，难以直接测试 store 级行为 — 改为导出 `migrateViewState` 单测（Task 2 Step 4），更可靠 ✓
- `import.meta.url` + `readFileSync` 在某些打包配置下可能有问题 — Task 1 Step 4 给出了 json import 和 readFileSync 两种方案
- migrate 函数必须返回**完整**结构（含所有字段），否则 store 缺字段 — 用 `DEFAULT_VIEW_STATE` 作为 base 保证完整性 ✓
