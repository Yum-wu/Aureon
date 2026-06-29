"""Security API Router"""
from typing import Optional
import os
import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from app.rate_limit import limiter
from app.security import (
    PIIDetector,
    SSOProvider,
    UserRole,
    create_sso_provider,
    list_sso_providers,
    delete_sso_provider,
    log_pii_detection,
    require_role,
    create_access_token,
)
from app.exceptions import NotFoundError, AuthenticationError

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Security"])

# PII 检测器实例
pii_detector = PIIDetector()


# ── SSO Login ──

class LoginRequest(BaseModel):
    """登录请求"""
    email: str = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=6, description="密码（至少 6 位）")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str


@router.post("/sso/login", response_model=LoginResponse)
async def sso_login(req: LoginRequest):
    """SSO 登录：验证邮箱密码，签发 JWT。

    开发模式（AUTH__ENVIRONMENT=dev 且未配置 API_AUTH_KEY）下，
    任意合法邮箱 + 8 位以上密码均可登录，默认 ADMIN 角色。
    生产模式下需配置用户数据库或对接外部 IdP。
    """
    from app.config import settings

    # 开发模式：接受任意合法邮箱 + 密码（仅非生产平台）
    _is_prod_platform = (
        os.environ.get("RAILWAY_ENVIRONMENT") == "production"
        or os.environ.get("ENV") == "production"
    )
    if settings.auth.environment == "dev" and not settings.api_auth_key:
        if _is_prod_platform:
            logger.critical("security.dev_login_blocked_in_production")
            raise AuthenticationError("Authentication service unavailable")
        token = create_access_token({
            "sub": req.email,
            "role": "ADMIN",
            "dev_only": True,
        })
        logger.warning("security.dev_login_used", email=req.email)
        return LoginResponse(
            access_token=token,
            token_type="bearer",
            email=req.email,
            role="ADMIN",
        )

    # 生产模式：需要配置用户验证逻辑
    # TODO: 对接企业 IdP 或用户数据库
    # 目前仅支持 API Key 认证，邮箱密码登录不可用
    raise AuthenticationError(
        "Email/password login is not configured. "
        "Use API Key authentication or configure an identity provider."
    )


# ── Demo Token (guest preview, no API key leaked to frontend) ──

# Demo token: short-lived, VIEWER-only JWT for anonymous preview.
# Replaces the previous design of hardcoding the production API_AUTH_KEY in
# the frontend bundle (Architecture Review C3).
_DEMO_TOKEN_EXPIRY_SECONDS = 3600  # 1 hour


class DemoTokenResponse(BaseModel):
    """Demo token response — limited VIEWER-role JWT for guest preview."""
    access_token: str
    token_type: str = "bearer"
    role: str = "viewer"
    demo: bool = True
    expires_in: int = _DEMO_TOKEN_EXPIRY_SECONDS


@router.post("/demo-token", response_model=DemoTokenResponse)
@limiter.limit("20/minute")
async def issue_demo_token(request: Request):
    """Issue a demo token with admin role for full feature preview.

    Demo token carries ADMIN role so users can explore all pages
    including cost governance, admin panel, and analytics.

    No authentication required — this is the public entry point for the
    "体验演示账号" button. The endpoint itself is whitelisted in the API key
    middleware so it does not require X-API-Key.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    token = create_access_token({
        "sub": "demo-guest",
        "role": "ADMIN",
        "demo": True,
        "exp": int(now.timestamp()) + _DEMO_TOKEN_EXPIRY_SECONDS,
    })
    logger.info("security.demo_token_issued")
    return DemoTokenResponse(access_token=token)


# ── PII Detection Endpoints ──

@router.post("/pii/detect")
async def detect_pii(
    text: str,
    user: dict = Depends(require_role(UserRole.VIEWER)),
):
    """检测文本中的 PII"""
    results = pii_detector.detect(text)
    return {"pii_found": len(results) > 0, "results": results}


@router.post("/pii/mask")
async def mask_pii(
    text: str,
    pii_type: Optional[str] = None,
    user: dict = Depends(require_role(UserRole.VIEWER)),
):
    """脱敏文本中的 PII"""
    masked_text = pii_detector.mask(text, pii_type)
    return {"masked": masked_text}


@router.post("/pii/scan-document")
async def scan_document(
    document_id: str,
    content: str,
    action: str = "mask",
    user: dict = Depends(require_role(UserRole.VIEWER)),
):
    """扫描文档中的 PII 并记录"""
    detections = pii_detector.detect(content)

    for detection in detections:
        masked_value = pii_detector.mask(detection["value"], detection["type"])
        log_pii_detection(
            document_id=document_id,
            pii_type=detection["type"],
            value=detection["value"],
            original_length=len(detection["value"]),
            masked_value=masked_value,
            action_taken=action,
        )

    return {
        "document_id": document_id,
        "pii_count": len(detections),
        "detections": detections,
    }


# ── SSO Endpoints ──

@router.post("/sso/providers", response_model=SSOProvider, status_code=201)
async def create_sso_provider_endpoint(
    provider: SSOProvider,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """创建 SSO 提供商 (需要 ADMIN 角色)"""
    return create_sso_provider(provider)


@router.get("/sso/providers", response_model=list[SSOProvider])
async def list_sso_providers_endpoint(
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """列出所有 SSO 提供商 (需要 ADMIN 角色)"""
    return list_sso_providers()


@router.delete("/sso/providers/{name}", status_code=204)
async def delete_sso_provider_endpoint(
    name: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """删除 SSO 提供商 (需要 ADMIN 角色)"""
    success = delete_sso_provider(name)
    if not success:
        raise NotFoundError("SSO provider not found")


# ── Rate Limiting Config ──

@router.get("/rate-limits/config")
async def get_rate_limit_config(
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取速率限制配置"""
    return {
        "enabled": True,
        "requests_per_minute": 60,
        "requests_per_hour": 1000,
        "tokens_per_minute": 100000,
        "tokens_per_hour": 1000000,
    }
