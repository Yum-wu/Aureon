"""Cost Governance - 成本追踪和 Budget 管理"""
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class CostRecord(BaseModel):
    """成本记录"""
    id: Optional[int] = None
    workspace_id: str = Field(..., description="Workspace ID")
    user_id: Optional[str] = None
    query_id: Optional[str] = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    model_used: Optional[str] = None
    cached: bool = False
    created_at: Optional[str] = None


class BudgetConfig(BaseModel):
    """Budget 配置"""
    id: Optional[int] = None
    workspace_id: str = Field(..., description="Workspace ID")
    monthly_limit_usd: float = Field(..., description="月度限额 (USD)")
    warning_threshold: float = Field(0.8, description="告警阈值 (0-1)")
    enforcement: str = Field("warn", description="enforcement 策略: warn/throttle/readonly/pause")
    reset_day: int = Field(1, description="每月重置日")
    enabled: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CostAlert(BaseModel):
    """成本告警"""
    id: Optional[int] = None
    workspace_id: str
    alert_type: str  # warning/critical/exceeded
    message: str
    current_usage: float
    limit: float
    percentage: float
    acknowledged: bool = False
    created_at: Optional[str] = None


# ── Token 定价 (每 1K tokens) ──
TOKEN_PRICING = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "deepseek-v4-flash": {"input": 0.0001, "output": 0.0002},
    "glm-4-flash": {"input": 0.0001, "output": 0.0001},
    "default": {"input": 0.0001, "output": 0.0002},
}


def calculate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    """计算成本"""
    pricing = TOKEN_PRICING.get(model, TOKEN_PRICING["default"])
    cost = (tokens_input / 1000 * pricing["input"]) + (tokens_output / 1000 * pricing["output"])
    return round(cost, 6)


def init_cost_tables():
    """初始化成本管理表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cost_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            user_id TEXT,
            query_id TEXT,
            tokens_input INTEGER DEFAULT 0,
            tokens_output INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            model_used TEXT,
            cached BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS budget_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT UNIQUE NOT NULL,
            monthly_limit_usd REAL NOT NULL,
            warning_threshold REAL DEFAULT 0.8,
            enforcement TEXT DEFAULT 'warn',
            reset_day INTEGER DEFAULT 1,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cost_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT,
            current_usage REAL DEFAULT 0,
            "limit" REAL DEFAULT 0,
            percentage REAL DEFAULT 0,
            acknowledged BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cost_records_workspace ON cost_records(workspace_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cost_records_created ON cost_records(created_at)
    """)
    conn.commit()


