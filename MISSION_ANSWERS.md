# Day 14 Lab — Mission Answers

> **Họ và tên:** Hoàng Thế Phong  
> **MSSV:** 2A202603832  
> **Lớp:** K5-L3B

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trực tiếp trong source code (dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - **Nguy hiểm:** Khi push code lên GitHub, key và mật khẩu DB bị lộ ngay trong lịch sử git; đồng thời không thể dùng cấu hình khác nhau cho dev/staging/production.
2. **In secret ra stdout bằng `print()` thay vì structured logging (dòng 33–38):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key trong hệ thống thu thập log. Ngoài ra `print()` không có timestamp, log level (`INFO`/`ERROR`), `request_id` hay định dạng JSON để hệ thống giám sát (Datadog, Loki) parse được.
3. **Không có Config Management & bật `DEBUG = True` cố định (dòng 21–22):**
   - Các tham số cấu hình (`DEBUG`, `MAX_TOKENS`) bị gán cứng thay vì đọc từ biến môi trường (`os.getenv` / `Settings`).
4. **Thiếu Health Check (`/health`) và Readiness (`/ready`) endpoints (dòng 42–43):**
   - Cloud platform (Railway, Render, Cloud Run, Kubernetes) và Load Balancer không có cách nào kiểm tra container còn sống hay đã sẵn sàng nhận traffic để tự động restart hoặc ngắt route khi lỗi.
5. **Bind vào `host="localhost"`, cố định `port=8000` và bật `reload=True` (dòng 49–54):**
   - `host="localhost"` (`127.0.0.1`) khiến container không nhận được kết nối từ bên ngoài network namespace của Docker (phải dùng `0.0.0.0`).
   - `port=8000` cố định sẽ lỗi trên Railway/Render/Cloud Run vì các nền tảng này cấp port động qua biến môi trường `PORT`.
   - `reload=True` tốn CPU/RAM theo dõi file và không an toàn trong môi trường production.
6. **Không xử lý Graceful Shutdown (`SIGTERM` / FastAPI `lifespan`):**
   - Khi nền tảng cloud tắt hoặc scale-down container (`SIGTERM`), process dừng đột ngột làm đứt ngang các request đang xử lý (in-flight requests).

---

### Exercise 1.2: Run develop version

Chạy bản `01-localhost-vs-production/develop/app.py` và gửi request qua query parameter:

```bash
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

*Nhận xét:* Dù ứng dụng trả lời được trên máy cá nhân, terminal server in thẳng dòng `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this` ra màn hình và thiếu toàn bộ các cơ chế vận hành an toàn trên cloud.

---

### Exercise 1.3: Comparison table (`develop/app.py` vs `production/app.py`)

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? (Why Important?) |
|---------|----------------------------|----------------------------------|--------------------------------------|
| **Config & Secrets** | Hardcode trong file (`OPENAI_API_KEY`, `DATABASE_URL`, `PORT=8000`) | Đọc từ biến môi trường qua `config.py` (`settings.port`, `settings.environment`...) | Tuân thủ **12-Factor App**: tách biệt code và config, không lộ secret lên Git, dùng cùng 1 Docker image cho mọi môi trường (dev/staging/prod). |
| **Network Binding & Port** | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port=int(os.getenv("PORT", 8000))`, tắt reload khi `DEBUG=false` | Giúp container lắng nghe được traffic từ Docker network / reverse proxy và tương thích với port động do PaaS (Railway/Render/Cloud Run) cấp. |
| **Health & Readiness Checks** | ❌ Không có | ✅ Có `GET /health` (liveness) và `GET /ready` (readiness trả `503` khi chưa sẵn sàng) | Giúp orchestrator biết khi nào cần restart container bị treo (`/health`) và khi nào load balancer được phép đưa traffic vào (`/ready`). |
| **Logging** | `print()` text tự do, in cả `OPENAI_API_KEY` | Structured JSON logging (`json.dumps` với `time`, `level`, `event`, không log secret) | Dễ dàng index, lọc, truy vấn tự động trên các hệ thống tập trung log (ELK, Loki, Cloud Logging) và đảm bảo an toàn bảo mật. |
| **Shutdown Lifecycle** | Tắt đột ngột khi nhận tín hiệu dừng | Bắt `signal.signal(signal.SIGTERM, ...)` kết hợp FastAPI `lifespan` (`is_ready = False`, chờ request hoàn tất) | **Graceful shutdown**: đảm bảo không làm rớt request của người dùng đang xử lý dở khi rolling deploy hoặc scale down. |
| **CORS & Input Validation** | Không kiểm soát CORS, nhận query string thô | Cấu hình `CORSMiddleware` với `allowed_origins` cụ thể, kiểm tra JSON body (`422` nếu thiếu `question`) | Ngăn chặn truy cập trái phép từ domain lạ trên trình duyệt và trả mã lỗi HTTP rõ ràng khi dữ liệu đầu vào sai. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**
   - `python:3.11` (bản đầy đủ dựa trên Debian, bao gồm cả trình biên dịch C/C++, build tools, thư viện hệ thống nên rất nặng ~1 GB+).
2. **Working directory là gì?**
   - `/app` (được thiết lập bởi lệnh `WORKDIR /app` — mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều thực thi tại thư mục này trong container).
3. **Tại sao `COPY requirements.txt` đứng trước `COPY . .` (copy source code)?**
   - Để tận dụng **Docker Layer Caching**: mỗi chỉ thị trong Dockerfile tạo ra 1 layer và Docker chỉ build lại từ layer đầu tiên có sự thay đổi. Vì source code (`app.py`) thay đổi liên tục còn `requirements.txt` ít khi đổi, đặt `COPY requirements.txt` và `RUN pip install` lên trước giúp Docker tái sử dụng cache của bước cài thư viện, giảm thời gian build từ hàng chục giây xuống dưới 1 giây khi chỉ sửa code.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` định nghĩa lệnh hoặc đối số **mặc định** khi chạy container và dễ dàng bị **ghi đè hoàn toàn** nếu truyền lệnh mới ở cuối `docker run <image> <new_cmd>`.
   - `ENTRYPOINT` biến container thành một file thực thi cố định (khó bị ghi đè trừ khi dùng cờ `--entrypoint`), còn các tham số truyền ở cuối `docker run` hay trong `CMD` sẽ được nối vào làm đối số (`arguments`) cho `ENTRYPOINT`.

---

### Exercise 2.2: Build and run basic container

Build image từ gốc repo và kiểm tra gọi container:

```bash
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -d --rm --name test-dev -p 8000:8000 my-agent:develop
$ curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
{"question":"What is Docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build & Image size comparison

- **Stage 1 (`FROM python:3.11-slim AS builder`):** Cài đặt các gói hệ thống phục vụ biên dịch (`gcc`, `libpq-dev`) và chạy `pip install --no-cache-dir --user -r requirements.txt` để biên dịch và cài toàn bộ Python packages vào `/root/.local`.
- **Stage 2 (`FROM python:3.11-slim AS runtime`):** Khởi tạo từ một image `python:3.11-slim` sạch, tạo user non-root (`appuser`), chỉ `COPY --from=builder /root/.local /home/appuser/.local` và mã nguồn ứng dụng sang.
- **Tại sao image nhỏ hơn?** Vì toàn bộ công cụ biên dịch nặng nề (`gcc`, `apt` cache, header files `libpq-dev`, pip wheels) đều bị bỏ lại ở Stage 1 (`builder`), không đi vào image `runtime` cuối cùng, đồng thời dùng base `python:3.11-slim` thay vì `python:3.11` full.

**Kết quả đo thực tế trên máy (`docker images | grep my-agent` & `docker image inspect`):**

```text
REPOSITORY   TAG        IMAGE ID       CREATED          SIZE (docker images)   Uncompressed/Inspect Size
my-agent     develop    4e64826d6f41   35 seconds ago   1.67GB (1670 MB)       396.14 MB (415,378,588 bytes)
my-agent     advanced   512c6749f3c3   1 second ago     265MB                  54.85 MB  (57,515,623 bytes)
```

- **Develop (`my-agent:develop`):** `1670 MB` (`1.67 GB` theo `docker images` / `396.1 MB` theo `docker image inspect`)
- **Production (`my-agent:advanced`):** `265 MB` (`54.9 MB` theo `docker image inspect`)
- **Chênh lệch (Difference):** Giảm **84.13%** theo kích thước `docker images` (từ `1670 MB` xuống `265 MB`) — hoặc giảm **86.15%** theo `docker image inspect` (`396.14 MB` xuống `54.85 MB`).

---

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc (Architecture Diagram):**

```text
                        ┌──────────────────────────────────────────────────────┐
                        │               Docker Bridge Network (internal)       │
┌──────────┐   :80/:443 │  ┌───────────────┐        :8000     ┌─────────────┐  │
│  Client  │ ─────────▶ │  │     nginx     │ ───────────────▶ │    agent    │  │
│ (curl)   │            │  │ (nginx:alpine)│   reverse proxy  │  (FastAPI)  │  │
└──────────┘            │  └───────────────┘                  └──────┬──────┘  │
                        │                                            │         │
                        │                         ┌──────────────────┼─────┐   │
                        │                         ▼ :6379                  ▼ :6333
                        │                 ┌───────────────┐        ┌───────────────┐
                        │                 │     redis     │        │    qdrant     │
                        │                 │(redis:7-alpine│        │(vector store) │
                        │                 └───────────────┘        └───────────────┘
                        └──────────────────────────────────────────────────────┘
```

- **Các services được khởi chạy:**
  1. `nginx` (`nginx:alpine`): Reverse proxy & Load balancer, là cổng duy nhất mở ra host (`80:80`, `443:443`), chuyển tiếp request vào `http://agent:8000`.
  2. `agent` (build từ `02-docker/production/Dockerfile`, stage `runtime`): FastAPI AI agent chạy ở cổng nội bộ `8000` (không expose trực tiếp ra host), chỉ khởi động sau khi `redis` và `qdrant` đạt trạng thái `service_healthy`.
  3. `redis` (`redis:7-alpine`): Lưu session cache & rate limiting ở cổng nội bộ `6379`, gắn volume `redis_data`.
  4. `qdrant` (`qdrant/qdrant:v1.9.0`): Vector database cho RAG ở cổng nội bộ `6333`, gắn volume `qdrant_data`.
- **Cách giao tiếp:** Cả 4 services cùng nằm trong mạng nội bộ `internal` (bridge network) và gọi nhau qua tên service bằng Docker DNS (`redis://redis:6379/0`, `http://qdrant:6333`, `http://agent:8000`).

**Kết quả test stack qua Nginx:**

```bash
$ curl -s http://localhost/health
{"status":"ok","environment":"staging"}

$ curl -s -X POST http://localhost/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain microservices"}'
{"question":"Explain microservices","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- **API key được check ở đâu?**
  - Tại dependency `verify_api_key(api_key: str = Security(api_key_header))` (dòng 39–54), đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` và được gắn vào endpoint `POST /ask` qua `_key: str = Depends(verify_api_key)`.
- **Điều gì xảy ra nếu thiếu hoặc sai key?**
  - Nếu thiếu header `X-API-Key` (`not api_key`): trả về `HTTP 401 Unauthorized` với thông báo `"Missing API key. Include header: X-API-Key: <your-key>"`.
  - Nếu gửi sai key (`api_key != API_KEY`): trả về `HTTP 403 Forbidden` (hoặc `401` theo chuẩn hợp đồng ở Part 6).
- **Làm sao để rotate key không gây downtime?**
  - Đọc danh sách các key hợp lệ từ biến môi trường (ví dụ `AGENT_API_KEYS="new-key,old-key"` hoặc lưu hash trong Redis/DB với TTL). Khi rotate: thêm `new-key` song song với `old-key`, cập nhật client sang `new-key`, sau khi hết traffic dùng `old-key` thì thu hồi `old-key` và restart/reload cấu hình.

**Kết quả test bản `develop` (`AGENT_API_KEY=secret-key-123`):**

```bash
# 1. Không có X-API-Key -> 401
$ curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# 2. Có X-API-Key hợp lệ -> 200
$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **Thuật toán Rate Limiting sử dụng:** **Sliding Window Counter** (lưu danh sách/deque các timestamp của request trong cửa sổ `window_seconds = 60` giây; mỗi lần gọi sẽ loại bỏ các timestamp cũ `< now - 60`).
- **Giới hạn (Limit):**
  - Role `user` (`rate_limiter_user`, tài khoản `student` / `demo123`): **10 requests / phút (60 giây)**.
  - Role `admin` (`rate_limiter_admin`, tài khoản `teacher` / `teach456`): **100 requests / phút (60 giây)**.
- **Cách phân biệt / nới giới hạn cho Admin:**
  - Khi user đăng nhập ở `POST /auth/token`, server tạo JWT chứa payload `{"sub": username, "role": role, "exp": ...}` được ký bằng `JWT_SECRET`. Khi gọi `POST /ask`, `verify_token` giải mã JWT lấy `user["role"]`, từ đó chọn `rate_limiter_admin` nếu `role == "admin"` hoặc `rate_limiter_user` nếu `role == "user"`.

**Kết quả chạy thực tế với `curl -i` (đã che JWT token):**

```bash
# 1. Gọi POST /ask không có JWT token -> 401 Unauthorized
$ curl -i -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:31:06 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# 2. Lấy JWT token tại POST /auth/token với tài khoản student / demo123
$ curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "student", "password": "demo123"}'
{"access_token":"eyJhbGciOiJIUzI...<REDACTED>","token_type":"bearer","expires_in_minutes":60}

# 3. Gọi vòng lặp với Bearer token: Request #1..#10 trả 200 OK, từ Request #11 trả 429 Too Many Requests
# --- Request #1 (200 OK) ---
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:31:06 GMT
server: uvicorn
content-length: 210
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 1","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}

