# Technical Stock Indicators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MA20 direction, ATR14, previous 10-day high/low, reversal trend, and entry suitability to both daily and intraday stock-screening results.

**Architecture:** A pure indicator function will calculate all new fields from ordered daily OHLC bars while strictly excluding the evaluation day. Daily synchronization persists the result; intraday screening fetches fresh Longbridge daily bars and quotes on every request and calculates the same fields in memory. Existing BOLL crossing signals remain unchanged.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, SQLite, pytest, React 19, TypeScript, Vite

## Global Constraints

- All historical windows use trading-day order, never natural-day subtraction.
- MA20, BOLL, ATR14, and previous 10-day high/low exclude the evaluation day in both channels.
- Daily uses the evaluation day's close as current price; intraday uses Longbridge's current real-time price.
- Intraday fetches fresh Longbridge daily bars and real-time quotes on every request and never reads persisted daily metrics for the new calculations.
- `atr14` is displayed to two decimal places.
- Missing required history makes all six new fields `null`; the UI renders each as `-`.
- Existing `upper_breakout` and `lower_breakdown` crossing semantics are not changed.
- Do not add new query filters in this iteration.

---

## File Map

- `backend/app/services/indicator_service.py`: pure technical-indicator calculations and long/short decisions.
- `backend/tests/test_indicator_service.py`: formula, boundary, exclusion, and insufficient-history tests.
- `backend/app/models/stock_metric.py`: persisted daily fields.
- `backend/app/db.py`: additive SQLite schema compatibility for existing databases.
- `backend/tests/test_config.py`: schema-upgrade coverage.
- `backend/app/services/daily_sync_service.py`: compute and persist daily values.
- `backend/tests/test_daily_sync_service.py`: daily integration and upsert tests.
- `backend/app/services/screening_service.py`: expose daily fields and calculate intraday fields from fresh data.
- `backend/tests/test_api.py`: API contract and intraday data-source tests.
- `frontend/src/api.ts`: nullable response types.
- `frontend/src/App.tsx`: six result columns and formatting.

### Task 1: Pure Historical Indicator Calculator

**Files:**
- Modify: `backend/app/services/indicator_service.py`
- Test: `backend/tests/test_indicator_service.py`

**Interfaces:**
- Consumes: `DailyPriceBar(trade_date: date, high: float, low: float, close: float)` values and `current_price: float`.
- Produces: `calculate_historical_setup(bars, current_price, boll_period=20, boll_std_multiplier=2) -> HistoricalSetup`.
- Produces `HistoricalSetup` fields: `ma20_direction`, `atr14`, `previous_10d_low`, `previous_10d_high`, `boll_mid`, `boll_upper`, `boll_lower`, `has_reversal_trend`, `is_suitable_for_entry`; every field is nullable as one all-or-nothing result.

- [ ] **Step 1: Write failing tests for trading-day windows**

Add fixtures with 26 sequential `DailyPriceBar` values and assert that `calculate_historical_setup(bars[:-1], current_price=bars[-1].close)`:

```python
assert result.ma20_direction == "上升"
assert result.previous_10d_low == min(bar.low for bar in bars[-11:-1])
assert result.previous_10d_high == max(bar.high for bar in bars[-11:-1])
```

Mutate the evaluation-day bar to an extreme high, low, and close and assert none of the historical values changes. Add descending closes and constant closes to assert `下降` and `需人工判断`.

- [ ] **Step 2: Run the MA/high-low tests and verify failure**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_indicator_service.py -v
```

Expected: FAIL because `DailyPriceBar` and `calculate_historical_setup` do not exist.

- [ ] **Step 3: Add failing TR and ATR tests**

Test the three standard TR branches:

```python
assert calculate_true_range(high=12, low=9, previous_close=10) == 3
assert calculate_true_range(high=15, low=14, previous_close=10) == 5
assert calculate_true_range(high=9, low=7, previous_close=12) == 5
```

Build 15 historical bars and assert ATR14 equals the mean of the final 14 TR values, including the extra previous close needed for the first TR.

- [ ] **Step 4: Implement immutable result and calculation functions**

Add:

```python
@dataclass(frozen=True)
class DailyPriceBar:
    trade_date: date
    high: float
    low: float
    close: float

@dataclass(frozen=True)
class HistoricalSetup:
    ma20_direction: str | None
    atr14: float | None
    previous_10d_low: float | None
    previous_10d_high: float | None
    boll_mid: float | None
    boll_upper: float | None
    boll_lower: float | None
    has_reversal_trend: str | None
    is_suitable_for_entry: str | None
