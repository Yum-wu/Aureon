# LangFuse RAG 追踪集成

## LangFuse 简介

LangFuse 是开源的 LLM 应用可观测性平台，提供全链路追踪、Prompt 管理、评估和成本分析。Aureon 使用 LangFuse Cloud 作为 RAG 追踪平台。

## 集成架构

```
Aureon FastAPI → LangChain Agent → astream_events → LangFuse CallbackHandler → LangFuse Cloud
```

### 三个核心函数

1. **`init_langfuse()`**：FastAPI lifespan startup 中调用，初始化 CallbackHandler 并验证连接
2. **`get_langfuse_handler()`**：返回 CallbackHandler 单例，注入到 astream_events 的 config
3. **`shutdown_langfuse()`**：lifespan shutdown 中调用，flush 所有待发送事件

### 配置参数

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| 启用 | LANGFUSE_ENABLED | true/false |
| 公钥 | LANGFUSE_PUBLIC_KEY | LangFuse 项目公钥 |
| 密钥 | LANGFUSE_SECRET_KEY | LangFuse 项目密钥 |
| 端点 | LANGFUSE_HOST | 默认 https://cloud.langfuse.com |
| 版本 | LANGFUSE_RELEASE | 部署版本标记 |

## 自动追踪内容

LangFuse CallbackHandler 自动追踪以下内容：

1. **LLM 调用**：输入 Prompt、输出内容、Token 使用量、延迟
2. **Tool 调用**：工具名称、输入参数、输出结果
3. **Chain 步骤**：检索、Rerank、压缩等步骤的输入输出
4. **Session 标签**：session_id 自动映射到 trace 的 session 标签

## 追踪 URL

```python
def get_trace_url(trace_id: str) -> str:
    """生成 trace 链接，可直接跳转到 LangFuse 控制台"""
    return f"{settings.LANGFUSE_HOST}/trace/{trace_id}"
```

## 关键事实

1. **LangFuse 通过 CallbackHandler 自动追踪 LLM 调用、Tool 调用和 Chain 步骤**，无需手动埋点
2. **session_id 自动映射到 LangFuse trace 的 session 标签**，支持按会话查看完整对话追踪
3. **`init_langfuse()` 在 startup 时异步 check_connection 验证凭据**，确保追踪可用
4. **`shutdown_langfuse()` 在 shutdown 时 flush 所有待发送事件**，避免数据丢失
5. **LangFuse 支持东京区域端点**，新加坡近端推荐使用东京区域降低延迟
