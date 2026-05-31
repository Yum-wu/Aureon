---
title: "LangChain 框架指南"
slug: "langchain-framework-guide"
language: "zh"
source: "langchain-framework-guide.md"
---

# LangChain 框架指南

## 什么是 LangChain

LangChain 是一个开源的 LLM 应用开发框架，用于构建基于大语言模型的复杂应用。它提供模块化组件和编排工具，让开发者能够快速搭建 RAG 系统、AI Agent、对话机器人等应用。

核心价值：将 LLM 调用、外部数据检索、工具调用、记忆管理等能力抽象为可组合的模块，降低开发复杂度。

## 核心概念

### 1. Models（模型）

LangChain 支持接入多种 LLM 提供商，统一接口调用：

```python
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatZhipuAI

# OpenAI
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 智谱 AI
llm = ChatZhipuAI(model="glm-4", temperature=0)

# 统一调用方式
response = llm.invoke("你好，请介绍 LangChain")
```

ChatModel 是 LangChain 的核心抽象，所有后续组件（Prompts、Chains、Agents）都基于统一的 `BaseChatModel` 接口。

### 2. Prompts（提示词）

PromptTemplate 和 ChatPromptTemplate 用于构建结构化提示词：

```python
from langchain_core.prompts import ChatPromptTemplate

# 简单模板
prompt = ChatPromptTemplate.from_template(
    "你是一个{role}。请用{language}回答以下问题：{question}"
)

# 带系统消息的模板
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是{role}，擅长{domain}领域。"),
    ("human", "{question}")
])

# 使用模板
messages = prompt.invoke({
    "role": "技术专家",
    "domain": "Python",
    "language": "中文",
    "question": "什么是 async/await？"
})
```

### 3. Chains（链）

Chain 是 LangChain 的核心编排机制，将多个组件串联为处理流水线：

```python
from langchain_core.output_parsers import StrOutputParser

# LCEL（LangChain Expression Language）链
chain = prompt | llm | StrOutputParser()

# 执行链
result = chain.invoke({
    "role": "Python 专家",
    "question": "解释装饰器的工作原理"
})
print(result)
```

LCEL 是 LangChain v0.2+ 推荐的链式编排语法，使用管道操作符 `|` 连接各组件，支持 streaming、async、并行执行。

### 4. Agents（智能体）

Agent 能根据用户输入动态决定调用哪些工具：

```python
from langchain.agents import create_tool_calling_agent
from langchain_core.tools import tool

@tool
def search_web(query: str) -> str:
    """搜索网页获取最新信息"""
    # 实际搜索逻辑
    return f"搜索结果：关于 {query} 的最新信息..."

@tool
def calculator(expression: str) -> str:
    """计算数学表达式"""
    return str(eval(expression))

# 创建 Agent
tools = [search_web, calculator]
agent = create_tool_calling_agent(llm, tools, prompt)

# 使用 AgentExecutor 运行
from langchain.agents import AgentExecutor
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
result = executor.invoke({"question": "北京今天天气如何？气温是多少度？"})
```

### 5. Memory（记忆）

Memory 组件管理对话历史，实现上下文感知的多轮对话：

```python
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain

# 缓冲记忆（保留所有对话历史）
memory = ConversationBufferMemory()

# 滑动窗口记忆（保留最近 N 轮）
from langchain.memory import ConversationBufferWindowMemory
memory = ConversationBufferWindowMemory(k=10)

# 摘要记忆（压缩历史为摘要）
from langchain.memory import ConversationSummaryMemory
memory = ConversationSummaryMemory(llm=llm)

# 构建对话链
chain = ConversationChain(llm=llm, memory=memory)
response = chain.invoke({"input": "我想了解机器学习"})
response = chain.invoke({"input": "刚才你说的主题，有哪些具体算法？"})
```

### 6. Retrieval（检索）

LangChain 的 Retrieval 模块支持构建 RAG 系统：

```python
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# 1. 加载文档并分割
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=200
)

# 2. 创建向量存储
vectorstore = Chroma.from_documents(
    documents=docs,
    embedding=OpenAIEmbeddings(model="text-embedding-3-small")
)

# 3. 构建 RAG 链
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

rag_prompt = ChatPromptTemplate.from_template("""
基于以下上下文回答问题。如果上下文中没有相关信息，请说明不知道。

上下文：{context}
问题：{question}
""")

rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | rag_prompt
    | llm
    | StrOutputParser()
)

answer = rag_chain.invoke("什么是 RAG？")
```

## LangChain vs LangGraph vs Deep Agents

### LangChain

- **定位**：基础构建框架
- **特点**：模块化组件、LCEL 链式编排、社区生态丰富
- **适用场景**：简单 RAG、单轮工具调用、标准 LLM 应用

### LangGraph

- **定位**：有状态 Agent 编排框架
- **特点**：基于有向图的状态机、支持循环和条件分支、内置持久化和人机协作
- **适用场景**：复杂 Agent 工作流、多步骤推理、需要人工审核的流程

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

# 定义状态图
graph = StateGraph(MessagesState)
graph.add_node("agent", call_model)
graph.add_node("tools", ToolNode(tools))
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END
})
graph.add_edge("tools", "agent")

app = graph.compile()
```

### Deep Agents

- **定位**：自主决策 Agent 框架
- **特点**：长任务执行、自我反思、动态规划
- **适用场景**：开放式任务、需要自主探索的场景

### 选型建议

| 场景 | 推荐框架 |
|------|----------|
| 简单 RAG 查询 | LangChain |
| 多轮工具调用 Agent | LangChain + Agent |
| 复杂工作流（条件分支、循环） | LangGraph |
| 需要持久化状态的长任务 | LangGraph |
| 完全自主的复杂任务 | Deep Agents |
| 生产环境多 Agent 协作 | LangGraph |

## create_agent API 详解

LangChain 提供了便捷的 Agent 创建 API：

```python
from langchain.agents import create_tool_calling_agent, create_react_agent

# 方式 1：Tool Calling Agent（推荐，需要模型支持 tool calling）
agent = create_tool_calling_agent(
    llm=llm,
    tools=tools,
    prompt=prompt_template
)

# 方式 2：ReAct Agent（兼容所有模型）
from langchain.agents import create_react_agent
agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=prompt_template
)
```

两者的区别：
- `create_tool_calling_agent`：依赖模型原生的 function calling 能力，性能更好，但需要模型支持
- `create_react_agent`：使用 ReAct prompt 模式，所有模型都兼容，但 token 消耗更高

## 最佳实践

1. **优先使用 LCEL**：用管道语法编排链，而非旧版 Chain 类
2. **流式输出**：生产环境始终开启 streaming，提升用户体验
3. **错误处理**：为每个 Tool 添加异常处理，避免 Agent 链路中断
4. **版本选择**：使用 LangChain v0.3+，旧版 API 已逐步废弃
5. **LangGraph 优先**：涉及状态管理的场景，优先选择 LangGraph 而非手动管理
