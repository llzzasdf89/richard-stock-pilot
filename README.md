# Richard Stock Pilot

Richard Stock Pilot is a React + FastAPI stock screening app for US and HK stocks. It selects stocks whose Z-Score is at least 1.5 or at most -1.5, with configurable market cap and average monthly volume filters.

## Current Scope

- Daily screening: reads stored daily metrics from SQLite.
- Intraday screening: discovers Longbridge screener indicators, runs screener search with the slider filters, then fetches daily and intraday bars for local Z-Score and reference Bollinger calculations.
- Chinese UI.
- Four application APIs:
  - `GET /api/daily-screenings`
  - `GET /api/intraday-screenings`
  - `GET /api/message-push-settings`
  - `PUT /api/message-push-settings`
- Unified API response body:

```json
{
  "success": true,
  "data": {},
  "code": 200
}
```

Internal failures still return HTTP 200 with:

```json
{
  "success": false,
  "data": {
    "message": "Internal server error",
    "request_id": "..."
  },
  "code": 500
}
```

## Environment

Create a root-level local environment file:

```bash
cp .env.example .env
```

Fill `.env` with your Longbridge credentials:

```dotenv
DATABASE_URL=sqlite:///./richard_stock_pilot.db
LONGBRIDGE_APP_KEY=your app key
LONGBRIDGE_APP_SECRET=your app secret
LONGBRIDGE_ACCESS_TOKEN=your access token
LONGBRIDGE_REGION=cn
LONGBRIDGE_ENABLE_OVERNIGHT=true
DAILY_SYNC_SYMBOLS="AAPL.US 700.HK"
DAILY_SYNC_BAR_COUNT=60
VITE_API_BASE=
```

`VITE_API_BASE` may stay empty in local development because Vite proxies `/api` to the backend. Set it to the backend URL when deploying the frontend separately.

Existing shell environment values take priority, so production deployments can still inject secrets without changing files. When credentials are available, `LongbridgeService` uses the official `longbridge` Python SDK. Without credentials, it falls back to deterministic mock data so local development still runs.

### PushPlus 建仓机会提醒

在 `.env` 中启用：

```dotenv
ENABLE_MESSAGE_PUSH=true
MESSAGE_PUSH_PROVIDER=pushplus
PUSHPLUS_TOKEN=your PushPlus token
```

开启后，FastAPI 启动时分别预热美股和港股的历史日 K 缓存。后台消息设置页可保存 10–120 分钟（步长 10 分钟）的推送间隔，以及最低市值和最低月均成交量。调度点每天以中国时间 `00:00` 为基准按所选间隔固定对齐；不能整除一天的间隔也会在跨日时重新从次日 `00:00` 对齐。保存设置不会立即扫描，而是从严格晚于保存时刻的下一个固定调度点生效。只有符合 Z-Score 建仓条件的股票才会通过 PushPlus 逐只发送；没有匹配股票时不会发送消息。

本功能不需要公网 IP 或域名，本地电脑也可以运行。电脑必须保持开机、联网且不进入休眠。后台定时任务第一版只支持单 Worker；不要同时启动多个 FastAPI Worker，否则会重复扫描和推送。

## Start

Run both frontend and backend from the project root:

```bash
./start.sh
```

The script creates `.env` from `.env.example` when missing, installs backend dependencies with `uv sync` when `backend/.venv` is absent, installs frontend dependencies with `npm install` when `frontend/node_modules` is absent, checks whether today's daily screening data already exists, runs the daily sync batch when it is missing, then starts FastAPI and Vite together.

`DAILY_SYNC_SYMBOLS` controls the symbols used by the startup sync batch. Keep symbols separated by spaces.

Optional ports:

```bash
BACKEND_PORT=8001 FRONTEND_PORT=5174 ./start.sh
```

## Backend

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Run tests:

```bash
cd backend
uv run pytest -v
```

The backend uses an MVC layout:

- `app/models`: SQLAlchemy models and database operations.
- `app/views`: FastAPI route definitions.
- `app/controllers`: API control logic.
- `app/services`: Longbridge access and indicator calculations.

Sync daily screening data for selected symbols:

```bash
cd backend
uv run python -m app.scripts.sync_daily_screening --symbols AAPL.US 700.HK
```

This command pulls static info, market cap, and daily candlesticks, computes Z-Score and reference BOLL metrics, and persists rows used by `GET /api/daily-screenings`.

`GET /api/intraday-screenings` does not depend on the daily metric table. It calls Longbridge screener indicators first, maps the slider filters to screener conditions, runs screener search, then fetches bars for the returned candidates and calculates Z-Score without persistence.

Z-Score uses the current price and the 20 complete trading days before the evaluation day:

```text
Z-Score = (current price - MA20) / SD20
```

SD20 is the population standard deviation of the same 20 closes and therefore includes a square root. When SD20 is zero, Z-Score is defined as zero. Daily and intraday results include the inclusive thresholds `Z-Score >= 1.5` and `Z-Score <= -1.5`. BOLL rails remain visible as reference values but do not gate results.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Production build:

```bash
cd frontend
npm run build
```

The frontend sends an `X-Request-ID` header with every API request. The backend writes request and response traces to `request_logs`.

## API Parameters

Daily:

```http
GET /api/daily-screenings?market=all&min_market_cap=200000000000&min_avg_volume=10000000&page=1&page_size=50
```

Intraday:

```http
GET /api/intraday-screenings?market=all&min_market_cap=200000000000&min_avg_volume=10000000&interval=5m&page=1&page_size=50
```

Message push settings:

```http
GET /api/message-push-settings

PUT /api/message-push-settings
Content-Type: application/json

{
  "interval_minutes": 30,
  "min_market_cap": 250000000000,
  "min_avg_volume": 12000000
}
```

## Out Of Scope For V1

- Long/short availability checks.
- Trading/order placement.
- Manual review status.
- Right-side detail panel or charts.
- Realtime streaming/WebSocket.
- Intraday persistence.
- User accounts.
- Backtesting.
