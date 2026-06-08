# Aureon 客服助手设计方案

**版本**: v1.0
**日期**: 2026-06-07
**状态**: Approved

---

## 概述

为 Aureon 平台添加 AI 客服助手功能，以右下角浮动 Widget 形式帮助访客了解平台功能和使用方式。复用现有 WebSocket 基础设施，零后端架构改动。

## 需求

| 项目 | 决策 |
|------|------|
| 位置 | 右下角浮动按钮（所有页面） |
| 知识范围 | Aureon 产品专属知识 |
| Quick Replies | 预设 3-4 个快捷问题 |
| 后端 | WebSocket（复用现有 /ws/chat/{client_id}） |
| 认证 | 公开访问（无需登录） |

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                        App.tsx                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Router (Landing / Dashboard / Search / ...)            │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  <SupportWidget />  ← 全局挂载，所有页面可见              │ │
│  │                                                          │ │
│  │  ┌──────┐    ┌────────────────────────────────────┐    │ │
│  │  │ FAB  │ →  │ 展开面板（ChatWidget 精简版）        │    │ │
│  │  │ (?)  │    │ - Header + Connection Status        │    │ │
│  │  └──────┘    │ - Quick Replies (3-4 个)            │    │ │
│  │              │ - Message List                      │    │ │
│  │              │ - Streaming Text                    │    │ │
│  │              │ - Input + Send Button               │    │ │
│  │              └────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                          │ WebSocket
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                           │
│  /ws/chat/{client_id}  ← 复用现有 WebSocket endpoint          │
│  - metadata.mode = "support" 触发客服专属 Prompt               │
│  - 知识库：Aureon 产品文档（已有 40 篇）                      │
└─────────────────────────────────────────────────────────────┘
```

## 前端组件设计

### 组件：SupportWidget.tsx

**文件**: `src/components/SupportWidget.tsx` (~200 行)

**状态**:
```typescript
interface SupportWidgetState {
  isOpen: boolean;         // 是否展开聊天面板
  isConnected: boolean;    // WebSocket 连接状态
  messages: ChatMessage[]; // 消息历史
  isStreaming: boolean;    // 正在流式输出
  streamingText: string;   // 当前流式文本
  error: string | null;    // 错误信息
}
```

**预设快捷问题**:
```typescript
const QUICK_REPLIES = {
  en: [
    "What can this platform do?",
    "How to deploy to production?",
    "Which LLM models are supported?",
    "What are the performance metrics?",
  ],
  zh: [
    "这个平台能做什么？",
    "如何部署到生产环境？",
    "支持哪些 LLM 模型？",
    "性能指标怎么样？",
  ],
};
```

### UI 布局

**收起状态（FAB）**:
- 右下角固定定位
- 56×56px 圆形按钮
- `var(--accent)` 背景色 + 白色问号图标
- 带 pulse 动画吸引注意

**展开状态（面板）**:
- 400px × 600px 固定尺寸
- 移动端 (< 640px) 全屏
- 使用现有 Design Token
- glass 毛玻璃效果

```
┌──────────────────────────┐
│ Aureon Support    ● 在线 │  Header
├──────────────────────────┤
│                          │
│  ? 你好！我是 Aureon    │  Welcome + Quick Replies
│  客服助手，有什么可以    │
│  帮助您？                │
│                          │
│  ┌────────────────────┐  │
│  │ 这个平台能做什么？  │  │
│  └────────────────────┘  │
│  ┌────────────────────┐  │
│  │ 如何部署到生产环境？│  │
│  └────────────────────┘  │
│                          │
├──────────────────────────┤
│ [输入消息...]      [发送] │  Input
└──────────────────────────┘
```

### 样式规范

- FAB: `var(--accent)` 背景，白色图标
- 面板: `var(--bg-secondary)` 背景，`glass` 效果
- 消息气泡: 用户 = `var(--accent)`，助手 = `var(--bg-tertiary)`
- Quick Reply: 边框按钮，hover 变 `var(--accent-soft)`

## 后端改动

### 核心策略：零架构改动

现有 WebSocket endpoint 已支持所有必要功能：
- ? 多轮对话（ConversationManager）
- ? 流式 RAG 响应（rag_query_astream）
- ? 来源引用（sources event）
- ? 心跳监控
- ? 自动重连

### System Prompt 差异

**修改文件**: `backend/app/api/websocket_chat.py`

```python
def _get_system_prompt(mode: str = "general") -> str:
    """Get system prompt based on mode."""
    if mode == "support":
        return """你是 Aureon 企业 AI 知识库平台的客服助手。

你的职责：
1. 帮助访客了解 Aureon 平台的功能和特性
2. 解答部署、配置、使用相关问题
3. 引导访客发现平台的核心价值

产品知识：
- 企业 AI 知识库平台（FastAPI + React 19）
- 核心能力：95% Recall@3 混合搜索、92% Context Precision、97% Faithfulness
- 部署方式：Docker + Railway 一键部署，24 小时内完成
- 支持模型：DeepSeek / GPT-4o / Claude
- 特色功能：Semantic Cache、Adaptive Re-ranking、WebSocket 实时流式

回答规则：
1. 基于检索到的文档回答，不编造信息
2. 简洁专业，每次回答不超过 200 字
3. 适当推荐相关功能（如提到搜索时介绍 Hybrid Search）
4. 无法回答时引导至 /search 页面或联系邮箱
"""
    # 现有通用 prompt
    return """你是 Aureon 企业 AI 知识库助手。..."""
