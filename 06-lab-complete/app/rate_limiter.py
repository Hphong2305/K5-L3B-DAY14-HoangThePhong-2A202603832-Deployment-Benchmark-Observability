"""
Rate limiting (tiêu chí 7).
"""
import time
import uuid
from collections import defaultdict, deque
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60
_fallback_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    now = time.time()
    limit = settings.rate_limit_per_minute
    redis_key = f"ratelimit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + WINDOW_SECONDS - now) + 1 if oldest else WINDOW_SECONDS
            retry_after = max(1, retry_after)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex[:8]}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS)
        pipe.execute()
    except HTTPException:
        raise
    except Exception:
        window = _fallback_windows[key]
        while window and window[0] < now - WINDOW_SECONDS:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(1, int(window[0] + WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)