```

Normalize bars by sorting and deduplicating on `trade_date`. Return an all-`None` result when fewer than 25 valid historical bars remain. Calculate current MA20 from `bars[-20:]` and comparison MA20 from `bars[-25:-5]`. Calculate BOLL from `bars[-20:]`, ATR14 from TR values for `bars[-14:]` using `bars[-15].close`, and high/low from `bars[-10:]`.

- [ ] **Step 5: Add failing decision-boundary tests**

Cover:

```python
# long reversal
current_price <= boll_lower
current_price < previous_10d_low - 0.25 * atr14

# short reversal
current_price >= boll_upper
current_price > previous_10d_high + 0.25 * atr14
```

Assert equality with a BOLL rail counts as a hit, equality with the ATR-adjusted high/low threshold does not count as reversal, and a non-reversal rail hit in the matching MA direction sets `is_suitable_for_entry == "是"`.

- [ ] **Step 6: Implement decision logic and run tests**

Use exact Chinese API values `上升`, `下降`, `需人工判断`, `是`, and `否`. A flat MA returns `需人工判断` and both decision fields return `否`.

Run the indicator test file and expect all tests to pass.

- [ ] **Step 7: Commit the pure calculator**

```bash
git add backend/app/services/indicator_service.py backend/tests/test_indicator_service.py
git commit -m "feat: calculate historical stock setup indicators"
```

### Task 2: Daily Persistence and Schema Compatibility

**Files:**
- Modify: `backend/app/models/stock_metric.py`
- Modify: `backend/app/db.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: nullable SQL values produced by daily synchronization.
- Produces: `StockMetricDaily.ma20_direction`, `.atr14`, `.previous_10d_low`, `.previous_10d_high`, `.has_reversal_trend`, `.is_suitable_for_entry`.

- [ ] **Step 1: Write failing model and schema-upgrade tests**

Extend the model construction test with all six values. Add a `_ensure_schema` test that creates the old `stock_metrics_daily` table, calls `init_db(engine)`, and asserts all six columns exist using SQLAlchemy inspection.

- [ ] **Step 2: Run targeted tests and verify failure**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_models.py tests/test_config.py -v
```

Expected: FAIL because the model and compatibility migration do not define the columns.

- [ ] **Step 3: Add nullable model columns**

Use `String` for the three textual results and `Numeric` for ATR/high/low:

```python
ma20_direction: Mapped[str | None] = mapped_column(String)
atr14: Mapped[Decimal | None] = mapped_column(Numeric)
previous_10d_low: Mapped[Decimal | None] = mapped_column(Numeric)
previous_10d_high: Mapped[Decimal | None] = mapped_column(Numeric)
has_reversal_trend: Mapped[str | None] = mapped_column(String)
is_suitable_for_entry: Mapped[str | None] = mapped_column(String)
```

- [ ] **Step 4: Add idempotent additive schema updates**

Extend `_ensure_schema` to inspect `stock_metrics_daily` and execute one `ALTER TABLE ... ADD COLUMN` for each absent column. Use `NUMERIC` and `VARCHAR` types; never rebuild or drop the table.

- [ ] **Step 5: Run targeted tests and commit**

Expect model and config tests to pass.

```bash
git add backend/app/models/stock_metric.py backend/app/db.py backend/tests/test_models.py backend/tests/test_config.py
git commit -m "feat: persist daily technical setup fields"
```

### Task 3: Daily Synchronization and Daily API

**Files:**
- Modify: `backend/app/services/daily_sync_service.py`
- Modify: `backend/app/services/screening_service.py`
- Modify: `backend/tests/test_daily_sync_service.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `calculate_historical_setup(history_bars, current_price)`.
- Produces: daily database values and six nullable JSON fields.

- [ ] **Step 1: Expand the daily fake data and write failing persistence assertions**

Make `FakeLongbridge.get_daily_bars` return at least 31 unique, ordered dates. Assert the latest day is used only as `current_price`, while the prior bars produce expected MA direction, ATR, and high/low values. Assert all six fields are persisted.

- [ ] **Step 2: Run the daily sync test and verify failure**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_daily_sync_service.py -v
```

- [ ] **Step 3: Integrate the calculator into `_build_metric`**

Convert `bars[:-1]` to `DailyPriceBar` values and call:

```python
setup = calculate_historical_setup(
    historical_bars,
    current_price=bars[-1].close,
    boll_period=boll_period,
    boll_std_multiplier=float(boll_std_multiplier),
)
```

Persist setup fields as `Decimal(str(value))` for numeric results. Preserve existing signal calculation unchanged. Add all six names to `_upsert_metric` so reruns update them.

- [ ] **Step 4: Add and run an upsert regression test**

Synchronize once, change fake prices, synchronize the same trade date again, and assert the existing row is updated rather than duplicated.

- [ ] **Step 5: Add failing daily API assertions**

Seed all six fields and assert the JSON row contains:

```python
assert row["ma20_direction"] == "上升"
assert row["atr14"] == 2.5
assert row["previous_10d_low"] == 100
assert row["previous_10d_high"] == 120
assert row["has_reversal_trend"] == "否"
assert row["is_suitable_for_entry"] == "是"
```

Also seed `None` values and assert each is JSON `null`.

- [ ] **Step 6: Expose fields in `_metric_row`**

Convert nullable numeric database fields through `_to_float`; pass text fields through unchanged.

- [ ] **Step 7: Run daily integration tests and commit**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_daily_sync_service.py tests/test_api.py -v
git add app/services/daily_sync_service.py app/services/screening_service.py tests/test_daily_sync_service.py tests/test_api.py
git commit -m "feat: add setup fields to daily screening"
```

