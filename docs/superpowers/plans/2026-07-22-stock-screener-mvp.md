# Stock Screener MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable React + FastAPI stock screener with Chinese UI, daily screening from stored metrics, intraday screening computed on demand, unified responses, and request logging.

**Architecture:** The backend uses FastAPI with an MVC layout: `views/` define routes, `controllers/` coordinate API behavior, `models/` own SQLAlchemy tables and database operations, and `services/` contain Longbridge access and Bollinger calculations. The frontend is a React/Vite app with two tabs, shared filters, full-width tables, request IDs, and no chart/detail panel.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, Vite, CSS modules/plain CSS.

## Global Constraints

- Use React frontend and Python FastAPI backend.
- Backend follows MVC: Model is database operation layer, View is API route layer, Controller stores actual API behavior.
- Expose only two application APIs: `GET /api/daily-screenings` and `GET /api/intraday-screenings`.
- All user-facing UI labels, table headers, empty states, loading text, errors, and button text are displayed in Chinese. API field names stay in English.
- API response body format is `{ success: boolean, data: any, code: number }`.
- HTTP status code remains `200`, including internal failures where response body uses `success=false` and `code=500`.
- Frontend sends `X-Request-ID` on every request.
- Backend records request logs with IP, request parameters, response body, status, duration, and errors.
- Daily screening uses stored daily metrics; daily `最新价格` is the daily close price.
- Intraday screening pulls data on request, computes in memory, and does not persist intraday data.
- First version excludes long/short availability, trading, manual review status, right-side detail panel, realtime charts, WebSocket streaming, user accounts, and backtesting.

---

### Task 1: Backend Project Skeleton And Indicator Core

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/services/indicator_service.py`
- Create: `backend/tests/test_indicator_service.py`

**Interfaces:**
- Produces: `calculate_bollinger(values: list[float], period: int, std_multiplier: float) -> list[dict[str, float | None]]`
- Produces: `detect_boll_signal(prev_close: float, close: float, prev_upper: float, upper: float, prev_lower: float, lower: float) -> str`
- Produces: `calculate_break_percent(signal_type: str, close: float, upper: float, lower: float) -> float | None`

- [ ] **Step 1: Write failing indicator tests**

Create `backend/tests/test_indicator_service.py` with tests for Bollinger output, upper breakout, lower breakdown, and break percent.

- [ ] **Step 2: Run failing test**

Run: `cd backend && uv run pytest tests/test_indicator_service.py -v`
Expected: FAIL because `app.services.indicator_service` does not exist.

- [ ] **Step 3: Implement indicator service**

Create minimal `backend/pyproject.toml`, package files, and `indicator_service.py`.

- [ ] **Step 4: Run passing test**

Run: `cd backend && uv run pytest tests/test_indicator_service.py -v`
Expected: PASS.

### Task 2: Backend Models And Database Operations

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/stock.py`
- Create: `backend/app/models/daily_bar.py`
- Create: `backend/app/models/stock_metric.py`
- Create: `backend/app/models/screening_run.py`
- Create: `backend/app/models/request_log.py`
- Create: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: SQLAlchemy session from `app.db`.
- Produces: ORM classes `Stock`, `DailyBar`, `StockMetricDaily`, `ScreeningRun`, `RequestLog`.
- Produces: `init_db(engine: Engine | None = None) -> None`

- [ ] **Step 1: Write failing model tests**

Create tests that initialize an in-memory SQLite database, insert a stock, daily metric, and request log, and query them back.

- [ ] **Step 2: Run failing test**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL because database modules do not exist.

- [ ] **Step 3: Implement models**

Implement SQLAlchemy models matching the design spec.

- [ ] **Step 4: Run passing test**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: PASS.

### Task 3: Backend Unified API, Request Logging, And Screening Controllers

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/views/daily_screening_view.py`
- Create: `backend/app/views/intraday_screening_view.py`
- Create: `backend/app/controllers/daily_screening_controller.py`
- Create: `backend/app/controllers/intraday_screening_controller.py`
- Create: `backend/app/services/screening_service.py`
- Create: `backend/app/services/longbridge_service.py`
- Create: `backend/app/response.py`
- Create: `backend/app/middleware.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: ORM models from Task 2.
- Consumes: indicator functions from Task 1.
- Produces: FastAPI app object `app`.
- Produces: `GET /api/daily-screenings`.
- Produces: `GET /api/intraday-screenings`.

- [ ] **Step 1: Write failing API tests**

Create tests that seed daily metrics, call both endpoints with `X-Request-ID`, verify unified response shape, Chinese-agnostic API field names, daily latest price equals close, and request log insertion.

- [ ] **Step 2: Run failing test**

Run: `cd backend && uv run pytest tests/test_api.py -v`
Expected: FAIL because API app does not exist.

- [ ] **Step 3: Implement API and middleware**

Implement app, routes, controllers, response wrapper, request logging middleware, and deterministic mock Longbridge intraday data.

- [ ] **Step 4: Run backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: PASS.

### Task 4: Frontend React UI

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `GET /api/daily-screenings`.
- Consumes: `GET /api/intraday-screenings`.
- Produces: Chinese UI with tabs, filters, slider controls, refresh button, paginated table, and `X-Request-ID`.

- [ ] **Step 1: Create frontend implementation**

Build the React UI according to the spec using static defaults and API calls.

- [ ] **Step 2: Install dependencies**

Run: `cd frontend && npm install`
Expected: dependencies install.

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: PASS.

### Task 5: Repository Integration And Verification

**Files:**
- Create: `.gitignore`
- Create: `README.md`

**Interfaces:**
- Consumes: backend and frontend tasks.
- Produces: documented local startup commands and final verification.

- [ ] **Step 1: Add repository docs and ignores**

Document backend and frontend setup, environment variables, API response shape, and request ID behavior.

- [ ] **Step 2: Run backend tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Check git status**

Run: `git status --short`
Expected: only intended implementation files are changed.
