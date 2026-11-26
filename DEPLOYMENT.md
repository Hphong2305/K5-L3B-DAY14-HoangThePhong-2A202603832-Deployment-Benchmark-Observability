# Deployment Information

## Public URL
https://k5-l3b-day14-hoangthephong-2a202603832.onrender.com

## Platform
Render (Free Tier Web Service Docker Container) / Render Blueprint (`render.yaml`)

## Test Commands

### 1. Health Check (Liveness Probe)
```bash
BASE="https://k5-l3b-day14-hoangthephong-2a202603832.onrender.com"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Actual Output: 200
curl -sS "$BASE/health"
# Actual Output: {"status":"ok","environment":"development","uptime_seconds":54.49}
```

### 2. Readiness Check (Redis Connectivity Probe)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Actual Output: 503 (or 200 when managed Redis attached)
curl -sS "$BASE/ready"
```

### 3. API Test (without Authentication -> 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Actual Output: 401
```

### 4. API Test (with Authentication -> 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"user_id":"test","question":"Hello"}'
# Expected Output: 200
```

## Environment Variables Set
- `PORT` (injected automatically by Railway/Render, defaults to `8000`)
- `ENVIRONMENT=production`
- `REDIS_URL` (pointing to managed Redis service instance)
- `AGENT_API_KEY` (secret API key set in platform environment variables, not committed to Git)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`
- `LOG_LEVEL=INFO`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
