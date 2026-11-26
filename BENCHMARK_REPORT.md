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

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](file:///Users/phong/Desktop/BaiTapVinUni/K5-L3B-DAY14-HoangThePhong-2A202603832-Deployment-Benchmark-Observability/screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](file:///Users/phong/Desktop/BaiTapVinUni/K5-L3B-DAY14-HoangThePhong-2A202603832-Deployment-Benchmark-Observability/screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [screenshots/jaeger-error-trace.png](file:///Users/phong/Desktop/BaiTapVinUni/K5-L3B-DAY14-HoangThePhong-2A202603832-Deployment-Benchmark-Observability/screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**: [screenshots/prometheus-alert-firing.png](file:///Users/phong/Desktop/BaiTapVinUni/K5-L3B-DAY14-HoangThePhong-2A202603832-Deployment-Benchmark-Observability/screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~1m (`for: 1m` khi error rate > 5%) | Panel **Error Rate (%)** trên Grafana vọt lên 22.4% |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | ~2m (`for: 2m` khi p95 > 1s) | Panel **Response Latency Percentiles** (p95 vọt lên ~1.958s) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | ~2m (`for: 2m` khi burn rate > $2/hr) | Panel **Hourly Cost Burn Rate** (vọt lên $9.73/hr) |
| D | `docker pause` 1 instance | `AgentInstanceDown` | ~30s (`for: 30s` scrape fail) | Panel **Healthy Instances / Up Status** (tụt từ 3 xuống 2) |
| E | `AGENT_VERSION=v1` | *Không có alert nào firing* | N/A | Panel **Request Throughput & Latency** (v1 phản hồi bình thường 200 OK) |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

1. **Nguyên nhân không firing:** Các Golden Signals và health check hạ tầng (Prometheus, Jaeger) chỉ theo dõi tầng kỹ thuật: mã trạng thái HTTP (200 OK), độ trễ (latency thấp ~180 ms), tỷ lệ lỗi mạng (0%), và tài nguyên CPU/RAM. Khi chuyển sang `v1`, API vẫn trả lời rất nhanh và không hề có crash/exception, do đó hệ thống giám sát hạ tầng nhận định là hoàn toàn "bình thường/khỏe mạnh", dù chất lượng câu trả lời đã suy thoái nghiêm trọng (accuracy sụt từ 100% xuống 4.3%).
2. **Cách phát hiện trong môi trường Production:**
   - **Continuous Synthetic Probing / Online Evaluation:** Chạy một worker ngầm định kỳ (ví dụ mỗi 5–15 phút) gửi bộ câu hỏi chuẩn (golden evaluation dataset) đến production endpoint và dùng LLM-as-a-Judge chấm điểm semantic relevance & accuracy. Nếu accuracy rơi xuống dưới ngưỡng (ví dụ < 85%), hệ thống kích hoạt alert `AgentSemanticQualityDegraded`.
   - **User Feedback & Behavior Signals:** Theo dõi metric phản hồi người dùng (tỷ lệ nhấn dislike/thumbs-down, tỷ lệ người dùng phải hỏi lại - re-prompt rate, độ dài phiên hội thoại). Khi tỷ lệ negative feedback tăng đột biến (> 10%), kích hoạt cảnh báo suy giảm trải nghiệm.
   - **Output Token & Embedding Drift Monitoring:** Giám sát phân phối độ dài câu trả lời (v1 trả lời trung bình ~57 tokens so với v2 ~114 tokens) và vector embedding khoảng cách ngữ nghĩa so với baseline để phát hiện model/prompt drift.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `956189035ddfad904276ef5c5606d297`
- Tổng thời gian: `1731.28 ms`
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1696.81 ms`, `98.01%`)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"event": "llm_call", "trace_id": "956189035ddfad904276ef5c5606d297", "span_id": "8bf89f293bd6d464", "request_id": "631e62627bcb", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 69, "output_tokens": 31, "cost_usd": 2.9e-05, "llm_ms": 1692.3}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.61 req/s (Agg: 65.73) | 200 ms (Agg: 190) | 230 ms (Agg: 230) | 1700 ms | 71 (1.00%) |
| 3 | 60.16 req/s (Agg: 66.32) | 190 ms (Agg: 190) | 230 ms (Agg: 220) | 1700 ms | 73 (1.02%) |

*(Ghi chú: Số liệu trên trích xuất trực tiếp từ file `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` cho endpoint `POST /ask` và dòng tổng hợp `Aggregated` tương ứng).*

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale từ 1 lên 3 instance không làm giảm đáng kể p95:** `p95` giữ nguyên ở mức `220–230 ms`, và `p99` cố định ở mức `1700 ms`.
- **Nút thắt thực sự (Bottleneck):**
  - Trái với các ứng dụng tính toán nặng CPU nơi việc nhân rộng số instance giúp giải tỏa hàng đợi, Agent LLM là ứng dụng thuần túy I/O-bound.
  - Nút thắt thời gian nằm hoàn toàn ở **thời gian phản hồi của upstream LLM** (`MOCK_LATENCY_MS = 180 ms` và khi gặp 3% tail latency `MOCK_SLOW_MS = 1500 ms` thì tổng latency của span LLM vọt lên `~1700 ms`).
  - Việc tăng thêm số lượng agent container phía sau Nginx giúp tăng tổng sức chứa chịu tải đồng thời (throughput capacity), nhưng **không thể rút ngắn độ trễ nội tại của cuộc gọi mạng ra LLM**.
- **Giải pháp tối ưu đúng đắn trong thực tế:**
  1. *Semantic Caching:* Cache các câu hỏi tương tự trên Redis bằng vector embeddings để trả lời trong < 10 ms mà không cần gọi LLM.
  2. *Streaming Response (SSE):* Trả token đầu tiên (TTFT) trong < 200 ms để mang lại cảm giác phản hồi tức thì cho người dùng.
  3. *Request Hedging / Speculative Execution:* Khi một request gọi LLM vượt quá ngưỡng 500 ms, tự động bắn một request song song sang endpoint hoặc model dự phòng.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Average là chỉ số đánh lừa nguy hiểm — SLO bắt buộc phải đặt theo Percentile (p95/p99):** Một hệ thống có `avg = 225 ms` vẫn có thể có `p99 = 1700 ms` khiến 1-5% người dùng chịu trải nghiệm tồi tệ. SLO và alert bắt buộc phải dựa trên p95/p99.
  2. **Metrics cho biết "có sự cố", nhưng Tracing mới cho biết "nguyên nhân ở đâu":** Prometheus phát hiện p95 tăng cao, nhưng chỉ khi mở Jaeger trace ta mới nhìn thấy span `chat mock-llm-small` chiếm tới 98% tổng thời gian request do tail latency từ upstream model.
  3. **Khoảng cách giữa System Health và AI Semantic Quality:** Một AI agent có thể "xanh" 100% trên dashboard hạ tầng (200 OK, latency thấp) nhưng câu trả lời lại hoàn toàn sai lệch hoặc vô dụng. Observability toàn diện cho AI agent phải kết hợp cả Golden Signals hạ tầng lẫn Continuous Evaluation chất lượng ngữ nghĩa.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  1. **Metric TTFT (Time To First Token) & Token Generation Rate (tokens/s):** Đo lường trực tiếp độ trễ cảm nhận của người dùng đối với các endpoint streaming SSE.
  2. **Semantic Cache Hit Ratio:** Đo tỷ lệ câu hỏi được giải quyết trực tiếp từ Redis cache để tối ưu hóa chi phí API token.
  3. **Alert LLM Provider Rate-Limit / Quota Exhaustion:** Cảnh báo ngay khi nhận mã HTTP 429 từ nhà cung cấp LLM (OpenAI, Anthropic, Gemini) để tự động failover sang provider dự phòng.
  4. **Alert Semantic Drift / Low Confidence Score:** Cảnh báo khi cosine similarity giữa câu hỏi người dùng và tri thức trong vector database xuống thấp, báo hiệu người dùng đang hỏi những chủ đề chưa có trong Knowledge Base.
