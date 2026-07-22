# Richard Stock Pilot Design

## Goal

Build a web application that helps screen US and HK stocks that break above or below Bollinger Bands. The first version focuses on a clean screening table, configurable filters, and reliable request tracing.

The application does not include automatic trading, long/short availability checks, manual review status, live charts, or right-side detail panels in the first version.

## Architecture

The application uses a React frontend and a Python FastAPI backend.

Frontend responsibilities:

- Render a polished stock screening workspace.
- Display all user-facing interface text in Chinese.
- Provide tabs for daily and intraday screening.
- Provide filters for market, signal type, market cap, and average monthly volume.
- Generate an `X-Request-ID` for every API request.
- Refresh the table when daily filters change.
- Refresh intraday data only when the user clicks the refresh button.

Backend responsibilities:

- Expose two REST-style GET APIs.
- Use MVC structure for route, controller, and model boundaries.
- Pull market data from Longbridge.
- Store daily bars and daily computed metrics.
- Compute intraday signals in memory without storing intraday bars.
- Store request logs for troubleshooting.
- Return a unified response body for all API responses.

## Backend MVC Structure

```text
backend/
├─ app/
│  ├─ main.py
│  ├─ config.py
│  ├─ db.py
│  ├─ models/
│  │  ├─ stock.py
│  │  ├─ daily_bar.py
│  │  ├─ stock_metric.py
│  │  ├─ screening_run.py
│  │  └─ request_log.py
│  ├─ views/
│  │  ├─ daily_screening_view.py
│  │  └─ intraday_screening_view.py
│  ├─ controllers/
│  │  ├─ daily_screening_controller.py
│  │  └─ intraday_screening_controller.py
│  └─ services/
│     ├─ longbridge_service.py
│     ├─ indicator_service.py
│     └─ screening_service.py
└─ tests/
```

`models/` contains SQLAlchemy models and database operations.

`views/` contains FastAPI route definitions and request parameter binding.

`controllers/` contains API control logic and coordinates models and services.

`services/` contains Longbridge access, Bollinger Band calculation, and screening routines. This keeps controllers readable while preserving the MVC shape.

## Frontend Design

The first screen is the actual screening workspace, not a landing page.

Layout:

- Compact top header with the product name and latest data timestamp.
- Two tabs: `日线筛选` and `分时筛选`.
- Filter toolbar with market, signal type, market cap slider, and average monthly volume slider.
- Full-width results table.
- No right-side chart or detail panel in the first version.

All user-facing UI labels, table headers, empty states, loading text, errors, and button text are displayed in Chinese. API field names stay in English.

Primary Chinese labels:

- Market filter: `全部`, `美股`, `港股`.
- Signal filter: `全部`, `上穿 BOLL`, `下击 BOLL`.
- Market cap filter: `最低市值`.
- Average volume filter: `最低月均成交量`.
- Intraday refresh button: `刷新分时数据`.
- Daily tab: `日线筛选`.
- Intraday tab: `分时筛选`.
- Table headers: `代码`, `名称`, `市场`, `货币`, `信号`, `收盘价`, `最新价`, `市值`, `月均成交量`, `BOLL 上轨`, `BOLL 中轨`, `BOLL 下轨`, `突破幅度`, `数据时间`.

Filters:

- `market`: all, US, HK.
- `signal_type`: all, upper_breakout, lower_breakdown.
- `min_market_cap`: default 200,000,000,000 in local currency.
- `min_avg_volume`: default 10,000,000.
- Pagination uses `page` and `page_size`.

Daily tab behavior:

- Filter changes call the daily screening API.
- Slider changes are debounced by roughly 300-500ms.
- The backend reads precomputed daily metrics from the database.

Intraday tab behavior:

- Filter changes update local state.
- The table refreshes only when the user clicks the refresh button.
- The backend pulls intraday data, computes signals in memory, and returns results.

## APIs

The first version exposes only two application APIs.

### Daily Screenings

```http
GET /api/daily-screenings
```

Query parameters:

```text
market=all|US|HK
signal_type=all|upper_breakout|lower_breakdown
min_market_cap=200000000000
min_avg_volume=10000000
page=1
page_size=50
```

Behavior:

- Query `stock_metrics_daily` joined with `stocks`.
- Apply market, signal type, market cap, average volume, and pagination filters.
- Return daily Bollinger Band screening rows.
- Do not call Longbridge from this endpoint during normal filtering.

### Intraday Screenings

```http
GET /api/intraday-screenings
```

Query parameters:

```text
market=all|US|HK
signal_type=all|upper_breakout|lower_breakdown
min_market_cap=200000000000
min_avg_volume=10000000
interval=5m
page=1
page_size=50
```

