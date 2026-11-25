"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

r = (
    redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    if settings.redis_url
    else None
)


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho endpoint /ready."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
