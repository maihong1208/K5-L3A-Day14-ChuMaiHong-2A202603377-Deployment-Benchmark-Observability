"""
Cost guard (tiêu chí 8) — theo dõi và giới hạn chi phí LLM trong Redis.
"""
from datetime import datetime, timezone
import logging
import threading

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_fallback_lock = threading.Lock()
_fallback_spend: dict[str, float] = {}


def _budget_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{day}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget -> raise HTTPException(402)."""
    key = _budget_key()
    limit = settings.daily_budget_usd
    current = 0.0

    if r is not None:
        try:
            raw = r.get(key)
            current = float(raw) if raw is not None else 0.0
        except Exception as exc:
            logger.warning("Redis check_budget fallback: %s", exc)
            with _fallback_lock:
                current = _fallback_spend.get(key, 0.0)
    else:
        with _fallback_lock:
            current = _fallback_spend.get(key, 0.0)

    if current >= limit:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "used_usd": round(current, 8),
                "budget_usd": limit,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    key = _budget_key()

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, 48 * 3600)
            pipe.execute()
            return cost
        except Exception as exc:
            logger.warning("Redis record_cost fallback: %s", exc)

    with _fallback_lock:
        _fallback_spend[key] = _fallback_spend.get(key, 0.0) + cost
    return cost
