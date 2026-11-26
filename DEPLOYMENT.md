# Deployment Information

## Public URL
https://day14-production-agent-hoangthephong.up.railway.app

## Platform
Railway (Docker Multi-stage Build + Managed Redis) / Render Blueprint (`render.yaml`)

## Test Commands

### 1. Health Check (Liveness Probe)
```bash
BASE="https://day14-production-agent-hoangthephong.up.railway.app"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Expected: 200
curl -sS "$BASE/health"
# Expected: {"status":"ok","environment":"production","uptime_seconds":...}
```

### 2. Readiness Check (Redis Connectivity Probe)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Expected: 200
curl -sS "$BASE/ready"
# Expected: {"status":"ready","redis":"connected"}
```

### 3. API Test (without Authentication -> 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Expected: 401
```

### 4. API Test (with Authentication -> 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"user_id":"test","question":"Hello"}'
# Expected: 200
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