# --- Request #10 (200 OK - còn 0 request trong window) ---
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:31:07 GMT
server: uvicorn
content-length: 181
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 10","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000186}}

# --- Request #11 (429 Too Many Requests) ---
HTTP/1.1 429 Too Many Requests
date: Thu, 26 Nov 2026 08:31:07 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795681928
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

---

### Exercise 4.4: Cost Guard Implementation

**Vì sao cần cả Rate Limit lẫn Cost Guard?**
- **Rate Limit** bảo vệ hệ thống theo **tần suất gọi (requests/phút)** chống spam/DDoS ngắn hạn, nhưng không ngăn được việc user gửi ít request nhưng mỗi request có prompt cực dài hoặc chạy rả rích suốt cả ngày/tháng.
- **Cost Guard** bảo vệ **ngân sách tiền thật (USD/ngày hoặc USD/tháng)** tính theo số lượng input/output tokens thực tế tiêu thụ trên LLM.

**Cách thiết kế & cài đặt Cost Guard với Redis:**
1. **Key theo chu kỳ ngày/tháng trong Redis:** Tạo key `cost:daily:<YYYY-MM-DD>` (hoặc `budget:<user_id>:<YYYY-MM>`).
2. **Kiểm tra trước khi gọi LLM (`check_budget`):** Đọc tổng số tiền đã tiêu từ Redis (`float(r.get(key) or 0.0)`). Nếu `spent >= DAILY_BUDGET_USD`, chặn ngay lập tức và trả `HTTP 402 Payment Required` trước khi tốn tiền gọi LLM API.
3. **Ghi nhận chi phí sau khi gọi LLM (`record_cost`):** Tính chi phí request dựa trên số token thực tế:
   $$\text{cost} = \frac{\text{input\_tokens}}{1000} \times 0.00015 + \frac{\text{output\_tokens}}{1000} \times 0.0006$$
   Sau đó dùng lệnh nguyên tử `r.incrbyfloat(key, cost)` trên Redis để cộng dồn an toàn giữa nhiều worker/instance và đặt `r.expire(key, 86400 * 2)` để tự động dọn key cũ.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Liveness (`GET /health`) vs Readiness (`GET /ready`)

