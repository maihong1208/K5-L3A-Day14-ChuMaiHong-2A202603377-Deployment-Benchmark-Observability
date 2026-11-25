"""
Production AI Agent — Part 6 Final Project.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import signal
import sys
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format mọi dòng log của app thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> logging.Logger:
    app_logger = logging.getLogger("production_agent")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        app_logger.addHandler(handler)
    return app_logger


logger = _configure_logging()


def _log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"extra_fields": {"event": event, **fields}})


_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _on_sigterm(signum, frame) -> None:
    _log_event("sigterm_received", signal=signum)
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _on_sigterm)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _log_event("startup", environment=settings.environment, port=settings.port)
    yield
    _log_event("shutdown", environment=settings.environment)


app = FastAPI(
    title="Production AI Agent",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn chạy (không phụ thuộc Redis)."""
    return {
        "status": "ok",
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi Redis sẵn sàng, 503 khi mất kết nối."""
    if not redis_healthy():
        _log_event("readiness_failed", level=logging.WARNING, reason="redis_unavailable")
        raise HTTPException(status_code=503, detail="Redis not ready")
    return {"status": "ready"}


@app.post("/ask")
def ask(
    body: AskRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    started = time.perf_counter()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = _estimate_tokens(body.question)
    output_tokens = _estimate_tokens(answer)
    cost_usd = record_cost(input_tokens, output_tokens)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    _log_event(
        "request",
        method=request.method,
        path="/ask",
        status=200,
        user_id=body.user_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 8),
        ms=elapsed_ms,
    )
    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "cost_usd": round(cost_usd, 8),
    }
