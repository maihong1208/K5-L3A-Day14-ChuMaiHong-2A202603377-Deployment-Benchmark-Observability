"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)


def _create_redis_client():
    raw_url = (settings.redis_url or "").strip()
    if not raw_url:
        return None
    if "://" not in raw_url:
        raw_url = f"redis://{raw_url}"
    try:
        return redis.from_url(
            raw_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception as exc:
        logger.warning("Invalid REDIS_URL (%s): %s", type(exc).__name__, exc)
        return None


r = _create_redis_client()


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho endpoint /ready."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
