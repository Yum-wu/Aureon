from pydantic import BaseModel, Field, field_validator
from typing import Optional


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="用户消息",
    )
    session_id: str | None = None
    model: Optional[str] = Field(default=None, description="Model name from MODEL_REGISTRY (e.g. 'qwen3.6-flash', 'zhipu')")

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        """Strip whitespace and reject whitespace-only input."""
        v = v.strip()
        if not v:
            raise ValueError("消息内容不能为空")
        return v


class SessionListResponse(BaseModel):
    sessions: list[str]
    count: int


class StatusResponse(BaseModel):
    status: str
    session_id: str | None = None
