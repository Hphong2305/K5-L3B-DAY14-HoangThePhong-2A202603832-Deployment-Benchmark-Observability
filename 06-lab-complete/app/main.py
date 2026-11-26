"""
Production AI Agent — Part 6 Final Project
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r as redis_conn, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            payload.update(extra_data)
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.handlers = [handler]
logger.setLevel(logging.INFO)
logger.propagate = False

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "agent_startup",
        extra={
            "extra_data": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        },
    )
    yield
    logger.info(
        "agent_shutdown",
        extra={"extra_data": {"event": "shutdown", "msg": "Graceful shutdown on SIGTERM"}},
    )
    try:
        redis_conn.close()
    except Exception:
        pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = "anonymous"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 2),
    }


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis not reachable")
    return {"status": "ready", "redis": "connected"}


@app.post("/ask")
def ask(
    body: AskRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    started = time.time()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(5, len(body.question.split()) * 2)
    output_tokens = max(10, len(answer.split()) * 2)
    cost_usd = record_cost(input_tokens, output_tokens)
    elapsed_ms = round((time.time() - started) * 1000, 2)

    logger.info(
        "ask_completed",
        extra={
            "extra_data": {
                "event": "request",
                "path": "/ask",
                "status": 200,
                "user_id": body.user_id,
                "ms": elapsed_ms,
                "cost_usd": round(cost_usd, 8),
            }
        },
    )
    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "cost_usd": round(cost_usd, 8),
    }
