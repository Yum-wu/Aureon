"""Reliability & Resilience - Backup, Failover, SLO, Circuit Breaker

Provides backup management, incident tracking, SLO monitoring, and circuit breaker pattern.
"""
import warnings
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import structlog

# Import circuit breaker from dedicated module
from .circuit_breaker import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerError,
    circuit_breaker,
    get_circuit_breaker,
    get_all_circuit_breakers,
    reset_all_circuit_breakers,
    create_llm_circuit_breaker,
    llm_circuit_breaker,
    embedding_circuit_breaker,
    reranker_circuit_breaker,
    wrap_llm_call,
)

# Phase 3: Bulkhead 隔舱模式
from .bulkhead import (
    Bulkhead,
    BulkheadFullError,
    bulkhead,
    get_bulkhead,
    get_all_bulkhead_stats,
    reset_all_bulkheads,
    redis_bulkhead,
    qdrant_bulkhead,
    llm_bulkhead,
    embedding_bulkhead,
)

# Phase 3: 超时级联
# 注意：TimeoutError 与内置冲突，以 LayerTimeoutError 别名导出
from .timeouts import (
    TIMEOUT_HIERARCHY,
    with_timeout,
    call_with_timeout,
)
from .timeouts import TimeoutError as LayerTimeoutError

# Phase 4: Chaos Engineering
from .chaos import (
    ChaosConfig,
    chaos,
    enable_chaos,
    disable_chaos,
    is_chaos_enabled,
    register_chaos_rule,
)

logger = structlog.get_logger()


class BackupRecord(BaseModel):
    """备份记录"""
    id: Optional[int] = None
    backup_type: str = Field(..., description="full/incremental")
    component: str = Field(..., description="vector_db/metadata_db/analytics_db")
    file_path: Optional[str] = None
    file_size_bytes: int = 0
    checksum: Optional[str] = None
    status: str = "pending"  # pending/completed/failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class IncidentRecord(BaseModel):
    """事件记录"""
    id: Optional[int] = None
    incident_id: str = Field(..., description="事件 ID")
    severity: str = Field(..., description="critical/warning/info")
    component: str = Field(..., description="组件名称")
    title: str = Field(..., description="事件标题")
    description: Optional[str] = None
    status: str = "open"  # open/investigating/resolved
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    started_at: Optional[str] = None
    resolved_at: Optional[str] = None


class SLOConfig(BaseModel):
    """SLO 配置"""
    id: Optional[int] = None
    metric_name: str = Field(..., description="指标名称")
    target_value: float = Field(..., description="目标值")
    window_days: int = Field(30, description="滚动窗口天数")
    enabled: bool = True
    created_at: Optional[str] = None


class SLOStatus(BaseModel):
    """SLO 状态"""
    metric_name: str
    target_value: float
    current_value: float
    is_met: bool
    error_budget_remaining: float  # 剩余错误预算百分比


# ── Circuit Breaker ──
# 使用 circuit_breaker 模块中的实现
# 保留旧的 CircuitBreaker 类用于向后兼容

class LegacyCircuitBreaker:
    """旧版熔断器（已弃用）
    
    请使用 circuit_breaker 模块中的新实现。
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        warnings.warn(
            "LegacyCircuitBreaker 已弃用，请使用 circuit_breaker.CircuitBreaker",
            DeprecationWarning,
            stacklevel=2,
        )
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed/open/half-open

    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                "circuit_breaker_opened",
                failure_count=self.failure_count,
            )

    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.state = "closed"

    def can_execute(self) -> bool:
        """是否可以执行"""
        if self.state == "closed":
            return True

        if self.state == "open":
            if self.last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self.last_failure_time).seconds
                if elapsed >= self.recovery_timeout:
                    self.state = "half-open"
                    return True
            return False

        # half-open 状态允许一次尝试
        return True


# ── Database Operations ──

def init_reliability_tables():
    """初始化可靠性管理表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backup_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_type TEXT NOT NULL,
            component TEXT NOT NULL,
            file_path TEXT,
            file_size_bytes INTEGER DEFAULT 0,
            checksum TEXT,
            status TEXT DEFAULT 'pending',
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS incident_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT UNIQUE NOT NULL,
            severity TEXT NOT NULL,
            component TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            root_cause TEXT,
            resolution TEXT,
            started_at TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slo_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT UNIQUE NOT NULL,
            target_value REAL NOT NULL,
            window_days INTEGER DEFAULT 30,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_incident_records_status ON incident_records(status)
    """)
    conn.commit()


def create_backup_record(record: BackupRecord) -> int:
    """创建备份记录"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO backup_records (backup_type, component, file_path, file_size_bytes, checksum, status, started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.backup_type,
            record.component,
            record.file_path,
            record.file_size_bytes,
            record.checksum,
            "pending",
            now,
        ),
    )
    conn.commit()

    return cursor.lastrowid


def complete_backup(record_id: int, status: str = "completed", file_path: str = None):
    """完成备份"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        UPDATE backup_records
        SET status = ?, file_path = ?, completed_at = ?
        WHERE id = ?
        """,
        (status, file_path, now, record_id),
    )
    conn.commit()


