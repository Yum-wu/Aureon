"""Security API Router"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.security import (
    PIIDetector,
    SSOProvider,
    UserRole,
    create_sso_provider,
    list_sso_providers,
    delete_sso_provider,
    log_pii_detection,
    require_role,
)
from app.exceptions import NotFoundError, AureonException

router = APIRouter(tags=["Security"])

# PII 检测器实例
pii_detector = PIIDetector()


# ── PII Detection Endpoints ──

@router.post("/pii/detect")
async def detect_pii(text: str):
    """检测文本中的 PII"""
    results = pii_detector.detect(text)
    return {"pii_found": len(results) > 0, "results": results}


@router.post("/pii/mask")
async def mask_pii(text: str, pii_type: Optional[str] = None):
    """脱敏文本中的 PII"""
    masked_text = pii_detector.mask(text, pii_type)
    return {"original": text, "masked": masked_text}


@router.post("/pii/scan-document")
async def scan_document(
    document_id: str,
    content: str,
    action: str = "mask",
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
async def get_rate_limit_config():
    """获取速率限制配置"""
    return {
        "enabled": True,
        "requests_per_minute": 60,
        "requests_per_hour": 1000,
        "tokens_per_minute": 100000,
        "tokens_per_hour": 1000000,
    }
