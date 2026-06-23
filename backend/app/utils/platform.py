"""统一的生产平台检测工具函数。"""
import os


def is_production_platform() -> bool:
    """检测当前是否运行在生产 PaaS 平台上。"""
    return any([
        os.environ.get("RAILWAY_ENVIRONMENT"),
        os.environ.get("RENDER"),
        os.environ.get("FLY_APP_NAME"),
        os.environ.get("DYNO"),
        os.environ.get("VERCEL"),
        os.environ.get("NETLIFY"),
    ])
