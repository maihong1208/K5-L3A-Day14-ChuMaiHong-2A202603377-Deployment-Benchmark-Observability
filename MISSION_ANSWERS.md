# Day 14 Lab — Mission Answers

> Ghi chú môi trường: Đã chạy đầy đủ với **Docker Desktop (`29.9.3`)** cho Part 2, Part 5, Part 6 (`check_production_ready.py`) và Part 7 (Bước 1 & Bước 2). Riêng bước **deploy lên Cloud** (Part 3/CP6) cần tài khoản Railway/Render của bạn, và check `SIGTERM` trực tiếp vào process Python trên Windows của `check_production_ready.py` báo `⚠️` (cần chạy trong WSL2/Linux để đạt `PASS 12/12`).

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong source code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` — nếu push lên GitHub, secret bị lộ ngay lập tức.
2. **Dùng `print()` thay cho structured logging và làm lộ secret ra log** (dòng 33–34, 38): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` ghi cả API key ra stdout và khó parse/tìm kiếm trên hệ thống log tập trung.
3. **Không có health check / readiness endpoint** (dòng 42–43): thiếu `GET /health` và `GET /ready`, nên cloud platform hoặc load balancer không biết container còn sống hay sẵn sàng nhận traffic không.
4. **Hardcode `host`, `port` và bật `reload=True`** (dòng 49–54): `host="localhost"` không nhận kết nối từ bên ngoài container, `port=8000` không đọc từ `PORT` env var (Railway/Render inject động), `reload=True` gây tốn tài nguyên và không an toàn cho production.
5. **Không xử lý graceful shutdown và thiếu CORS / lifecycle management**: tắt đột ngột có thể cắt ngang request đang xử lý; `DEBUG = True` (dòng 21) cũng cố định trong code thay vì đọc từ env.

### Exercise 1.2: Kết quả chạy bản `develop`

```text
GET / -> 200 {"message":"Hello! Agent is running on my machine :)"}
POST /ask?question=Hello -> 200 {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

*(Lưu ý: bản `develop` nhận `question` qua query parameter `?question=Hello`, gửi body JSON sẽ bị `422`.)*

### Exercise 1.3: So sánh `develop` vs `production` (`01-localhost-vs-production/production/app.py` & `config.py`)

| Feature | Develop | Production | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `PORT=8000`, `DEBUG=True` trong `app.py` | Đọc qua `Settings` dùng `os.getenv(...)` trong `config.py` + `validate()` fail-fast khi thiếu `AGENT_API_KEY` ở `production` | Tách biệt config khỏi code (12-Factor), cùng một artifact chạy được trên dev/staging/prod và không lộ secret vào Git |
| **Health & Readiness** | Không có | Có `GET /health` (liveness) và `GET /ready` (readiness trả `503` khi `is_ready=False`) | Platform biết khi nào cần restart container hỏng (`/health`) và khi nào ngừng route traffic vào instance chưa sẵn sàng (`/ready`) |
| **Logging** | `print("[DEBUG] ...")`, in cả `OPENAI_API_KEY` | Structured JSON logging (`logging` + `json.dumps`), chỉ log độ dài question/response và `client_ip` | Dễ thu thập, lọc và phân tích trên Datadog/Loki/ELK; không làm rò rỉ thông tin nhạy cảm |
| **Shutdown & Binding** | `uvicorn.run(..., host="localhost", port=8000, reload=True)`, tắt đột ngột | `host="0.0.0.0"`, `port=settings.port`, `lifespan` + `signal.signal(signal.SIGTERM, handle_sigterm)` | Container nhận traffic từ bên ngoài qua `0.0.0.0`, lắng nghe đúng `PORT` cloud cấp và hoàn thành request đang chạy trước khi thoát |

---

## Part 2: Docker

### Exercise 2.1: Trả lời câu hỏi từ `02-docker/develop/Dockerfile`

1. **Base image là gì?** `python:3.11` (chứa Debian đầy đủ + Python 3.11 runtime và các build tools, dung lượng ~1 GB).
2. **Working directory là gì?** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY 02-docker/develop/requirements.txt .` đứng trước `COPY 02-docker/develop/app.py .`?** Để tận dụng **Docker build layer cache**: `requirements.txt` ít thay đổi hơn source code (`app.py`), nên khi chỉ sửa `app.py`, Docker tái sử dụng cache của layer `RUN pip install --no-cache-dir -r requirements.txt` mà không phải tải và cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?** `ENTRYPOINT` định nghĩa lệnh thực thi cố định của container (khó bị ghi đè nếu không truyền `--entrypoint`), còn `CMD` cung cấp lệnh hoặc tham số mặc định và có thể bị ghi đè dễ dàng khi truyền tham số lúc `docker run`.

