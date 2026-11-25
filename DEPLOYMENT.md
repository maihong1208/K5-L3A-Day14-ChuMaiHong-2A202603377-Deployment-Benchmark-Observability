# Deployment Information

> Sau khi deploy thư mục `06-lab-complete/` lên Railway hoặc Render (theo [CHECKPOINTS.md — CP6](CHECKPOINTS.md#cp6--cloud-deployment-250--315)), điền URL thật bên dưới và chạy 4 lệnh kiểm tra để lưu kết quả.

## Public URL
https://<your-agent>.up.railway.app

## Platform
Railway (hoặc Render)

## Test Commands

### 1. Health Check (expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://<your-agent>.up.railway.app/health"
```

### 2. Readiness Check (expected: 200 khi Redis đã nối)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://<your-agent>.up.railway.app/ready"
```

### 3. Auth Check — Không có API Key (expected: 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://<your-agent>.up.railway.app/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
```

### 4. API Test — Có API Key (expected: 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://<your-agent>.up.railway.app/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Environment Variables Set (trên Cloud Dashboard — không ghi giá trị secret vào Git)
- `PORT` (do nền tảng tự cấp)
- `ENVIRONMENT=production`
- `REDIS_URL` (trỏ tới Redis add-on trên nền tảng)
- `AGENT_API_KEY` (đặt trên dashboard / `railway variables set`)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
