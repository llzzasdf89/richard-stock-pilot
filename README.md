# Richard Stock Pilot

Richard Stock Pilot is a React + FastAPI stock screening app for US and HK stocks. The first version focuses on Bollinger Band breakout/breakdown screening with configurable market cap and average monthly volume filters.

## Current Scope

- Daily screening: reads stored daily metrics from SQLite.
- Intraday screening: discovers Longbridge screener indicators, runs screener search with the slider filters, then fetches daily and intraday bars for local Bollinger calculations.
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
DAILY_SYNC_SYMBOLS="AAPL.US 700.HK"
DAILY_SYNC_BAR_COUNT=60
VITE_API_BASE=
```

`VITE_API_BASE` may stay empty in local development because Vite proxies `/api` to the backend. Set it to the backend URL when deploying the frontend separately.

Existing shell environment values take priority, so production deployments can still inject secrets without changing files. When credentials are available, `LongbridgeService` uses the official `longbridge` Python SDK. Without credentials, it falls back to deterministic mock data so local development still runs.

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

Sync daily screening data for selected symbols:

```bash
cd backend
uv run python -m app.scripts.sync_daily_screening --symbols AAPL.US 700.HK
```

This command pulls static info, market cap, and daily candlesticks, computes BOLL metrics, and persists rows used by `GET /api/daily-screenings`.

`GET /api/intraday-screenings` does not depend on the daily metric table. It calls Longbridge screener indicators first, maps the slider filters to screener conditions, runs screener search, then fetches bars for the returned candidates and calculates intraday BOLL signals without persistence.

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
