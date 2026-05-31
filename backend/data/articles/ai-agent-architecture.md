---
title: "AI Agent 架构设计"
slug: "ai-agent-architecture"
language: "zh"
source: "ai-agent-architecture.md"
---

# AI Agent 架构设计

## 什么是 AI Agent

AI Agent 是一个能够自主感知环境、制定计划、调用工具并执行任务的智能系统。与简单的 LLM 调用不同，Agent 具备**自主决策能力**——它可以根据中间结果动态调整行动策略，而非按固定流程执行。

核心组件：LLM（大脑）+ Tools（工具）+ Memory（记忆）+ Planning（规划）

## ReAct 模式

ReAct（Reasoning + Acting）是最经典的 Agent 模式，交替进行推理和行动：

```
Thought: 用户想知道北京今天的天气。我需要调用天气 API。
Action: search_weather(city="北京")
Observation: 北京今天晴，气温 28°C
Thought: 已经获取到天气信息，可以回答用户了。
Answer: 北京今天天气晴朗，气温 28°C，适合外出。
```

ReAct 的核心循环：`Thought → Action → Observation → Thought → ... → Answer`

### LangChain 实现

```python
from langchain.agents import create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

react_prompt = PromptTemplate.from_template("""
Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}
""")

agent = create_react_agent(
    llm=ChatOpenAI(model="gpt-4o"),
    tools=tools,
    prompt=react_prompt
)
```

## Tool Calling

Tool Calling 是 Agent 与外部世界交互的机制，让 LLM 能够调用函数、API、数据库等：

### 工具定义

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# 方式 1：简单工具
@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气信息"""
    return f"{city}今天晴，25°C"

# 方式 2：带结构化输入
class SearchInput(BaseModel):
    query: str = Field(description="搜索关键词")
    max_results: int = Field(default=5, description="最大结果数")

@tool(args_schema=SearchInput)
def web_search(query: str, max_results: int = 5) -> str:
    """搜索网页获取信息"""
    results = perform_search(query, max_results)
    return str(results)

# 方式 3：数据库查询工具
@tool
def query_database(sql: str) -> str:
    """执行 SQL 查询（只读）"""
    # 安全校验：禁止 INSERT/UPDATE/DELETE
    if any(keyword in sql.upper() for keyword in ["INSERT", "UPDATE", "DELETE", "DROP"]):
        return "错误：不允许执行写操作"
    result = db.execute(sql)
    return str(result)
```

### 工具安全原则

1. **最小权限**：工具只暴露必要能力
2. **输入校验**：使用 Pydantic 做结构化验证
3. **沙箱执行**：避免 `eval`、`exec` 等危险操作
4. **速率限制**：对 API 调用类工具设置频率限制
5. **只读优先**：数据库工具默认只读，写操作需要额外确认

## 记忆系统

### 短期记忆（Short-term Memory）

管理当前对话的上下文窗口：

```python
from langgraph.checkpoint.memory import MemorySaver

# 对话缓冲
from langchain.memory import ConversationBufferMemory
memory = ConversationBufferMemory(return_messages=True)

# 滑动窗口（只保留最近 N 轮）
from langchain.memory import ConversationBufferWindowMemory
memory = ConversationBufferWindowMemory(k=10)

# 摘要压缩（适合长对话）
from langchain.memory import ConversationSummaryBufferMemory
memory = ConversationSummaryBufferMemory(
    llm=llm,
    max_token_limit=2000  # 超过 2000 token 自动压缩
)
```

### 长期记忆（Long-term Memory）

跨会话持久化的记忆：

```python
from langgraph.checkpoint.sqlite import SqliteSaver

# 持久化到 SQLite
checkpointer = SqliteSaver.from_conn_string("memory.db")

# LangGraph Agent 自动支持
from langgraph.graph import StateGraph, MessagesState

graph = StateGraph(MessagesState)
# ... 添加节点和边 ...

app = graph.compile(checkpointer=checkpointer)

# 使用时指定 thread_id
config = {"configurable": {"thread_id": "user-123"}}
result = app.invoke({"messages": [("user", "我想学习 Python")]}, config)
```

### 记忆存储方案对比

| 方案 | 持久化 | 容量 | 查询能力 | 适用场景 |
|------|-------|------|---------|---------|
| BufferMemory | 否 | 小 | 无 | 简单对话 |
| SummaryMemory | 否 | 中 | 无 | 长对话 |
| SQLite Checkpointer | 是 | 中 | 基础 | 单用户应用 |
| Redis | 是 | 大 | 基础 | 高并发 |
| 向量数据库 | 是 | 大 | 语义搜索 | 知识检索型记忆 |

## 多 Agent 系统

### 架构模式

**1. 主从模式（Orchestrator-Worker）**：

```python
from langgraph.graph import StateGraph, MessagesState, START, END

# 编排者负责分配任务，Worker 负责执行
orchestrator_prompt = """你是一个项目协调者。根据用户需求，
将任务分配给合适的专家。