### Exercise 2.2 & 2.3: Kích thước image và lợi ích multi-stage

- **Lệnh đã chạy từ gốc repo:**
  ```bash
  docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
  docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
  docker images my-agent
  ```
- **Kết quả đo thực tế (`docker image inspect --format "{{.Size}}"`):**
  - **Develop (`my-agent:develop`)**: **1590.5 MB** (`1,667,784,003` bytes)
  - **Production (`my-agent:advanced`)**: **228.7 MB** (`239,815,401` bytes)
  - **Chênh lệch**: giảm **85.6%** dung lượng
- **Kết quả chạy & test container `my-agent:develop`:**
  ```text
  POST http://127.0.0.1:8120/ask?question=What+is+Docker?
  -> 200 {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
  ```
- **Cơ chế giảm dung lượng của `02-docker/production/Dockerfile`**:
  - **Stage 1 (`builder`, `python:3.11-slim`)**: cài `gcc`, `libpq-dev` và chạy `pip install --no-cache-dir --user -r requirements.txt` để compile packages vào `/root/.local`.
  - **Stage 2 (`runtime`, `python:3.11-slim`)**: chỉ copy thư mục `/root/.local`, `main.py` và `utils/mock_llm.py`, bỏ lại hoàn toàn `gcc`, `libpq-dev` và apt cache; đồng thời chạy dưới user non-root `appuser` và khai báo `HEALTHCHECK`.

### Exercise 2.4: Kiến trúc Docker Compose stack (`02-docker/production/docker-compose.yml`)

```text
Client
  │ (HTTP :80 / HTTPS :443)
  ▼
Nginx (nginx:alpine, reverse proxy + rate limit 10r/s)
  │ (network: internal)
  ▼
Agent (FastAPI, port 8000, depends_on redis & qdrant healthy)
  ├──► Redis (redis:7-alpine, port 6379, session/rate-limit cache)
  └──► Qdrant (qdrant/qdrant:v1.9.0, port 6333, vector DB)
```

- **Kết quả test qua Nginx (`docker compose -p k5-day14-part2 -f 02-docker/production/docker-compose.yml up -d --build`)**:
  ```text
  GET http://127.0.0.1/health
  -> 200 {"status":"ok","uptime_seconds":0.3,"version":"2.0.0","timestamp":"2026-11-25T08:43:05.322888"}

  POST http://127.0.0.1/ask -d '{"question": "Explain microservices"}'
  -> 200 {"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
  ```

---

## Part 3: Cloud Deployment

### URL Public (Agent Part 6)
- **URL**: `[CẦN DEPLOY — chạy railway up hoặc Render Blueprint trong 06-lab-complete/ rồi điền URL vào đây và DEPLOYMENT.md]`
- **Screenshots**: xem `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` (sau khi deploy).

### So sánh `railway.toml` và `render.yaml` (trong `06-lab-complete/`)

| Tiêu chí | `railway.toml` | `render.yaml` (Blueprint) |
| --- | --- | --- |
| **Định dạng & phạm vi** | TOML, cấu hình build & deploy cho **1 service** hiện tại | YAML (IaC Blueprint), có thể khai báo **nhiều services** (web, Redis, envVars, region, plan) trong cùng 1 file |
| **Build / Runtime** | `[build] builder = "DOCKERFILE"` | `runtime: docker` (hoặc `runtime: python` với `buildCommand`/`startCommand`) |
| **Health check** | `healthcheckPath = "/health"` dưới `[deploy]` | `healthCheckPath: /health` trong định nghĩa service |
| **Quản lý biến môi trường & secret** | Đặt qua CLI (`railway variables set`) hoặc Dashboard, không khai báo secret trong file | Khai báo ngay trong `envVars:` của `render.yaml`; secret dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập trên Dashboard) để không lộ giá trị thật |