Behavior:

- Use daily stored metrics to narrow the candidate universe by market cap and average volume.
- Pull current intraday bars from Longbridge for candidates.
- Compute Bollinger Band signals in memory.
- Return matching rows.
- Do not store intraday bars, intraday metrics, or intraday screening results.

## Unified Response Format

Every API response uses HTTP status code `200`. Business success or failure is represented by the response body.

Success:

```json
{
  "success": true,
  "data": {},
  "code": 200
}
```

Internal server failure:

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

Detailed exception messages and stack traces are not exposed to the frontend. They are stored in backend logs.

## Request Logging

The frontend sends `X-Request-ID` on every API request. If it is missing, the backend generates one.

The backend returns the same request ID in the response header.

Middleware records:

- Request ID.
- Client IP.
- HTTP method.
- Path.
- Query parameters.
- Request body.
- Response status from the unified body.
- Response body.
- Duration in milliseconds.
- User agent.
- Error message, if any.
- Created timestamp.

Sensitive headers and secrets are not stored.

## Data Model

The first version uses five tables.

### `stocks`

Stores stock identity and basic metadata.

```text
id                 integer primary key
symbol             text not null unique
name               text not null
market             text not null        -- US / HK
currency           text not null        -- USD / HKD
exchange           text
lot_size           integer
status             text                 -- active / inactive / unknown
created_at         datetime not null
updated_at         datetime not null
```

### `daily_bars`

Stores daily OHLCV bars.

```text
id                 integer primary key
stock_id           integer not null references stocks(id)
trade_date         date not null
open               numeric not null
high               numeric not null
low                numeric not null
close              numeric not null
volume             integer not null
turnover           numeric
created_at         datetime not null
updated_at         datetime not null
```

Constraints and indexes:

```text
unique(stock_id, trade_date)
index(stock_id, trade_date)
```

### `stock_metrics_daily`

Stores daily computed metrics and daily Bollinger Band signal snapshots.

```text
id                  integer primary key
stock_id            integer not null references stocks(id)
trade_date          date not null
close               numeric not null
market_cap          numeric not null
avg_volume_1m       numeric not null
boll_period         integer not null
boll_std_multiplier numeric not null
boll_mid            numeric not null
boll_upper          numeric not null
boll_lower          numeric not null
prev_close          numeric
prev_boll_upper     numeric
prev_boll_lower     numeric
signal_type         text not null        -- upper_breakout / lower_breakdown / none
break_percent       numeric
created_at          datetime not null
updated_at          datetime not null
```

Constraints and indexes:

```text
unique(stock_id, trade_date, boll_period, boll_std_multiplier)
index(trade_date, signal_type)
index(market_cap)
index(avg_volume_1m)
```

### `screening_runs`

Stores daily screening job history.

```text
id                  integer primary key
run_date            date not null
status              text not null        -- running / success / failed
markets             text not null        -- US,HK
boll_period         integer not null
boll_std_multiplier numeric not null
started_at          datetime not null
finished_at         datetime
stock_count         integer default 0
metrics_count       integer default 0
signal_count        integer default 0
error_message       text
created_at          datetime not null
updated_at          datetime not null
```

### `request_logs`

Stores API request and response traces.

```text
id                  integer primary key
request_id          text not null
client_ip           text
method              text not null
path                text not null
query_params        text
request_body        text
response_status     integer
response_body       text
duration_ms         integer
user_agent          text
error_message       text
created_at          datetime not null
```

Indexes:

```text
index(request_id)
index(created_at)
index(path)
index(response_status)
```

## Signal Rules

Default Bollinger Band parameters:

```text
period = 20
std_multiplier = 2
```

Daily upper breakout:

```text
prev_close <= prev_boll_upper
current_close > current_boll_upper
```

Daily lower breakdown:

```text
prev_close >= prev_boll_lower
current_close < current_boll_lower
```

Intraday uses the same signal definition on the selected intraday interval. The first version defaults to `5m`.

Break percent:

```text
upper_breakout: (close - boll_upper) / boll_upper
lower_breakdown: (boll_lower - close) / boll_lower
```

## Out of Scope

The first version does not include:

- Long/short availability checks.
- IBKR integration.
- Trading or order placement.
- Manual review status.
- Right-side detail panel.
- Realtime charts.
- WebSocket streaming.
- Intraday persistence.
- User accounts.
- Backtesting.

## Open Implementation Notes

- Longbridge is the primary market data provider.
- Daily metrics are stored so frontend filters are fast.
- Intraday data is intentionally treated as transient.
- The backend should use clear defaults but accept frontend query parameters for market cap, average volume, signal type, market, page, and page size.
