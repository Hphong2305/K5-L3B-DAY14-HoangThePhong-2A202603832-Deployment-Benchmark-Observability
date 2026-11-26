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