| Tiêu chí | Liveness Probe (`GET /health`) | Readiness Probe (`GET /ready`) |
|----------|--------------------------------|--------------------------------|
| **Câu hỏi trả lời** | Process của container còn sống không hay đã treo/deadlock? | Instance này có sẵn sàng nhận và xử lý user traffic ngay lúc này không? |
| **Kiểm tra gì?** | Chỉ kiểm tra bản thân HTTP event loop của ứng dụng (`return {"status": "ok"}`, luôn trả `200` kể cả khi Redis/DB sập). | Kiểm tra các phụ thuộc bên ngoài bắt buộc như `redis.ping()`, kết nối DB, model đã nạp xong chưa. |
| **Khi trả về lỗi (`503` / timeout)** | Platform (Kubernetes / Cloud Run / Railway) **kill và restart lại container**. | Load Balancer **tạm ngừng route traffic mới** vào instance đó nhưng **không restart** container. |
| **Vì sao `/health` không nên phụ thuộc Redis?** | Nếu Redis tạm thời gián đoạn mà `/health` trả `503`, orchestrator sẽ restart toàn bộ dàn container agent liên tục (cascading restart loop) dù bản thân process agent không bị lỗi. |

---

### Exercise 5.2: Graceful Shutdown (`SIGTERM`)

