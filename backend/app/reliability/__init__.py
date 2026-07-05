"""Reliability & Resilience - Backup, Failover, SLO, Circuit Breaker

Provides backup management, incident tracking, SLO monitoring, and circuit breaker pattern.
PostgreSQL asyncpg backend.
"""
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
    wrap_llm_call,
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


# ── asyncpg 助手 ──


async def _get_pool():
    from app.database.connection import get_db_pool
    pool = get_db_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL not configured")
    return pool


# ── 表结构 (schema.sql 也会创建，此函数作为 lifespan 中的安全兜底) ──


async def init_reliability_tables():
    """初始化可靠性管理表"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS backup_records (
                id BIGSERIAL PRIMARY KEY,
                backup_type TEXT NOT NULL,
                component TEXT NOT NULL,
                file_path TEXT,
                file_size_bytes INTEGER DEFAULT 0,
                checksum TEXT,
                status TEXT DEFAULT 'pending',
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS incident_records (
                id BIGSERIAL PRIMARY KEY,
                incident_id TEXT UNIQUE NOT NULL,
                severity TEXT NOT NULL,
                component TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'open',
                root_cause TEXT,
                resolution TEXT,
                started_at TIMESTAMPTZ,
                resolved_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS slo_configs (
                id BIGSERIAL PRIMARY KEY,
                metric_name TEXT UNIQUE NOT NULL,
                target_value REAL NOT NULL,
                window_days INTEGER DEFAULT 30,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    logger.info("reliability_tables_initialized")


def _fmt_ts(val) -> Optional[str]:
    if val is None:
        return None
    return val.isoformat() if hasattr(val, "isoformat") else str(val)


# ── Backup Operations ──


async def create_backup_record(record: BackupRecord) -> int:
    """创建备份记录"""
    pool = await _get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO backup_records (backup_type, component, file_path, file_size_bytes, checksum, status, started_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            record.backup_type, record.component, record.file_path,
            record.file_size_bytes, record.checksum, "pending", now,
        )
    return row["id"]


async def complete_backup(record_id: int, status: str = "completed", file_path: str = None):
    """完成备份"""
    pool = await _get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE backup_records SET status = $1, file_path = $2, completed_at = $3 WHERE id = $4",
            status, file_path, now, record_id,
        )


async def get_recent_backups(limit: int = 10) -> list[BackupRecord]:
    """获取最近的备份记录"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM backup_records ORDER BY started_at DESC LIMIT $1", limit
        )

    return [
        BackupRecord(
            id=r["id"],
            backup_type=r["backup_type"],
            component=r["component"],
            file_path=r["file_path"],
            file_size_bytes=r["file_size_bytes"],
            checksum=r["checksum"],
            status=r["status"],
            started_at=_fmt_ts(r["started_at"]),
            completed_at=_fmt_ts(r["completed_at"]),
        )
        for r in rows
    ]


# ── Incident Operations ──


async def create_incident(record: IncidentRecord) -> int:
    """创建事件记录"""
    pool = await _get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO incident_records (incident_id, severity, component, title, description, status, started_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            record.incident_id, record.severity, record.component,
            record.title, record.description, "open", now,
        )
    return row["id"]


async def resolve_incident(incident_id: str, resolution: str):
    """解决事件"""
    pool = await _get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE incident_records SET status = 'resolved', resolution = $1, resolved_at = $2
               WHERE incident_id = $3""",
            resolution, now, incident_id,
        )


async def get_open_incidents() -> list[IncidentRecord]:
    """获取未解决的事件"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM incident_records WHERE status != 'resolved' ORDER BY started_at DESC"
        )

    return [
        IncidentRecord(
            id=r["id"],
            incident_id=r["incident_id"],
            severity=r["severity"],
            component=r["component"],
            title=r["title"],
            description=r["description"],
            status=r["status"],
            root_cause=r.get("root_cause"),
            resolution=r.get("resolution"),
            started_at=_fmt_ts(r["started_at"]),
            resolved_at=_fmt_ts(r["resolved_at"]),
        )
        for r in rows
    ]


# ── SLO Operations ──


async def create_slo_config(config: SLOConfig) -> SLOConfig:
    """创建 SLO 配置"""
    pool = await _get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO slo_configs (metric_name, target_value, window_days, enabled, created_at)
               VALUES ($1, $2, $3, $4, $5) RETURNING id, metric_name, target_value, window_days, enabled, created_at""",
            config.metric_name, config.target_value, config.window_days, config.enabled, now,
        )

    return SLOConfig(
        id=row["id"],
        metric_name=row["metric_name"],
        target_value=row["target_value"],
        window_days=row["window_days"],
        enabled=bool(row["enabled"]),
        created_at=_fmt_ts(row["created_at"]),
    )


async def get_slo_configs() -> list[SLOConfig]:
    """获取所有 SLO 配置"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM slo_configs WHERE enabled = TRUE")

    return [
        SLOConfig(
            id=r["id"],
            metric_name=r["metric_name"],
            target_value=r["target_value"],
            window_days=r["window_days"],
            enabled=bool(r["enabled"]),
            created_at=_fmt_ts(r["created_at"]),
        )
        for r in rows
    ]


async def get_slo_status() -> list[SLOStatus]:
    """获取 SLO 状态"""
    pool = await _get_pool()
    configs = await get_slo_configs()
    statuses = []

    async with pool.acquire() as conn:
        for config in configs:
            current_value = 0.0

            if config.metric_name == "availability":
                row = await conn.fetchrow(
                    """SELECT COALESCE(
                           SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0),
                           100.0
                       ) as value
                    FROM query_traces
                    WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL""",
                    str(config.window_days),
                )
                current_value = row["value"] or 100.0 if row else 100.0

            elif config.metric_name == "error_rate":
                row = await conn.fetchrow(
                    """SELECT COALESCE(
                           SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0),
                           0.0
                       ) as value
                    FROM query_traces
                    WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL""",
                    str(config.window_days),
                )
                current_value = row["value"] or 0.0 if row else 0.0

            elif config.metric_name == "p95_latency":
                row = await conn.fetchval(
                    """SELECT total_latency_ms FROM query_traces
                       WHERE status = 'completed'
                       ORDER BY total_latency_ms
                       LIMIT 1 OFFSET (SELECT GREATEST(0, CAST(COUNT(*) * 0.95 AS INTEGER) - 1)
                                        FROM query_traces WHERE status = 'completed')"""
                )
                current_value = row or 0.0

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
    "circuit_breaker",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "reset_all_circuit_breakers",
    "create_llm_circuit_breaker",
    "wrap_llm_call",

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