```

**调用方式**:
```python
# websocket_chat.py 中 _handle_user_message
metadata = data.get("metadata", {})
mode = metadata.get("mode", "general")
messages = conv_manager.get_context_messages(
    conversation_id,
    system_prompt=_get_system_prompt(mode),
)
```

## 集成点

### App.tsx 全局挂载

```tsx
function AppLayout() {
  const location = useLocation();
  const isLanding = location.pathname === "/";
  const isLogin = location.pathname === "/login";
  
  return (
    <div className="h-screen flex flex-col">
      {/* 现有导航（Landing/Login 隐藏）*/}
      {!isLanding && !isLogin && <nav>...</nav>}
      
      {/* 现有路由内容 */}
      <div className="flex-1 overflow-auto">
        <Routes>...</Routes>
      </div>
      
      {/* 全局客服 Widget（登录页隐藏） */}
      {!isLogin && <SupportWidget />}
    </div>
  );
}
```

**注意**: Landing 页面无导航栏但有 Widget，Login 页面两者都无。

### WebSocket Metadata 传递

```typescript
// websocket.ts 修改 sendUserMessage
sendUserMessage(query: string, metadata?: Record<string, any>): void {
  this.send({
    type: 'user_message',
    query,
    metadata: { mode: 'support', ...metadata },  // 新增 mode
    conversation_id: this.conversationId,
  });
}
```

## 文件变更清单

| 文件 | 操作 | 说明 | 预估行数 |
|------|------|------|---------|
| `src/components/SupportWidget.tsx` | 新建 | 浮动客服组件 | ~200 |
| `src/App.tsx` | 修改 | 全局挂载 (+3 行) | +3 |
| `src/services/websocket.ts` | 修改 | metadata 传递 (+5 行) | +5 |
| `backend/app/api/websocket_chat.py` | 修改 | 客服 Prompt (+15 行) | +15 |
| `src/i18n/en.json` + `zh.json` | 修改 | 客服翻译 (+10 键) | +20 |
| `src/components/__tests__/SupportWidget.test.tsx` | 新建 | 单元测试 | ~80 |

## 测试策略

### 单元测试：SupportWidget.test.tsx

1. **FAB 按钮点击展开/收起**
2. **Quick Reply 点击发送消息**
3. **连接状态正确显示**
4. **流式文本正确渲染**
5. **移动端全屏响应式**

### 手动验证清单

- [ ] Landing Page (`/`) → 右下角出现气泡
- [ ] 点击展开 → 显示欢迎语 + 快捷问题
- [ ] 点击快捷问题 → 流式回答（< 500ms TTFT）
- [ ] 切换页面 → Widget 保持打开状态
- [ ] 登录页 → Widget 隐藏
- [ ] WebSocket 断开 → 显示连接状态

## 预估工时

| 任务 | 预估时间 |
|------|---------|
| SupportWidget.tsx 开发 | 1.5 小时 |
| App.tsx 集成 | 15 分钟 |
| 后端 Prompt 修改 | 30 分钟 |
| i18n 翻译 | 30 分钟 |
| 单元测试 | 45 分钟 |
| 手动验证 + 修复 | 30 分钟 |
| **总计** | **~4 小时** |

## 后续扩展（不在本次范围）

- 页面感知：根据当前路由推荐不同问题
- 对话历史：localStorage 持久化
- 主动问候：首次访问延迟弹出
- 离线模式：WebSocket 断开时降级为 FAQ
- 满意度调查：对话结束后评分

---

*设计文档版本: v1.0*
*创建日期: 2026-06-07*
*状态: Approved*