- Khi container bị dừng (`docker stop`, scale down, hoặc rolling deploy), hệ thống gửi tín hiệu `SIGTERM` tới tiến trình PID 1 trước, chờ một khoảng grace period (mặc định 10–30 giây) rồi mới gửi `SIGKILL`.
- Để tắt êm (Graceful Shutdown):
  1. Trong `Dockerfile`, `uvicorn` phải chạy ở **PID 1** (dùng exec form `CMD ["sh", "-c", "exec uvicorn ..."]`).
  2. Khi nhận `SIGTERM`, `uvicorn` ngừng nhận kết nối mới, chờ các request in-flight xử lý xong và trả `200 OK`, sau đó chạy phần sau `yield` trong `lifespan(app)` của FastAPI để đóng kết nối Redis/DB rồi thoát với `exit code 0`.
  3. Lưu ý: Nếu tự đăng ký `signal.signal(signal.SIGTERM, handler)` để ghi log, bắt buộc phải gọi lại signal handler gốc của `uvicorn`, nếu không sẽ ghi đè làm `uvicorn` không bao giờ tự thoát.

---

### Exercise 5.3: Stateless Design

- **Vì sao giữ state trong RAM (`conversation_history = {}`) bị hỏng khi chạy nhiều instance?**
  - Khi scale ngang lên 3 instances (`agent-1`, `agent-2`, `agent-3`) đứng sau Load Balancer (Nginx round-robin), mỗi container có không gian bộ nhớ (RAM) độc lập.
  - Nếu Request 1 của User A rơi vào `agent-1` (lưu lịch sử hội thoại hoặc bộ đếm rate limit vào RAM của `agent-1`), thì khi Request 2 của User A được Nginx điều phối sang `agent-2`, `agent-2` hoàn toàn không biết lịch sử trước đó hay số lượt đã gọi của User A. Đồng thời nếu `agent-1` restart, toàn bộ dữ liệu trong RAM mất sạch.