### Exercise 3.3: Mô tả pipeline CI/CD của Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD gồm 4 bước tuần tự (`waitFor`):
1. **Test (`python:3.11-slim`)**: cài dependencies từ `requirements.txt` + `pytest` và chạy `pytest tests/ -v --tb=short` trước khi build.
2. **Build (`gcr.io/cloud-builders/docker`)**: build Docker image với layer cache (`--cache-from`) và gắn 2 tag (`$COMMIT_SHA` và `latest`).
3. **Push (`gcr.io/cloud-builders/docker`)**: đẩy image vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`gcr.io/cloud-builders/gcloud`)**: deploy bản `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`, `min-instances=1`, `max-instances=10`, `512Mi` RAM, secret lấy từ Google Secret Manager qua `--set-secrets`), kết hợp `service.yaml` khai báo `livenessProbe` (`/health`), `startupProbe` (`/ready`) và `containerConcurrency: 80`.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)
- Kiểm tra header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` trong dependency `verify_api_key`.
- Nếu thiếu header → `401`; nếu sai key → `403` (trong `develop/app.py`); rotate key bằng cách cập nhật biến môi trường `AGENT_API_KEY` và reload/restart service.
- **Output test thực tế**:
```text
No key: 401 {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
With key: 200 {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)
- **Algorithm rate limiting** trong `rate_limiter.py`: **Sliding Window Counter** lưu danh sách timestamp (`deque`) cho từng `username`, xóa timestamp cũ hơn `now - 60`, giới hạn `10 req/phút` cho `user` (`student`) và `100 req/phút` cho `admin` (`teacher`, chọn `rate_limiter_admin` khi `role == "admin"`).
- **Output test thực tế** (`POST /auth/token` với `student`/`demo123`, rồi gọi `POST /ask` 15 lần liên tiếp):
```text
POST /auth/token -> 200 (token_type=bearer)
No token -> 401 {"detail":"Authentication required. Include: Authorization: Bearer <token>"}

Requests 1..10  -> HTTP 200
  Sample 200: {"question":"Test 1","answer":"Đây là câu trả lời từ AI agent (mock)...","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}

Requests 11..15 -> HTTP 429
  Headers: x-ratelimit-limit: 10, x-ratelimit-remaining: 0, retry-after: 59
  Body: {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách làm Cost Guard với Redis
- **Tại sao cần cả Rate Limit và Cost Guard?** Rate limit chặn spam theo số request/phút (tốc độ), nhưng một ít request prompt rất dài vẫn có thể tiêu tốn nhiều token và vượt ngân sách. Cost guard bảo vệ **chi phí thực tế (USD)** dựa trên token input/output.
- **Cách triển khai trong Redis**: trước khi gọi LLM, đọc tổng chi phí hiện tại từ Redis (`cost:daily:<YYYY-MM-DD>` hoặc `budget:<user>:<YYYY-MM>`); nếu `current >= budget_limit` thì trả `HTTP 402 Payment Required`. Sau khi gọi LLM, tính `cost = (in_tok/1000)*price_in + (out_tok/1000)*price_out` và cộng dồn nguyên tử bằng `INCRBYFLOAT` kèm `EXPIRE`.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health check, Readiness & Graceful Shutdown (`05-scaling-reliability/develop/app.py`)
- **`/health` (Liveness)** vs **`/ready` (Readiness)**:
  - `/health` kiểm tra process còn sống để orchestrator quyết định có **restart container** hay không.
  - `/ready` kiểm tra khả năng sẵn sàng phục vụ (model đã load xong, Redis/DB kết nối được, chưa bước vào giai đoạn shutdown) để load balancer quyết định có **route traffic** tới instance đó hay không (trả `503` khi chưa sẵn sàng, không làm container bị restart oan).
- **Output test thực tế (`develop/app.py`)**:
```text
GET /health -> 200 {"status":"ok","uptime_seconds":1.0,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:30:56.889366+00:00","checks":{"memory":{"status":"ok","used_percent":58.9}}}
GET /ready  -> 200 {"ready":true,"in_flight_requests":1}
POST /ask   -> 200 {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```
- **Graceful shutdown**: khi nhận `SIGTERM`, `lifespan` đặt `_is_ready = False` (ngừng nhận traffic mới qua `/ready`), middleware `track_requests` đếm `_in_flight_requests` và vòng lặp shutdown đợi các request đang xử lý hoàn thành trước khi process thoát với exit code `0`.

### Exercise 5.3, 5.4 & 5.5: Stateless Design & Load Balancing (`05-scaling-reliability/production/`)
- **Tại sao state trong RAM hỏng khi scale nhiều instance?** Nếu lưu `conversation_history` trong dict ở RAM của từng process, request 1 có thể vào `instance-1` còn request 2 bị Nginx round-robin sang `instance-2` (không có dữ liệu turn 1). Đưa session sang **Redis** (`session:{session_id}` với TTL 3600s) giúp mọi instance đều đọc/ghi cùng một trạng thái.
- **Kết quả chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` + `python test_stateless.py`**:
  ```text
  Session ID: 1fd4ff75-e5f1-4a4f-94da-ccc4fb07422a

  Request 1: [instance-8ed915]
  Request 2: [instance-1c3c12]
  Request 3: [instance-8ed915]
  Request 4: [instance-9df975]
  Request 5: [instance-1c3c12]

  Total requests: 5
  Instances used: {'instance-9df975', 'instance-1c3c12', 'instance-8ed915'}
  ✅ All requests served despite different instances!

  --- Conversation History ---
  Total messages: 10
  ✅ Session history preserved across all instances via Redis!
  ```
  - Dù 5 request đi qua cả 3 container (`instance-8ed915`, `instance-1c3c12`, `instance-9df975`) qua Nginx round-robin ở cổng `8080`, toàn bộ 10 messages (5 câu hỏi + 5 câu trả lời) vẫn liên tục vì session được lưu chung trong Redis.

---

## Part 6: Final Project (`06-lab-complete/`)

Đã hoàn thiện toàn bộ mã nguồn và cấu hình trong `06-lab-complete/`:
- `app/config.py`: đọc `PORT`, `ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD` từ biến môi trường.
- `app/redis_client.py`: khởi tạo Redis client non-blocking lúc import + `redis_healthy()` cho `/ready`.
- `app/auth.py`: xác thực `X-API-Key` bằng `APIKeyHeader(auto_error=False)` và `secrets.compare_digest`, trả `401` khi thiếu/sai.
- `app/rate_limiter.py`: sliding window 60s bằng Redis sorted set (`ZREMRANGEBYSCORE` → `ZCARD` → `ZADD` + `EXPIRE`), trả `429` kèm `Retry-After`.
- `app/cost_guard.py`: kiểm tra ngân sách (`402` khi vượt `DAILY_BUDGET_USD`) và cộng dồn chi phí vào Redis bằng `INCRBYFLOAT`.
- `app/main.py`: `GET /health`, `GET /ready`, `POST /ask`, `JsonFormatter` xuất log JSON hợp lệ, `lifespan` + chain handler `SIGTERM`.
- `Dockerfile` (multi-stage `python:3.11-slim`, image **238 MB** < 500 MB), `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`.

### Output chạy `python check_production_ready.py` đầy đủ với Docker Desktop

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ⚠️  Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 11/12 tiêu chí đạt · 42/42 checks passed
  ⚠️  Chưa kiểm tra được: Graceful shutdown
```

*(Chi tiết mục 11: `✅ Code xử lý SIGTERM / lifespan shutdown`, `✅ Docker: docker stop tắt êm (exit code 0, 0.6s)`; trên Windows check gửi `SIGTERM` trực tiếp vào process Python báo `⚠️`, nhưng đã kiểm chứng thêm bằng `check_production_ready.py --skip-docker` trong container `python:3.11-slim` POSIX cho kết quả `✅ Khi chạy: SIGTERM lúc đang có request → request vẫn 200, process tự thoát — exit code 0`.)*

---

## AI Log

- **Mục đích sử dụng**: Hỗ trợ đọc cấu trúc repo, triển khai các module trong `06-lab-complete/` theo đúng hợp đồng của `check_production_ready.py`, sửa lỗi `PYTHONUSERBASE` trong `benchmark-observability/production/Dockerfile`, chạy toàn bộ các bài test Docker/benchmark và tổng hợp số liệu từ file JSON/CSV/log thực tế.
- **Kết quả & tự kiểm tra**:
  - Đã chạy `06-lab-complete/check_production_ready.py` đầy đủ với Docker (`42/42 checks passed`, image `238 MB`, `docker stop` `exit code 0` trong `0.6s`, stateless rate limit qua Redis pass sau khi restart agent).
  - Đã đo kích thước image Part 2 (`1590.5 MB` → `228.7 MB`, giảm `85.6%`) và chạy Part 5 `--scale agent=3` (`test_stateless.py` pass trên 3 instances).
  - Đã chạy thật Part 7 Bước 1 (`eval_v1.json`, `eval_v2.json`, sửa `KNOWLEDGE_BASE` để `eval_v2_fixed.json` đạt `23/23` `0` regression, 7 file `load_v2_*.json`) và Part 7 Bước 2 (`promtool` `SUCCESS`, Locust `scale_1` & `scale_3`, Jaeger trace + log JSON, và 4 thí nghiệm alert firing).