### Task 4: Fresh Intraday Calculation

**Files:**
- Modify: `backend/app/services/screening_service.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: fresh `get_daily_bars(..., count=30)`, `get_latest_quotes`, and `calculate_historical_setup`.
- Produces: six nullable fields in each intraday row.

- [ ] **Step 1: Write a failing intraday exclusion/data-source test**

Create a fake provider returning 26 completed daily bars plus an extreme bar whose date equals the latest quote's market date. Assert:

- `get_daily_bars` is called on every separate API request;
- the same-day bar does not affect MA20, BOLL, ATR14, or high/low;
- real-time price does affect reversal/entry decisions;
- no `StockMetricDaily` seed is required.

- [ ] **Step 2: Run the targeted test and verify failure**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_api.py -k intraday -v
```

- [ ] **Step 3: Normalize intraday historical bars**

For each security, determine the evaluation market date from the latest quote timestamp. Convert US timestamps with `ZoneInfo("America/New_York")` and HK timestamps with `ZoneInfo("Asia/Hong_Kong")`; add a focused helper such as `_market_date(value: datetime, market: str) -> date`. Convert each daily bar timestamp through the same market timezone and exclude bars whose market date is on or after the evaluation date. Pass only prior complete daily bars to `calculate_historical_setup`.

- [ ] **Step 4: Preserve existing signal behavior**

Continue to calculate and filter existing `signal_type` exactly as before. Use the newly calculated historical BOLL values for the current rail, but do not replace crossing rules with simple rail-position rules. Add setup fields to the response independently.

- [ ] **Step 5: Run all intraday API tests and commit**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_api.py -k intraday -v
git add app/services/screening_service.py tests/test_api.py
git commit -m "feat: calculate intraday setup from fresh market data"
```

### Task 5: Frontend Result Columns

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: six nullable JSON fields.
- Produces: six table columns in both tabs with `-` null rendering.

- [ ] **Step 1: Extend the TypeScript contract**

Add:

```typescript
ma20_direction: "上升" | "下降" | "需人工判断" | null;
atr14: number | null;
previous_10d_low: number | null;
previous_10d_high: number | null;
has_reversal_trend: "是" | "否" | null;
is_suitable_for_entry: "是" | "否" | null;
```

- [ ] **Step 2: Add headers and cells**

Add the six headers in the specified order. Render nullable text using `value ?? "-"`, ATR with a dedicated two-decimal formatter, and nullable high/low with a price formatter that returns `-` for `null`.

- [ ] **Step 3: Correct empty-row column spans**

Increase both daily and intraday `emptyColSpan` values by six so loading and empty messages span the full table.

- [ ] **Step 4: Build and fix type errors**

```bash
cd frontend
npm run build
```

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 5: Commit the frontend**

```bash
git add frontend/src/api.ts frontend/src/App.tsx
git commit -m "feat: display technical setup fields"
```

### Task 6: Full Verification

**Files:**
- Verify only; modify a failing file only when the failure is caused by this feature.

**Interfaces:**
- Consumes: completed backend and frontend implementation.
- Produces: passing automated test/build evidence.

- [ ] **Step 1: Run the complete backend suite**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging -v
```

Expected: all tests pass.

- [ ] **Step 2: Run the production frontend build**

```bash
cd frontend
npm run build
```

Expected: `tsc -b` and Vite build pass.

- [ ] **Step 3: Inspect the final diff and schema safety**

```bash
git diff main...HEAD --check
git status --short
```

Confirm there are no whitespace errors, generated build artifacts, credentials, unrelated refactors, destructive migrations, or changes to existing BOLL signal semantics.

- [ ] **Step 4: Commit any verification-only corrections**

If verification required scoped corrections, commit only those files:

```bash
git status --short
git add backend/app/services/indicator_service.py backend/app/services/daily_sync_service.py backend/app/services/screening_service.py frontend/src/api.ts frontend/src/App.tsx
git commit -m "fix: address technical indicator verification"
```

Omit unchanged paths from the `git add` command after inspecting `git status --short`.
