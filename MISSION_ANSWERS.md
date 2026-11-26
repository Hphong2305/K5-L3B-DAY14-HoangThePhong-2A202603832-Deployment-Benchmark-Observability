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
