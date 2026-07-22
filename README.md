# Richard Stock Pilot

Richard Stock Pilot is a React + FastAPI stock screening app for US and HK stocks. The first version focuses on Bollinger Band breakout/breakdown screening with configurable market cap and average monthly volume filters.

## Current Scope

- Daily screening: reads stored daily metrics from SQLite.
- Intraday screening: fetches intraday data on request and computes Bollinger signals in memory.
- Chinese UI.
- Two application APIs:
  - `GET /api/daily-screenings`
  - `GET /api/intraday-screenings`
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

## Backend

```bash
cd backend
uv run uvicorn app.main:app --reload
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

Longbridge credentials are read from environment variables supported by the official SDK:

```bash
export LONGBRIDGE_APP_KEY="your app key"
export LONGBRIDGE_APP_SECRET="your app secret"
export LONGBRIDGE_ACCESS_TOKEN="your access token"
```

For mainland China routing, set:

```bash
export LONGBRIDGE_REGION="cn"
```

When credentials are available, `LongbridgeService` uses the official `longbridge` Python SDK. Without credentials, it falls back to deterministic mock data so local development still runs.

Sync daily screening data for selected symbols:

```bash
cd backend
uv run python -m app.scripts.sync_daily_screening --symbols AAPL.US 700.HK
```

This command pulls static info, market cap, and daily candlesticks, computes BOLL metrics, and persists rows used by `GET /api/daily-screenings`.

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
GET /api/daily-screenings?market=all&signal_type=all&min_market_cap=200000000000&min_avg_volume=10000000&page=1&page_size=50
```

Intraday:

```http
GET /api/intraday-screenings?market=all&signal_type=all&min_market_cap=200000000000&min_avg_volume=10000000&interval=5m&page=1&page_size=50
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
