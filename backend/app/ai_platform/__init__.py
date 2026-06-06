"""AI Platform Layer - Multi-LLM Router & Confidence Scoring

EXPERIMENTAL: Not connected to core paths. Models/Routes exist but unused by production flow.
"""
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import structlog

from app.common import mask_secret

logger = structlog.get_logger()


class LLMProvider(BaseModel):
    """LLM 提供商配置"""
    id: Optional[int] = None
    name: str = Field(..., description="提供商名称")
    provider_type: str = Field(..., description="openai/anthropic/google/local/zhipu")
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: str = Field(..., description="模型名称")
    enabled: bool = True
    priority: int = Field(0, description="优先级（越小越高）")
    max_tokens: int = 4096
    temperature: float = 0.7
    created_at: Optional[str] = None


class LLMRouteConfig(BaseModel):
    """LLM 路由配置"""
    id: Optional[int] = None
    workspace_id: str = Field(..., description="Workspace ID")
    strategy: str = Field("quality_first", description="cost_first/quality_first/latency_first")
    fallback_enabled: bool = True
    created_at: Optional[str] = None


class ConfidenceScore(BaseModel):
    """置信度分数"""
    id: Optional[int] = None
    query_id: str = Field(..., description="查询 ID")
    query: str = Field(..., description="查询内容")
    confidence_score: float = Field(..., description="置信度分数 (0-1)")
    citation_coverage: float = Field(0.0, description="引用覆盖率")
    retrieved_chunks: int = 0
    cited_chunks: int = 0
    low_confidence: bool = False
    fallback_action: Optional[str] = None
    created_at: Optional[str] = None


class ConversationSession(BaseModel):
    """对话会话"""
    id: Optional[int] = None
    session_id: str = Field(..., description="会话 ID")
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None
    message_count: int = 0
    total_tokens: int = 0
    status: str = "active"  # active/completed/archived
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConversationMessage(BaseModel):
    """对话消息"""
    id: Optional[int] = None
    session_id: str = Field(..., description="会话 ID")
    role: str = Field(..., description="user/assistant/system")
    content: str = Field(..., description="消息内容")
    tokens: int = 0
    model_used: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: Optional[str] = None


# ── Confidence Thresholds ──

CONFIDENCE_THRESHOLDS = {
    "high": 0.8,      # 高置信度：直接返回答案
    "medium": 0.5,    # 中置信度：标注"建议人工确认"
    "low": 0.3,       # 低置信度：拒绝回答，引导用户
}


# ── Database Operations ──

def init_ai_platform_tables():
    """初始化 AI 平台表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            provider_type TEXT NOT NULL,
            api_key TEXT,
            base_url TEXT,
            model_name TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            priority INTEGER DEFAULT 0,
            max_tokens INTEGER DEFAULT 4096,
            temperature REAL DEFAULT 0.7,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_route_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT UNIQUE NOT NULL,
            strategy TEXT DEFAULT 'quality_first',
            fallback_enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS confidence_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id TEXT UNIQUE NOT NULL,
            query TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            citation_coverage REAL DEFAULT 0,
            retrieved_chunks INTEGER DEFAULT 0,
            cited_chunks INTEGER DEFAULT 0,
            low_confidence BOOLEAN DEFAULT 0,
            fallback_action TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            user_id TEXT,
            workspace_id TEXT,
            message_count INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            tokens INTEGER DEFAULT 0,
            model_used TEXT,
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_confidence_scores_query ON confidence_scores(query_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_session ON conversation_messages(session_id)
    """)
    conn.commit()


# ── LLM Provider Operations ──

