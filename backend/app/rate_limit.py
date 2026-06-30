"""集中式速率限制配置。单例 limiter，共享 Redis 后端。"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings

_redis_url = settings.cache.redis_url

if _redis_url and _redis_url.startswith("redis://"):
    _storage_uri = f"{_redis_url}/1"
elif _redis_url:
    _storage_uri = f"redis://{_redis_url}/1"
else:
    _storage_uri = None

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
)

# 预定义速率限制
CHAT_STREAM_LIMIT = "20/minute"
RAG_QUERY_LIMIT = "30/minute"
LANGGRAPH_LIMIT = "5/minute"
API_DEFAULT_LIMIT = "60/minute"
