"""Integration Ecosystem - Enterprise Connectors & IM Bot"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class IntegrationConnector(BaseModel):
    """集成连接器"""
    id: Optional[int] = None
    name: str = Field(..., description="连接器名称")
    connector_type: str = Field(..., description="google_drive/sharepoint/notion/confluence/github")
    config: dict = Field(default_factory=dict, description="配置信息")
    sync_interval_minutes: int = Field(60, description="同步间隔（分钟）")
    enabled: bool = True
    last_sync_at: Optional[str] = None
    sync_status: str = "idle"  # idle/syncing/error
    error_message: Optional[str] = None
    created_at: Optional[str] = None


class IntegrationSyncLog(BaseModel):
    """集成同步日志"""
    id: Optional[int] = None
    connector_id: int
    sync_type: str = Field(..., description="full/incremental")
    status: str = Field(..., description="success/failed/partial")
    documents_synced: int = 0
    documents_failed: int = 0
    duration_ms: int = 0
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class IMBotConfig(BaseModel):
    """IM Bot 配置"""
    id: Optional[int] = None
    platform: str = Field(..., description="slack/teams/wechat/feishu/dingtalk")
    bot_token: Optional[str] = None
    webhook_url: Optional[str] = None
    workspace_id: str = Field(..., description="关联的 Workspace ID")
    enabled: bool = True
    created_at: Optional[str] = None


# ── Database Operations ──

def init_integration_tables():
    """初始化集成生态表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS integration_connectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            connector_type TEXT NOT NULL,
            config TEXT DEFAULT '{}',
            sync_interval_minutes INTEGER DEFAULT 60,
            enabled BOOLEAN DEFAULT 1,
            last_sync_at TIMESTAMP,
            sync_status TEXT DEFAULT 'idle',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS integration_sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connector_id INTEGER NOT NULL,
            sync_type TEXT NOT NULL,
            status TEXT NOT NULL,
            documents_synced INTEGER DEFAULT 0,
            documents_failed INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (connector_id) REFERENCES integration_connectors(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS im_bot_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            bot_token TEXT,
            webhook_url TEXT,
            workspace_id TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sync_logs_connector ON integration_sync_logs(connector_id)
    """)
    conn.commit()


# ── Integration Connector Operations ──

def create_connector(connector: IntegrationConnector) -> IntegrationConnector:
    """创建集成连接器"""
    import json
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.utcnow().isoformat()

    cursor = conn.execute(
        """
        INSERT INTO integration_connectors (name, connector_type, config, sync_interval_minutes, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            connector.name,
            connector.connector_type,
            json.dumps(connector.config),
            connector.sync_interval_minutes,
            connector.enabled,
            now,
        ),
    )
    conn.commit()

    return IntegrationConnector(
        id=cursor.lastrowid,
        name=connector.name,
        connector_type=connector.connector_type,
        config=connector.config,
        sync_interval_minutes=connector.sync_interval_minutes,
        enabled=connector.enabled,
        created_at=now,
    )


