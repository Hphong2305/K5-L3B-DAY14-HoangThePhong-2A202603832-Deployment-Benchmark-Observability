"""
Cost guard (tiêu chí 8).
"""
import time
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_fallback_cost: float = 0.0


def _cost_key() -> str:
    today = time.strftime("%Y-%m-%d")
    return f"cost:daily:{today}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    budget = min(settings.daily_budget_usd, settings.monthly_budget_usd)
    try:
        val = r.get(_cost_key())
        spent = float(val) if val is not None else 0.0
    except Exception:
        spent = _fallback_cost

    if spent >= budget:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Budget exceeded",
                "spent_usd": round(spent, 8),
                "budget_usd": budget,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    global _fallback_cost
    cost = (
        max(1, input_tokens) / 1000.0 * PRICE_INPUT_PER_1K
        + max(1, output_tokens) / 1000.0 * PRICE_OUTPUT_PER_1K
    )
    key = _cost_key()
    try:
        r.incrbyfloat(key, cost)
        r.expire(key, 86400 * 2)
    except Exception:
        _fallback_cost += cost
    return cost