- **Giải pháp Stateless:** Đẩy toàn bộ state (session, conversation history, rate limit counters, cost counters) ra kho lưu trữ tập trung tốc độ cao là **Redis** (`session:<session_id>`, `ratelimit:<key>`, `cost:daily:<date>`). Nhờ đó bất kỳ instance nào cũng đọc/ghi chung một nguồn sự thật.

---

### Exercise 5.4 & 5.5: Load Balancing & Stateless Test (`05-scaling-reliability/production/`)

Chạy stack với 3 instances (`docker compose -p k5-day14-scaling up -d --build --scale agent=3`) mở cổng `8080` (`POST /chat`) và chạy `python test_stateless.py`:

```text
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
 ✔ Container k5-day14-scaling-redis-1  Healthy
 ✔ Container k5-day14-scaling-agent-1  Started
 ✔ Container k5-day14-scaling-agent-2  Started
 ✔ Container k5-day14-scaling-agent-3  Started
 ✔ Container k5-day14-scaling-nginx-1  Started

$ python test_stateless.py
============================================================
Stateless Scaling Demo
============================================================

Session ID: 601bc66c-8443-4503-8e64-e43b584d93cd

Request 1: [instance-3f1bda]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-981376]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-36437d]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-3f1bda]
  Q: How does load balancing work?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 5: [instance-981376]
  Q: What is Redis used for?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-981376', 'instance-3f1bda', 'instance-36437d'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: How does load balancing work?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Redis used for?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...

✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:**
- 5 câu hỏi liên tiếp trong cùng một `session_id` (`601bc66c-8443-4503-8e64-e43b584d93cd`) được Nginx phân phối xoay vòng (round-robin) qua cả 3 container agent khác nhau (`instance-3f1bda`, `instance-981376`, `instance-36437d`).
- Khi gọi `GET /chat/{session_id}/history`, toàn bộ **10 messages** (5 cặp `user`/`assistant`) vẫn được lưu giữ đầy đủ và đúng thứ tự nhờ mọi instance đều đọc/ghi chung key `session:601bc66c-8443-4503-8e64-e43b584d93cd` trên Redis.
