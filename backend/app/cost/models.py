"""Cost Governance 数据模型 — 成本追踪、聚合、Budget 配置和告警。

与现有 cost/__init__.py 中的 CostRecord/BudgetConfig 兼容，
新增 TokenUsage、CostAggregation、CostSummary 等聚合模型。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """单次 Token 使用记录。"""
    tenant_id: str = Field(..., description="租户 ID")
    model: str = Field(..., description="使用的 LLM 模型")
    input_tokens: int = Field(0, ge=0, description="输入 token 数")
    output_tokens: int = Field(0, ge=0, description="输出 token 数")
    cost_usd: float = Field(0.0, ge=0.0, description="成本（USD）")
    workspace_id: Optional[str] = Field(None, description="Workspace ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    timestamp: datetime = Field(default_factory=datetime.now)


class CostAggregation(BaseModel):
    """成本聚合结果。"""
    tenant_id: str
    period: str = Field(..., description="聚合周期: 7d/30d/90d")
    total_cost: float = Field(0.0, description="总成本（USD）")
    burn_rate: float = Field(0.0, description="日均消耗（USD/天）")
    total_input_tokens: int = Field(0, description="总输入 token 数")
    total_output_tokens: int = Field(0, description="总输出 token 数")
    by_model: Dict[str, float] = Field(default_factory=dict, description="按模型分组的成本")
    by_workspace: Dict[str, float] = Field(default_factory=dict, description="按 Workspace 分组的成本")
    trend: List[Dict[str, Any]] = Field(default_factory=list, description="日趋势数据点")


class BudgetConfigNew(BaseModel):
    """Budget 配置（新模型，与现有 BudgetConfig 兼容）。"""
    tenant_id: str = Field(..., description="租户 ID")
    workspace_id: Optional[str] = Field(None, description="Workspace ID（None=租户级）")
    monthly_limit_usd: float = Field(..., gt=0, description="月度限额（USD）")
    warning_threshold: float = Field(0.8, ge=0, le=1, description="告警阈值（0-1）")
    critical_threshold: float = Field(0.95, ge=0, le=1, description="严重阈值（0-1）")
    hard_limit: bool = Field(False, description="超限是否阻断查询")


class BudgetAlert(BaseModel):
    """Budget 告警。"""
    id: str = Field(..., description="告警 ID")
    tenant_id: str
    workspace_id: Optional[str] = None
    threshold_type: str = Field(..., description="告警类型: warning/critical/hard_limit")
    current_usage: float = Field(..., description="当前用量（USD）")
    budget_limit: float = Field(..., description="Budget 限额（USD）")
    percentage: float = Field(..., description="用量百分比")
    created_at: datetime = Field(default_factory=datetime.now)


class CostSummary(BaseModel):
    """成本摘要（Dashboard 用）。"""
    total_cost: float = Field(0.0, description="总成本")
    burn_rate: float = Field(0.0, description="日均消耗")
    total_tokens: int = Field(0, description="总 token 数")
    budget_used_pct: float = Field(0.0, description="Budget 使用百分比")
    budget_total: Optional[float] = Field(None, description="Budget 总额")
    trend_direction: str = Field("stable", description="趋势方向: up/down/stable")
    data_available: bool = Field(True, description="是否有实际数据（False 表示空数据源）")