def create_llm_provider(provider: LLMProvider) -> LLMProvider:
    """创建 LLM 提供商"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO llm_providers (name, provider_type, api_key, base_url, model_name, enabled, priority, max_tokens, temperature, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provider.name,
            provider.provider_type,
            provider.api_key,
            provider.base_url,
            provider.model_name,
            provider.enabled,
            provider.priority,
            provider.max_tokens,
            provider.temperature,
            now,
        ),
    )
    conn.commit()

    return LLMProvider(
        id=cursor.lastrowid,
        name=provider.name,
        provider_type=provider.provider_type,
        api_key=provider.api_key,
        base_url=provider.base_url,
        model_name=provider.model_name,
        enabled=provider.enabled,
        priority=provider.priority,
        max_tokens=provider.max_tokens,
        temperature=provider.temperature,
        created_at=now,
    )


def list_llm_providers() -> list[LLMProvider]:
    """列出所有 LLM 提供商"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM llm_providers WHERE enabled = 1 ORDER BY priority ASC"
    ).fetchall()

    return [
        LLMProvider(
            id=row["id"],
            name=row["name"],
            provider_type=row["provider_type"],
            api_key=mask_secret(row["api_key"]),
            base_url=row["base_url"],
            model_name=row["model_name"],
            enabled=bool(row["enabled"]),
            priority=row["priority"],
            max_tokens=row["max_tokens"],
            temperature=row["temperature"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_llm_provider(name: str) -> Optional[LLMProvider]:
    """获取单个 LLM 提供商（api_key 脱敏）"""
    from app.memory.db import get_db

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM llm_providers WHERE name = ?",
        (name,),
    ).fetchone()

    if row is None:
        return None

    return LLMProvider(
        id=row["id"],
        name=row["name"],
        provider_type=row["provider_type"],
        api_key=mask_secret(row["api_key"]),
        base_url=row["base_url"],
        model_name=row["model_name"],
        enabled=bool(row["enabled"]),
        priority=row["priority"],
        max_tokens=row["max_tokens"],
        temperature=row["temperature"],
        created_at=row["created_at"],
    )


def delete_llm_provider(name: str) -> bool:
    """删除 LLM 提供商"""
    from app.memory.db import get_db

    conn = get_db()
    cursor = conn.execute("DELETE FROM llm_providers WHERE name = ?", (name,))
    conn.commit()

    return cursor.rowcount > 0


# ── Confidence Scoring Operations ──

def calculate_confidence(
    retrieved_chunks: list[dict],
    cited_chunks: list[dict],
    query: str,
) -> ConfidenceScore:
    """计算置信度分数"""
    retrieved_count = len(retrieved_chunks)
    cited_count = len(cited_chunks)

    # 引用覆盖率
    citation_coverage = cited_count / retrieved_count if retrieved_count > 0 else 0

    # 置信度分数（基于引用覆盖率和检索数量）
    confidence_score = citation_coverage * 0.7 + min(retrieved_count / 10, 0.3)

    # 判断是否低置信度
    low_confidence = confidence_score < CONFIDENCE_THRESHOLDS["medium"]
    fallback_action = None
    if confidence_score < CONFIDENCE_THRESHOLDS["low"]:
        fallback_action = "reject"
    elif confidence_score < CONFIDENCE_THRESHOLDS["medium"]:
        fallback_action = "warn"

    return ConfidenceScore(
        query_id="",
        query=query,
        confidence_score=round(confidence_score, 4),
        citation_coverage=round(citation_coverage, 4),
        retrieved_chunks=retrieved_count,
        cited_chunks=cited_count,
        low_confidence=low_confidence,
        fallback_action=fallback_action,
    )


def save_confidence_score(score: ConfidenceScore) -> int:
    """保存置信度分数"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO confidence_scores (query_id, query, confidence_score, citation_coverage, retrieved_chunks, cited_chunks, low_confidence, fallback_action, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            score.query_id,
            score.query,
            score.confidence_score,
            score.citation_coverage,
            score.retrieved_chunks,
            score.cited_chunks,
            score.low_confidence,
            score.fallback_action,
            now,
        ),
    )
    conn.commit()

    return cursor.lastrowid


# ── Conversation Session Operations ──

def create_conversation_session(session: ConversationSession) -> ConversationSession:
    """创建对话会话"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO conversation_sessions (session_id, user_id, workspace_id, message_count, total_tokens, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session.session_id,
            session.user_id,
            session.workspace_id,
            session.message_count,
            session.total_tokens,
            "active",
            now,
            now,
        ),
    )
    conn.commit()

    return ConversationSession(
        id=cursor.lastrowid,
        session_id=session.session_id,
        user_id=session.user_id,
        workspace_id=session.workspace_id,
        message_count=session.message_count,
        total_tokens=session.total_tokens,
        status="active",
        created_at=now,
        updated_at=now,
    )


def add_conversation_message(message: ConversationMessage) -> int:
    """添加对话消息"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO conversation_messages (session_id, role, content, tokens, model_used, confidence_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message.session_id,
            message.role,
            message.content,
            message.tokens,
            message.model_used,
            message.confidence_score,
            now,
        ),
    )

    # 更新会话消息计数
    conn.execute(
        """
        UPDATE conversation_sessions
        SET message_count = message_count + 1, total_tokens = total_tokens + ?, updated_at = ?
        WHERE session_id = ?
        """,
        (message.tokens, now, message.session_id),
    )
    conn.commit()

    return cursor.lastrowid


def get_conversation_history(session_id: str, limit: int = 50) -> list[ConversationMessage]:
    """获取对话历史"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM conversation_messages
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()

    return [
        ConversationMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            tokens=row["tokens"],
            model_used=row["model_used"],
            confidence_score=row["confidence_score"],
            created_at=row["created_at"],
        )
        for row in reversed(rows)  # 按时间正序返回
    ]


def get_session_context(session_id: str, max_tokens: int = 4000) -> list[dict]:
    """获取会话上下文（用于 LLM 调用）"""
    messages = get_conversation_history(session_id)

    # 计算 token 并截断
    context = []
    total_tokens = 0
    for msg in reversed(messages):
        msg_tokens = msg.tokens or len(msg.content) // 4  # 估算
        if total_tokens + msg_tokens > max_tokens:
            break
        context.insert(0, {"role": msg.role, "content": msg.content})
        total_tokens += msg_tokens

    return context