def get_recent_backups(limit: int = 10) -> list[BackupRecord]:
    """获取最近的备份记录"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM backup_records ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    return [
        BackupRecord(
            id=row["id"],
            backup_type=row["backup_type"],
            component=row["component"],
            file_path=row["file_path"],
            file_size_bytes=row["file_size_bytes"],
            checksum=row["checksum"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
        for row in rows
    ]


def create_incident(record: IncidentRecord) -> int:
    """创建事件记录"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO incident_records (incident_id, severity, component, title, description, status, started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.incident_id,
            record.severity,
            record.component,
            record.title,
            record.description,
            "open",
            now,
        ),
    )
    conn.commit()

    return cursor.lastrowid


def resolve_incident(incident_id: str, resolution: str):
    """解决事件"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        UPDATE incident_records
        SET status = 'resolved', resolution = ?, resolved_at = ?
        WHERE incident_id = ?
        """,
        (resolution, now, incident_id),
    )
    conn.commit()


def get_open_incidents() -> list[IncidentRecord]:
    """获取未解决的事件"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM incident_records WHERE status != 'resolved' ORDER BY started_at DESC"
    ).fetchall()

    return [
        IncidentRecord(
            id=row["id"],
            incident_id=row["incident_id"],
            severity=row["severity"],
            component=row["component"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            root_cause=row["root_cause"],
            resolution=row["resolution"],
            started_at=row["started_at"],
            resolved_at=row["resolved_at"],
        )
        for row in rows
    ]


def create_slo_config(config: SLOConfig) -> SLOConfig:
    """创建 SLO 配置"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO slo_configs (metric_name, target_value, window_days, enabled, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (config.metric_name, config.target_value, config.window_days, config.enabled, now),
    )
    conn.commit()

    return SLOConfig(
        id=cursor.lastrowid,
        metric_name=config.metric_name,
        target_value=config.target_value,
        window_days=config.window_days,
        enabled=config.enabled,
        created_at=now,
    )


def get_slo_configs() -> list[SLOConfig]:
    """获取所有 SLO 配置"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute("SELECT * FROM slo_configs WHERE enabled = 1").fetchall()

    return [
        SLOConfig(
            id=row["id"],
            metric_name=row["metric_name"],
            target_value=row["target_value"],
            window_days=row["window_days"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_slo_status() -> list[SLOStatus]:
    """获取 SLO 状态"""
    from app.memory.db import get_db

    configs = get_slo_configs()
    statuses = []

    conn = get_db()
    for config in configs:
        # 根据指标名称获取当前值
        current_value = 0.0
        if config.metric_name == "availability":
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as value
                FROM query_traces
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                """,
                (config.window_days,),
            ).fetchone()
            current_value = row["value"] or 100.0
        elif config.metric_name == "error_rate":
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as value
                FROM query_traces
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                """,
                (config.window_days,),
            ).fetchone()
            current_value = row["value"] or 0.0
        elif config.metric_name == "p95_latency":
            row = conn.execute(
                """
                SELECT total_latency_ms as value FROM query_traces
                WHERE status = 'completed'
                ORDER BY total_latency_ms
                LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * 0.95 AS INTEGER) FROM query_traces WHERE status = 'completed')
                """
            ).fetchone()
            current_value = row["value"] if row else 0.0

        is_met = current_value >= config.target_value if config.metric_name != "error_rate" else current_value <= config.target_value
        error_budget = max(0, 100 - (current_value / config.target_value * 100)) if config.target_value > 0 else 100

        statuses.append(SLOStatus(
            metric_name=config.metric_name,
            target_value=config.target_value,
            current_value=round(current_value, 2),
            is_met=is_met,
            error_budget_remaining=round(max(0, error_budget), 2),
        ))

    return statuses


# ── 导出 ──
__all__ = [
    # 数据模型
    "BackupRecord",
    "IncidentRecord",
    "SLOConfig",
    "SLOStatus",

    # 断路器
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerError",
    "LegacyCircuitBreaker",
    "circuit_breaker",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "reset_all_circuit_breakers",
    "create_llm_circuit_breaker",
    "llm_circuit_breaker",
    "embedding_circuit_breaker",
    "reranker_circuit_breaker",
    "wrap_llm_call",

    # Phase 3: Bulkhead 隔舱模式
    "Bulkhead",
    "BulkheadFullError",
    "bulkhead",
    "get_bulkhead",
    "get_all_bulkhead_stats",
    "reset_all_bulkheads",
    "redis_bulkhead",
    "qdrant_bulkhead",
    "llm_bulkhead",
    "embedding_bulkhead",

    # Phase 3: 超时级联
    "TIMEOUT_HIERARCHY",
    "with_timeout",
    "call_with_timeout",
    "LayerTimeoutError",

    # Phase 4: Chaos Engineering
    "ChaosConfig",
    "chaos",
    "enable_chaos",
    "disable_chaos",
    "is_chaos_enabled",
    "register_chaos_rule",

    # 数据库操作
    "init_reliability_tables",
    "create_backup_record",
    "complete_backup",
    "get_recent_backups",
    "create_incident",
    "resolve_incident",
    "get_open_incidents",
    "create_slo_config",
    "get_slo_configs",
    "get_slo_status",
]
