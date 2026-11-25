# Benchmark & Observability Report — Day 14

> Các số liệu trong báo cáo được lấy trực tiếp từ các file JSON trong `reports/`, các file CSV trong `benchmark-results/`, Jaeger traces, Prometheus API và log JSON của agent khi chạy stack Docker `06-lab-complete/benchmark-observability/production/`.

**Họ tên:** Chu Mai Hồng (MSSV: 2A202603377)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows + Docker Desktop 29.9.3 (WSL2 backend) + Python 3.14.7 (`.venv`)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Khớp cấu hình `--slo-p95-ms 500` của `load_test.py`: 95% người dùng nhận phản hồi trong nửa giây (mock LLM bình thường ~170–240ms + retrieval ~20ms), còn 5% đuôi chậm bất thường (`MOCK_SLOW_RATE=0.03`) không làm kéo tụt trải nghiệm đa số |
| Error rate `/ask` | `< 2.0 %` | Khớp cấu hình `--slo-error-rate 0.02`: mock LLM có `MOCK_ERROR_RATE=0.01` (1% lỗi upstream), ngưỡng 2% tạo error budget hợp lý cho nhiễu ngắn trước khi kích hoạt alert ở ngưỡng cao hơn (`> 5%`) |
| Accuracy trên golden dataset | `≥ 80 %` (mục tiêu release sau fix KB: `100 %`) | Đảm bảo agent v2 trả lời đúng kiến thức trọng tâm trên `golden_dataset.jsonl` và không bị regression khi thay đổi prompt/KB |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, `--requests 300`)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.98 | 206.6 | 236.1 | 1704.1 | 1.33% | PASS |
| 10 | 36.21 | 204.2 | 240.8 | 1727.6 | 1.33% | PASS |
| 50 | 85.19 | 230.1 | 950.6 | 1710.6 | 0.67% | FAIL (p95 > 500ms) |
| 100 | 42.13 | 430.0 | 5268.2 | 5459.8 | 1.00% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. Từ `c=1` lên `c=10`, RPS tăng gần tuyến tính (`3.98` → `36.21 req/s`) trong khi `p50` (~205ms) và `p95` (~240ms) gần như giữ nguyên vì agent vẫn còn dư năng lực xử lý. Lên `c=50`, RPS tăng lên `85.19 req/s` nhưng hàng đợi bắt đầu xuất hiện nên `p95` vọt lên `950.6 ms` (vượt SLO 500ms). Tới `c=100`, hệ thống quá tải/nghẽn (1 worker uvicorn + contention trên Windows), khiến `p50` tăng lên `430.0 ms`, `p95` lên tới `5268.2 ms` và throughput thực tế còn **giảm xuống** `42.13 req/s`.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 209.3 | 238.5 | 252.5 |
| 0.03 (mặc định) | 248.0 | 246.1 | 1709.1 |
| 0.1 | 380.8 | 1722.4 | 1737.3 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

