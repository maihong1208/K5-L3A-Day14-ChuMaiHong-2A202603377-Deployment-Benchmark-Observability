"""
Rate limiting (tiêu chí 7) — sliding window 60 giây lưu trong Redis.
"""
from collections import defaultdict, deque
import hashlib
import logging
import threading
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
_fallback_lock = threading.Lock()
_fallback_windows: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit_key(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"ratelimit:{digest}"


def _check_memory_fallback(redis_key: str, limit: int, now: float) -> None:
    with _fallback_lock:
        window = _fallback_windows[redis_key]
        cutoff = now - WINDOW_SECONDS
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
        window.append(now)


def check_rate_limit(key: str) -> None:
    """Giới hạn tối đa RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    limit = max(1, settings.rate_limit_per_minute)
    now = time.time()
    redis_key = _rate_limit_key(key)

    if r is None:
        _check_memory_fallback(redis_key, limit, now)
        return

    window_start = now - WINDOW_SECONDS
    member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        pipe2 = r.pipeline()
        pipe2.zadd(redis_key, {member: now})
        pipe2.expire(redis_key, WINDOW_SECONDS + 5)
        pipe2.execute()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Redis rate_limit fallback: %s", exc)
        _check_memory_fallback(redis_key, limit, now)