可用专家：
- researcher：负责信息搜集和调研
- coder：负责代码编写
- reviewer：负责代码审查
"""
```

**2. 对话模式（Debate/Consensus）**：

多个 Agent 就同一问题给出不同观点，通过讨论达成共识。

**3. 流水线模式（Pipeline）**：

```python
# 每个 Agent 处理特定环节
pipeline = (
    researcher_agent |  # 调研
    coder_agent |       # 实现
    reviewer_agent      # 审查
)
```

### LangGraph 多 Agent 编排

```python
from langgraph.graph import StateGraph, MessagesState
from typing import Literal

def researcher(state: MessagesState):
    """调研 Agent"""
    # 执行调研任务
    return {"messages": [("assistant", "调研结果...")]}

def coder(state: MessagesState):
    """编码 Agent"""
    return {"messages": [("assistant", "代码实现...")]}

def reviewer(state: MessagesState):
    """审查 Agent"""
    return {"messages": [("assistant", "审查意见...")]}

def router(state: MessagesState) -> Literal["researcher", "coder", "reviewer", END]:
    last_msg = state["messages"][-1].content
    if "需要调研" in last_msg:
        return "researcher"
    elif "需要编码" in last_msg:
        return "coder"
    elif "需要审查" in last_msg:
        return "reviewer"
    return END

# 构建图
graph = StateGraph(MessagesState)
graph.add_node("researcher", researcher)
graph.add_node("coder", coder)
graph.add_node("reviewer", reviewer)
graph.add_edge(START, "researcher")
graph.add_conditional_edges("researcher", router)

app = graph.compile()
```

## Agent vs Chain vs Function Calling

| 维度 | Chain | Function Calling | Agent |
|------|-------|-----------------|-------|
| 执行流程 | 固定线性 | LLM 决定调用哪个函数 | 动态多步 |
| 自主性 | 无 | 有限（单轮） | 高（多轮循环） |
| 适用场景 | 简单流水线 | 单次工具调用 | 复杂多步任务 |
| token 消耗 | 低 | 中 | 高 |
| 可预测性 | 高 | 中 | 低 |
| 实现复杂度 | 低 | 低 | 中高 |

**选择指南**：
- 步骤固定、不需要分支 → **Chain**
- 需要调用 1-2 个工具 → **Function Calling**
- 需要动态决策、多步推理 → **Agent**
- 需要状态持久化和循环 → **LangGraph Agent**

## 生产环境考虑

1. **可观测性**：记录每个 Agent 的 Thought/Action/Observation，便于调试
2. **超时控制**：设置 Agent 最大循环次数和总时间限制，避免无限循环
3. **错误恢复**：Tool 调用失败时的降级策略（重试、跳过、换工具）
4. **成本控制**：监控 token 消耗，设置单次请求上限
5. **并行执行**：无依赖的 Tool 可并行调用，降低延迟
6. **人机协作**：关键决策点加入 Human-in-the-loop 确认