Các chỉ số percentile cao (**p99**, và **p95** khi tỉ lệ chậm vượt 5%) nhạy nhất với request chậm:
- Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (3% request chậm), `avg` chỉ tăng nhẹ từ `209.3 ms` lên `248.0 ms` (+38.7 ms, trông vẫn rất ổn), nhưng `p99` nhảy vọt gần 7 lần từ `252.5 ms` lên `1709.1 ms`.
- Khi `MOCK_SLOW_RATE = 0.1` (10% request chậm > 5%), cả `p95` cũng vọt lên `1722.4 ms` (vi phạm SLO 500ms) trong khi `avg` mới ở mức `380.8 ms`.
- Do đó không nên đặt SLO theo `average`, vì giá trị trung bình bị 90–97% request nhanh làm loãng và **che giấu nhóm người dùng đang phải chờ gần 1.7 giây**.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.7 | 108.8 | 113.7 |
| Tổng cost (USD) | $0.000399 | $0.000758 | $0.000791 |
| Cost / câu đúng (USD) | $0.00039915 | $0.00003607 | $0.00003439 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "xác thực", "api key"], ...)` giải thích JWT có token, chữ ký số và thời gian hết hạn vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["kubernetes", "hpa", "chỉ số"], ...)` giải thích Kubernetes HPA scale theo CPU, memory và custom metrics vào `KNOWLEDGE_BASE` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng**: v2 dùng retrieval (RAG) đưa context vào prompt nên accuracy tăng từ **4.3% (1/23)** lên **91.3% (21/23)** và đạt **100% (23/23)** sau khi bổ sung KB.
- **Chi phí**: mỗi câu của v2 tốn gần gấp đôi token (`108.8`–`113.7` so với `56.7`) và tổng chi phí cao hơn ~2 lần (`$0.000791` vs `$0.000399`), nhưng tính theo **cost / câu đúng** thì v2 (`$0.00003439`) **rẻ hơn >11 lần** so với v1 (`$0.00039915`) vì v1 trả lời sai 22/23 câu.
- **Latency**: v2 chậm hơn một chút ở p50 (`193.7–213.6 ms` so với `167.2 ms` của v1) do thêm bước tìm kiếm KB (~20ms) và prompt dài hơn. Đây là đánh đổi hợp lý trong thực tế.

**Quality gate trong CI:**
- Khi chạy thử `python eval/run_eval.py --url http://127.0.0.1:8001 --baseline reports/eval_v2.json` (agent v1 so với baseline v2), script phát hiện `20` câu regression và thoát với **exit code `1`** (`Quality gate: ❌ FAIL`).
- Trong GitHub Actions, thêm step chạy `run_eval.py --min-accuracy 0.85 --baseline reports/eval_v2.json`; nếu exit code khác `0`, job CI fail và tự động chặn merge PR.

```yaml
- name: Agent quality gate
  run: |
    cd 06-lab-complete/benchmark-observability/develop
    AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
    sleep 3
    python eval/run_eval.py --min-accuracy 0.9 --baseline reports/eval_v2.json
```

---

## 4. Observability stack (production)

> Đã chạy unit test alert rules (`promtool test rules /p/alert_rules_test.yml` → `SUCCESS`), khởi động toàn bộ stack Docker (`agent`, `nginx`, `prometheus`, `grafana`, `jaeger`, `locust`) và chạy các thí nghiệm chaos.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải ([grafana-dashboard.png](screenshots/grafana-dashboard.png))
- [x] Một trace chậm trong Jaeger ([jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png))
- [x] Một trace lỗi trong Jaeger ([jaeger-error-trace.png](screenshots/jaeger-error-trace.png))
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** ([prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png))

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | `70.7 s` (`for: 1m`) | Error rate (`/ask`) & LLM calls ok vs error |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | `131.1 s` (`for: 2m`) | Latency p50 / p95 / p99 |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | Firing ngay khi burn rate > `$2/h` (0.0s sau khi chuyển từ tải trước; `for: 2m`) | Estimated cost / hour (USD) & Tokens / s |
| D | `docker pause` 1 instance | `AgentInstanceDown` | `40.3 s` (`for: 30s`) | Instances Up |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | — | Retrieval hit ratio & bảng Agent versions |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng chỉ đo error rate, latency, CPU/RAM và trạng thái `up`, trong khi chuyển về `v1` chỉ làm giảm chất lượng câu trả lời (vẫn trả `200 OK` và còn nhanh hơn). Để phát hiện sự cố chất lượng trong production cần:
1. Chạy **Eval CI/CD quality gate** trên golden dataset trước mỗi lần deploy.
2. Theo dõi metric nghiệp vụ/chất lượng như `retrieval_hits_total{result="hit"|"miss"}` (khi hit ratio tụt xuống 0 thì cảnh báo ngay).
3. Chạy **online eval / LLM-as-a-judge** trên một mẫu traffic thực tế và thu thập phản hồi người dùng (thumbs up/down).