def record_cost(record: CostRecord) -> int:
    """记录成本"""
    from app.memory.db import get_db

    conn = get_db()
    cost = calculate_cost(record.model_used or "default", record.tokens_input, record.tokens_output)

    cursor = conn.execute(
        """
        INSERT INTO cost_records (workspace_id, user_id, query_id, tokens_input, tokens_output, cost_usd, model_used, cached)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.workspace_id,
            record.user_id,
            record.query_id,
            record.tokens_input,
            record.tokens_output,
            cost,
            record.model_used,
            record.cached,
        ),
    )
    conn.commit()

    # 检查 Budget
    check_budget_alerts(record.workspace_id)

    return cursor.lastrowid


def get_workspace_cost(workspace_id: str, days: int = 30) -> dict:
    """获取 Workspace 成本统计"""
    from app.memory.db import get_db

    conn = get_db()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    row = conn.execute(
        """
        SELECT
            COUNT(*) as total_queries,
            SUM(tokens_input) as total_tokens_input,
            SUM(tokens_output) as total_tokens_output,
            SUM(cost_usd) as total_cost_usd,
            SUM(CASE WHEN cached = 1 THEN cost_usd ELSE 0 END) as cache_savings
        FROM cost_records
        WHERE workspace_id = ? AND created_at >= ?
        """,
        (workspace_id, since),
    ).fetchone()

    return {
        "workspace_id": workspace_id,
        "period_days": days,
        "total_queries": row["total_queries"] or 0,
        "total_tokens_input": row["total_tokens_input"] or 0,
        "total_tokens_output": row["total_tokens_output"] or 0,
        "total_cost_usd": round(row["total_cost_usd"] or 0, 4),
        "cache_savings_usd": round(row["cache_savings"] or 0, 4),
        "avg_cost_per_query": round(
            (row["total_cost_usd"] or 0) / (row["total_queries"] or 1), 6
        ),
    }


def get_user_cost(user_id: str, days: int = 30) -> dict:
    """获取用户成本统计"""
    from app.memory.db import get_db

    conn = get_db()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    row = conn.execute(
        """
        SELECT
            COUNT(*) as total_queries,
            SUM(cost_usd) as total_cost_usd
        FROM cost_records
        WHERE user_id = ? AND created_at >= ?
        """,
        (user_id, since),
    ).fetchone()

    return {
        "user_id": user_id,
        "period_days": days,
        "total_queries": row["total_queries"] or 0,
        "total_cost_usd": round(row["total_cost_usd"] or 0, 4),
    }


def get_top_users(workspace_id: str, limit: int = 10, days: int = 30) -> list[dict]:
    """获取高消费用户排行"""
    from app.memory.db import get_db

    conn = get_db()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    rows = conn.execute(
        """
        SELECT user_id, SUM(cost_usd) as total_cost, COUNT(*) as query_count
        FROM cost_records
        WHERE workspace_id = ? AND user_id IS NOT NULL AND created_at >= ?
        GROUP BY user_id
        ORDER BY total_cost DESC
        LIMIT ?
        """,
        (workspace_id, since, limit),
    ).fetchall()

    return [
        {
            "user_id": row["user_id"],
            "total_cost_usd": round(row["total_cost"], 4),
            "query_count": row["query_count"],
        }
        for row in rows
    ]


# ── Budget Management ──

def create_budget(budget: BudgetConfig) -> BudgetConfig:
    """创建 Budget 配置"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.utcnow().isoformat()

    cursor = conn.execute(
        """
        INSERT INTO budget_configs (workspace_id, monthly_limit_usd, warning_threshold, enforcement, reset_day, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            budget.workspace_id,
            budget.monthly_limit_usd,
            budget.warning_threshold,
            budget.enforcement,
            budget.reset_day,
            budget.enabled,
            now,
            now,
        ),
    )
    conn.commit()

    return BudgetConfig(
        id=cursor.lastrowid,
        workspace_id=budget.workspace_id,
        monthly_limit_usd=budget.monthly_limit_usd,
        warning_threshold=budget.warning_threshold,
        enforcement=budget.enforcement,
        reset_day=budget.reset_day,
        enabled=budget.enabled,
        created_at=now,
        updated_at=now,
    )


def get_budget(workspace_id: str) -> Optional[BudgetConfig]:
    """获取 Budget 配置"""
    from app.memory.db import get_db

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM budget_configs WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()

    if row is None:
        return None

    return BudgetConfig(
        id=row["id"],
        workspace_id=row["workspace_id"],
        monthly_limit_usd=row["monthly_limit_usd"],
        warning_threshold=row["warning_threshold"],
        enforcement=row["enforcement"],
        reset_day=row["reset_day"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def update_budget(workspace_id: str, update: dict) -> Optional[BudgetConfig]:
    """更新 Budget 配置"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.utcnow().isoformat()

    updates = []
    params = []

    # 允许更新的字段
    allowed_fields = ["monthly_limit_usd", "warning_threshold", "enforcement", "reset_day", "enabled"]

    for key, value in update.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            params.append(value)

    if not updates:
        return get_budget(workspace_id)

    updates.append("updated_at = ?")
    params.append(now)
    params.append(workspace_id)

    conn.execute(
        f"UPDATE budget_configs SET {', '.join(updates)} WHERE workspace_id = ?",
        params,
    )
    conn.commit()

    return get_budget(workspace_id)


def check_budget_alerts(workspace_id: str) -> Optional[CostAlert]:
    """检查 Budget 告警"""
    from app.memory.db import get_db

    budget = get_budget(workspace_id)
    if budget is None or not budget.enabled:
        return None

    # 获取本月成本
    conn = get_db()
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    row = conn.execute(
        """
        SELECT SUM(cost_usd) as total_cost
        FROM cost_records
        WHERE workspace_id = ? AND created_at >= ?
        """,
        (workspace_id, month_start),
    ).fetchone()

    total_cost = row["total_cost"] or 0
    percentage = total_cost / budget.monthly_limit_usd if budget.monthly_limit_usd > 0 else 0

    alert = None
    if percentage >= 1.0:
        alert = CostAlert(
            workspace_id=workspace_id,
            alert_type="exceeded",
            message=f"Budget exceeded: ${total_cost:.2f} / ${budget.monthly_limit_usd:.2f}",
            current_usage=total_cost,
            limit=budget.monthly_limit_usd,
            percentage=round(percentage * 100, 2),
        )
    elif percentage >= budget.warning_threshold:
        alert = CostAlert(
            workspace_id=workspace_id,
            alert_type="warning",
            message=f"Budget warning: ${total_cost:.2f} / ${budget.monthly_limit_usd:.2f} ({percentage*100:.1f}%)",
            current_usage=total_cost,
            limit=budget.monthly_limit_usd,
            percentage=round(percentage * 100, 2),
        )

    if alert:
        # 保存告警
        conn.execute(
            """
            INSERT INTO cost_alerts (workspace_id, alert_type, message, current_usage, "limit", percentage)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (alert.workspace_id, alert.alert_type, alert.message, alert.current_usage, alert.limit, alert.percentage),
        )
        conn.commit()

    return alert


def get_budget_status(workspace_id: str) -> dict:
    """获取 Budget 状态"""
    budget = get_budget(workspace_id)
    if budget is None:
        return {"has_budget": False}

    cost_stats = get_workspace_cost(workspace_id, days=30)
    current_cost = cost_stats["total_cost_usd"]
    percentage = current_cost / budget.monthly_limit_usd if budget.monthly_limit_usd > 0 else 0

    return {
        "has_budget": True,
        "monthly_limit_usd": budget.monthly_limit_usd,
        "current_usage_usd": current_cost,
        "percentage_used": round(percentage * 100, 2),
        "remaining_usd": round(max(0, budget.monthly_limit_usd - current_cost), 4),
        "enforcement": budget.enforcement,
        "warning_threshold": budget.warning_threshold,
    }