def list_connectors() -> list[IntegrationConnector]:
    """列出所有集成连接器"""
    import json
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute("SELECT * FROM integration_connectors ORDER BY created_at DESC").fetchall()

    return [
        IntegrationConnector(
            id=row["id"],
            name=row["name"],
            connector_type=row["connector_type"],
            config=json.loads(row["config"]),
            sync_interval_minutes=row["sync_interval_minutes"],
            enabled=bool(row["enabled"]),
            last_sync_at=row["last_sync_at"],
            sync_status=row["sync_status"],
            error_message=row["error_message"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_connector(name: str) -> Optional[IntegrationConnector]:
    """获取集成连接器"""
    import json
    from app.memory.db import get_db

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM integration_connectors WHERE name = ?",
        (name,),
    ).fetchone()

    if row is None:
        return None

    return IntegrationConnector(
        id=row["id"],
        name=row["name"],
        connector_type=row["connector_type"],
        config=json.loads(row["config"]),
        sync_interval_minutes=row["sync_interval_minutes"],
        enabled=bool(row["enabled"]),
        last_sync_at=row["last_sync_at"],
        sync_status=row["sync_status"],
        error_message=row["error_message"],
        created_at=row["created_at"],
    )


def delete_connector(name: str) -> bool:
    """删除集成连接器"""
    from app.memory.db import get_db

    conn = get_db()
    cursor = conn.execute("DELETE FROM integration_connectors WHERE name = ?", (name,))
    conn.commit()

    return cursor.rowcount > 0


def update_connector_status(name: str, status: str, error_message: str = None):
    """更新连接器状态"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.utcnow().isoformat()

    conn.execute(
        """
        UPDATE integration_connectors
        SET sync_status = ?, error_message = ?, last_sync_at = ?
        WHERE name = ?
        """,
        (status, error_message, now, name),
    )
    conn.commit()


# ── Sync Log Operations ──

def create_sync_log(log: IntegrationSyncLog) -> int:
    """创建同步日志"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.utcnow().isoformat()

    cursor = conn.execute(
        """
        INSERT INTO integration_sync_logs (connector_id, sync_type, status, documents_synced, documents_failed, duration_ms, error_message, started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log.connector_id,
            log.sync_type,
            log.status,
            log.documents_synced,
            log.documents_failed,
            log.duration_ms,
            log.error_message,
            now,
        ),
    )
    conn.commit()

    return cursor.lastrowid


def complete_sync_log(log_id: int, status: str, documents_synced: int = 0, documents_failed: int = 0):
    """完成同步日志"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.utcnow().isoformat()

    conn.execute(
        """
        UPDATE integration_sync_logs
        SET status = ?, documents_synced = ?, documents_failed = ?, completed_at = ?
        WHERE id = ?
        """,
        (status, documents_synced, documents_failed, now, log_id),
    )
    conn.commit()


def get_sync_logs(connector_id: int = None, limit: int = 10) -> list[IntegrationSyncLog]:
    """获取同步日志"""
    from app.memory.db import get_db

    conn = get_db()
    if connector_id:
        rows = conn.execute(
            """
            SELECT * FROM integration_sync_logs
            WHERE connector_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (connector_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM integration_sync_logs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [
        IntegrationSyncLog(
            id=row["id"],
            connector_id=row["connector_id"],
            sync_type=row["sync_type"],
            status=row["status"],
            documents_synced=row["documents_synced"],
            documents_failed=row["documents_failed"],
            duration_ms=row["duration_ms"],
            error_message=row["error_message"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
        for row in rows
    ]


# ── IM Bot Operations ──

def create_im_bot(bot: IMBotConfig) -> IMBotConfig:
    """创建 IM Bot 配置"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.utcnow().isoformat()

    cursor = conn.execute(
        """
        INSERT INTO im_bot_configs (platform, bot_token, webhook_url, workspace_id, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            bot.platform,
            bot.bot_token,
            bot.webhook_url,
            bot.workspace_id,
            bot.enabled,
            now,
        ),
    )
    conn.commit()

    return IMBotConfig(
        id=cursor.lastrowid,
        platform=bot.platform,
        bot_token=bot.bot_token,
        webhook_url=bot.webhook_url,
        workspace_id=bot.workspace_id,
        enabled=bot.enabled,
        created_at=now,
    )


def list_im_bots(workspace_id: str = None) -> list[IMBotConfig]:
    """列出 IM Bot 配置"""
    from app.memory.db import get_db

    conn = get_db()
    if workspace_id:
        rows = conn.execute(
            "SELECT * FROM im_bot_configs WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM im_bot_configs").fetchall()

    return [
        IMBotConfig(
            id=row["id"],
            platform=row["platform"],
            bot_token=row["bot_token"],
            webhook_url=row["webhook_url"],
            workspace_id=row["workspace_id"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def delete_im_bot(platform: str, workspace_id: str) -> bool:
    """删除 IM Bot 配置"""
    from app.memory.db import get_db

    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM im_bot_configs WHERE platform = ? AND workspace_id = ?",
        (platform, workspace_id),
    )
    conn.commit()

    return cursor.rowcount > 0