### 4.3 Debug bằng trace

**Trace chậm nhất đã trích xuất từ Jaeger & logs:**

- `trace_id`: `f3666a9777a3faf70a2c53385c9075bc`
- Tổng thời gian (`POST /ask`): `1726.1 ms` (`agent.run`: `1722.5 ms` / `99.8%`; `agent.retrieve_context`: `24.9 ms` / `1.4%`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1697.3 ms`, `98.3%`) → nút thắt nằm ở lời gọi LLM upstream (tail latency), không phải bước retrieval hay code FastAPI.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T08:55:32.451629+00:00", "level": "INFO", "service": "observable-agent", "instance": "c91dba04d5e7", "event": "llm_call", "trace_id": "f3666a9777a3faf70a2c53385c9075bc", "span_id": "a55d36d32873c065", "request_id": "75764fc41319", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1696.7}
```

**Trace lỗi đã trích xuất:**

- `trace_id`: `58f5f90c9c23e5bea08963e1e0f2963f`
- Dòng log tương ứng:

```json
{"ts": "2026-11-25T08:52:47.736281+00:00", "level": "INFO", "service": "observable-agent", "instance": "c91dba04d5e7", "event": "llm_error", "trace_id": "58f5f90c9c23e5bea08963e1e0f2963f", "span_id": "347db02587768c6f", "request_id": "8b4072946339", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu lấy từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `Aggregated`, kèm chi tiết `POST /ask`):

| Số instance | RPS (`Aggregated` / `/ask`) | p50 (ms) | p95 (ms) (`Aggregated` / `/ask`) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | `65.90` (`59.78`) | `190` | `220` (`220`) | `1700` | `67 / 7868` (`0.85%`) |
| 3 | `66.18` (`60.12`) | `190` | `220` (`230`) | `1700` | `70 / 7911` (`0.88%`) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance **không cải thiện `p95` (`220–230 ms`) hay `RPS` (`~66 req/s`)** vì:
1. Agent FastAPI chạy bất đồng bộ (`async/await`), nên ở mức 100 user (`wait_time = between(1, 2)` giây → tổng tải tối đa ~66 req/s), **1 instance chưa hề bão hòa CPU**.
2. Nút thắt chính nằm ở **latency của mỗi lần gọi LLM upstream** (`MOCK_LATENCY_MS=120` + jitter + 3% slow request `+1500ms`) và thời gian chờ của chính user mô phỏng trong Locust. Tăng số container agent chỉ tăng khả năng chịu tải khi agent bị nghẽn CPU hoặc giới hạn worker, chứ không rút ngắn thời gian chờ phản hồi từ LLM provider.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. `average` latency che giấu tail latency (`p95`/`p99`): với `MOCK_SLOW_RATE=0.03`, `avg` là `248.0 ms` nhưng `p99` đã vọt lên `1709.1 ms`.
  2. Benchmark chất lượng (`eval`) cần chạy cùng benchmark hiệu năng (`load_test`) vì một phiên bản rẻ hơn/nhanh hơn (như `v1`) có thể trả lời sai tới >95% câu hỏi, làm `cost / câu đúng` đắt hơn bản RAG (`v2`) hơn 11 lần.
  3. 3 trụ cột Metrics – Traces – Logs kết hợp qua `trace_id` và `route` template (tránh cardinality cao như `user_id`) giúp khoanh vùng nhanh xem chậm do code hay do LLM upstream.
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  - Metric & alert cho tỷ lệ retrieval miss (`retrieval_hits_total{result="miss"}` tăng đột biến), tỷ lệ rate-limit (`429`) và budget exhausted (`402`), kết nối Redis fail (`/ready` trả `503`), cùng synthetic probe từ bên ngoài load balancer để bắt lỗi `504` ở tầng Nginx.
