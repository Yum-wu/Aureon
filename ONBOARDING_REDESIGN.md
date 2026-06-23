# Aureon 用户引导系统重新设计

## 设计原则

基于 UX 最佳实践：

1. **聚焦价值而非功能** — 帮助用户快速获得"第一次成功"
2. **渐进式披露** — 不要一次性展示所有功能
3. **上下文帮助** — 在用户需要时提供帮助
4. **可跳过** — 尊重老用户，提供跳过选项
5. **庆祝成功** — 完成引导时给予正面反馈
6. **角色感知** — 根据用户角色显示不同引导

## 现有问题分析

### 现有引导步骤（4步）

| 步骤 | 目标 | 问题 |
|------|------|------|
| dashboard-overview | Golden Signals | ✅ 仍然有效 |
| dashboard-pipeline | RAG Pipeline | ✅ 仍然有效 |
| search-execute | 搜索功能 | ✅ 仍然有效 |
| analytics-insight | 分析页面 | ✅ 仍然有效 |

### 缺失的新功能引导

| 功能 | 优先级 | 说明 |
|------|--------|------|
| **文档管理** | 高 | 用户需要知道如何上传和管理文档 |
| **客服机器人** | 高 | 新用户最可能使用的功能 |
| **管理页面** | 中 | 仅管理员需要 |
| **FAQ 知识库** | 中 | 已索引的 6 篇 FAQ |

## 新引导系统设计

### 引导流程（5步，聚焦首次价值）

```
步骤 1: 仪表盘概览 → 了解系统状态
步骤 2: 智能搜索 → 体验核心功能
步骤 3: 文档管理 → 上传第一个文档
步骤 4: 客服助手 → 获取帮助
步骤 5: 分析洞察 → 了解使用情况
```

### 角色感知

| 角色 | 引导步骤 |
|------|----------|
| **Viewer** | 1, 2, 5 |
| **Editor** | 1, 2, 3, 4, 5 |
| **Admin** | 1, 2, 3, 4, 5 + 管理页面提示 |

### 上下文帮助（非引导场景）

| 场景 | 帮助方式 |
|------|----------|
| 首次搜索无结果 | 显示"尝试更通用的查询"提示 |
| 文档列表为空 | 显示"上传第一个文档"引导 |
| 客服按钮未点击 | 3天后显示脉冲动画提醒 |
| 管理页面首次访问 | 显示功能概览卡片 |

## 实现方案

### 1. 更新引导步骤

```typescript
// steps.ts
export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: 'dashboard-overview',
    anchor: '[data-onboarding="dashboard-metrics"]',
    titleKey: 'onboarding.steps.dashboard-overview.title',
    descriptionKey: 'onboarding.steps.dashboard-overview.description',
    page: '/dashboard',
    roles: ['VIEWER', 'EDITOR', 'ADMIN'],  // 新增：角色过滤
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
    roles: ['EDITOR', 'ADMIN'],  // 仅编辑者和管理员
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
```

### 2. 更新 i18n 文案

```json
{
  "onboarding": {
    "steps": {
      "dashboard-overview": {
        "title": "系统健康一目了然",
        "description": "这里展示 Aureon 的实时状态。延迟、流量、错误率、饱和度四大指标帮助您快速了解系统运行状况。绿色表示正常，红色需要关注。"
      },
      "search-execute": {
        "title": "智能搜索，精准回答",
        "description": "输入任何问题，Aureon 会自动选择最佳检索策略，返回带来源引用的答案。试试输入「这个平台能做什么？」"
      },
      "documents-upload": {
        "title": "知识库管理",
        "description": "上传文档让 Aureon 学习您的知识。支持 .md、.txt、.pdf、.docx、.xlsx 格式。上传后系统会自动索引，立即可用于搜索。"
      },
      "support-widget": {
        "title": "随时获取帮助",
        "description": "右下角的客服助手可以回答关于 Aureon 的任何问题。点击快捷回复或直接输入问题，获得即时帮助。"
      },
      "analytics-insight": {
        "title": "洞察使用模式",
        "description": "Analytics 页面展示查询量、延迟分布、Token 消耗等数据，帮助您优化使用策略和控制成本。"
      }
    }
  }
}
```

### 3. 上下文帮助组件

```tsx
// ContextualHelp.tsx
export function ContextualHelp({ scenario }: { scenario: string }) {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(false);
  
  // 检查是否已关闭
  useEffect(() => {
    const key = `aureon:help:${scenario}:dismissed`;
    setDismissed(localStorage.getItem(key) === 'true');
  }, [scenario]);
  
  if (dismissed) return null;
  
  const handleDismiss = () => {
    localStorage.setItem(`aureon:help:${scenario}:dismissed`, 'true');
    setDismissed(true);
  };
  
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
      <div className="flex items-start gap-3">
        <Lightbulb className="w-5 h-5 text-blue-500 mt-0.5" />
        <div className="flex-1">
          <p className="text-sm text-blue-800">{t(`help.${scenario}`)}</p>
        </div>
        <button onClick={handleDismiss} className="text-blue-400 hover:text-blue-600">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
```

### 4. 页面级上下文帮助

| 页面 | 场景 | 提示内容 |
|------|------|----------|
| Search | 首次搜索无结果 | "尝试更通用的查询，或上传相关文档" |
| Documents | 列表为空 | "点击「上传文档」开始构建知识库" |
| Dashboard | 首次访问 | "这是您的系统仪表盘，查看实时状态" |
| Admin | 首次访问 | "这里是管理中心，管理用户和配置" |

## 验证清单

- [ ] 新用户首次登录看到 5 步引导
- [ ] 老用户不重复看到引导
- [ ] Viewer 看到 3 步（不含文档管理）
- [ ] Editor/Admin 看到全部 5 步
- [ ] 客服按钮有脉冲动画提醒
- [ ] 空状态有上下文帮助
- [ ] 引导完成后显示庆祝消息
- [ ] 可通过「?」菜单重新查看引导
