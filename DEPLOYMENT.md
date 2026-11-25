# Deployment Information

## Public URL
https://k5-l3a-day14-chumaihong-2a202603377-ohfw.onrender.com

## Platform
Render (Docker Web Service + Key Value Redis, Root Directory: `06-lab-complete`, Region: Singapore, Plan: Free)

## Test Commands & Observed Results

*(Đặt `BASE="https://k5-l3a-day14-chumaihong-2a202603377-ohfw.onrender.com"` và `AGENT_API_KEY` từ cấu hình trên Render — không ghi secret vào Git).*

### 1. Health Check (expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Kết quả: 200  {"status":"ok","environment":"production"}
```

### 2. Readiness Check (expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Kết quả: 200  {"status":"ready"}
```

### 3. Auth Check — Không có API Key (expected: 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# Kết quả: 401  {"detail":"Missing or invalid API key"}
```

### 4. API Test — Có API Key (expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"What is deployment?"}'
# Kết quả: 200  {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được.","user_id":null,"cost_usd":1.2e-05}
```

### 5. Public URL Check (`check_production_ready.py`)
```bash
python check_production_ready.py --public-url https://k5-l3a-day14-chumaihong-2a202603377-ohfw.onrender.com
# ✅ Public URL: GET https://k5-l3a-day14-chumaihong-2a202603377-ohfw.onrender.com/health → 200
```

## Environment Variables Set (trên Render Dashboard — không ghi giá trị secret vào Git)
- `PORT` (do Render tự cấp, mặc định `10000`)
- `ENVIRONMENT=production`
- `REDIS_URL` (Internal Key Value URL trên Render)
- `AGENT_API_KEY` (đặt trên Render Dashboard)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
