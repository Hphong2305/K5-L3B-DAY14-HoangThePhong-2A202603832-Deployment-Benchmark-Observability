# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Hoàng Thế Phong — 2A202603832
**Ngày chạy:** 2026-11-26
**Môi trường:** macOS Apple Silicon (arm64, 10 threads), Docker Desktop 28.4.0, Python 3.12 / 3.11-slim

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo 95% người dùng nhận được câu trả lời trong dưới 0.5 giây (trải nghiệm hội thoại thời gian thực mượt mà), trong khi vẫn cho phép phần nhỏ tail latency (< 5%) của LLM upstream. |
| Error rate `/ask` | < 2.0 % | Tương ứng với Error Budget 2% (98% request thành công), dung sai hợp lý cho các lỗi mạng/upstream 503 thoáng qua từ LLM provider mà chưa ảnh hưởng nghiêm trọng đến người dùng. |
| Accuracy trên golden dataset | ≥ 85 % (100% sau khi bổ sung KB) | Đảm bảo chất lượng câu trả lời RAG đạt chuẩn kiến thức miền (domain knowledge) và chặn mọi bản cập nhật gây regression trước khi merge/deploy. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.34 | 190.8 | 218.5 | 1689.3 | 1.67% | PASS |
| 10 | 44.11 | 189.6 | 217.1 | 1663.2 | 0.33% | PASS |
| 50 | 108.69 | 191.7 | 221.4 | 1694.8 | 0.33% | PASS |
| 100 | 61.79 | 298.4 | 2848.0 | 3965.8 | 0.67% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- Từ `concurrency=1` lên `10`, RPS tăng gần như tuyến tính gấp ~10 lần (`4.34` → `44.11 req/s`) trong khi `p50` (~`190 ms`) và `p95` (~`217 ms`) giữ nguyên vì `asyncio` event loop xử lý song song thời gian chờ I/O (`asyncio.sleep` của retrieval và LLM).
- Từ `10` lên `50`, RPS tiếp tục tăng lên `108.69 req/s` (tăng ~2.46 lần thay vì 5 lần), bắt đầu xuất hiện chi phí chuyển ngữ cảnh (context switching) và giới hạn connection pool.
- Ở `concurrency=100`, RPS không những không tăng mà **tụt xuống `61.79 req/s`**, đồng thời `p95` vọt lên `2848.0 ms` (`p99 = 3965.8 ms`, vi phạm SLO `p95 ≤ 500 ms`). Lý do là một process uvicorn đơn lẻ cùng backlog socket/HTTP client bị bão hoà (queuing delay theo định luật Little: $L = \lambda W$), các request phải xếp hàng chờ event loop giải phóng.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 186.0 | 217.0 | 222.0 |
| 0.03 (mặc định) | 225.1 | 218.9 | 1695.3 |
| 0.1 | 314.7 | 1682.8 | 1706.7 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **`p99` và `p95` (high percentiles)** nhạy nhất với hiện tượng tail latency:
  - Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (3% request bị chậm thêm `1500 ms`), `avg` chỉ tăng nhẹ thêm `39.1 ms` (`186.0 ms` → `225.1 ms`) và `p95` gần như không đổi (`218.9 ms`), nhưng **`p99` nhảy vọt gấp ~7.6 lần lên `1695.3 ms`**.
  - Khi `MOCK_SLOW_RATE = 0.1` (10% request bị chậm > ngưỡng 5%), cả **`p95` cũng nhảy vọt lên `1682.8 ms`** (vi phạm SLO `< 500 ms`), trong khi `avg` mới ở mức `314.7 ms` (vẫn thấp hơn nhiều so với 500 ms!).
- Nếu đặt SLO theo `average`, hệ thống vẫn báo "xanh" (`314.7 ms < 500 ms`) dù cứ 10 người dùng thì có 1 người phải chờ gần 1.7 giây. Vì vậy SLO bắt buộc phải đặt theo percentile (`p95`, `p99`) để bảo vệ trải nghiệm của nhóm người dùng ở đuôi phân phối.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.3 | 109.1 | 113.7 |
| Tổng cost (USD) | $0.000406 | $0.000762 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040635 | $0.00003627 | $0.00003436 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm tài liệu với từ khoá kích hoạt `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"Kubernetes HPA (Horizontal Pod Autoscaler) scale số pod dựa trên CPU, memory hoặc custom metrics như RPS hay độ dài hàng đợi."* |
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu với từ khoá kích hoạt `["jwt"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"API key là chuỗi bí mật cố định, không tự hết hạn. JWT là token có chữ ký số, chứa thông tin user và thời điểm hết hạn; server xác minh chữ ký mà không cần tra database."* |

**Cách dùng exit code của `run_eval.py` làm Quality Gate trong CI để chặn merge:**
- Script `eval/run_eval.py` kiểm tra 2 điều kiện khi truyền `--min-accuracy` và `--baseline`: (1) `accuracy >= min_accuracy`, và (2) không có câu nào trước đây pass ở baseline mà nay bị fail (`regressions == 0`). Nếu vi phạm một trong hai, script kết thúc với **`sys.exit(1)`** (exit code khác 0).
- Trong GitHub Actions (`.github/workflows/eval.yml`), khi chạy lệnh `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85 --baseline reports/eval_v2.json`, bất kỳ bước nào trả về exit code `1` sẽ làm CI job báo đỏ (` status: failure`), từ đó GitHub Branch Protection tự động chặn nút **Merge Pull Request**.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Latency & Chi phí trên mỗi request:** Agent v2 có thêm bước retrieval tìm kiếm tài liệu (~20 ms) và chèn context vào prompt nên `p95 latency` tăng nhẹ từ `189.8 ms` lên `215.4–219.2 ms` (+25 ms) và số token trung bình mỗi câu tăng gần gấp đôi (`57.3` → `113.7 tokens`), làm tổng cost cho 23 câu tăng từ `$0.000406` lên `$0.000790`.
- **Hiệu quả chi phí thực tế (`Cost / câu đúng`):** Agent v1 trả lời chung chung nên chỉ đúng `1/23` câu (`4.3%`), khiến chi phí cho mỗi câu trả lời có ích lên tới **`$0.00040635`**. Ngược lại, Agent v2 (sau khi bổ sung KB) đạt **`100%` (`23/23`)**, kéo chi phí trên mỗi câu trả lời đúng xuống chỉ còn **`$0.00003436` — rẻ hơn gấp ~11.8 lần** so với v1. Đánh đổi thêm ~25 ms latency và gấp đôi token để lấy độ chính xác từ 4.3% lên 100% là hoàn toàn xứng đáng.

---

## 4. Observability stack (production)

*(Đang chạy Docker stack cho CP8 — sẽ cập nhật kết quả thực nghiệm Bước 2 ngay ở CP8)*
