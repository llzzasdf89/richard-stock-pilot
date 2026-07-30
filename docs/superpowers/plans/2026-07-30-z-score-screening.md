# Z-Score Stock Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared Z-Score indicator and make daily, intraday, and message-push opportunity selection use inclusive ±1.5 Z thresholds instead of BOLL crossings.

**Architecture:** Extend the pure historical setup calculator so every consumer receives the same Z-Score, reversal, and entry decisions. Persist daily Z-Score, compute intraday and push values from real-time prices, filter API results server-side, and remove the obsolete signal control and column from the UI while retaining BOLL values as reference data.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, SQLite, pytest, React 19, TypeScript 5.9, Vite 7

## Global Constraints

- MA20 and SD20 use the same 20 complete trading days before the evaluation day.
- SD20 is the population standard deviation and Z-Score is `(current_price - MA20) / SD20`.
- When SD20 is zero, Z-Score is exactly `0`.
- Daily uses the evaluation-day close; intraday and message push use the latest real-time price.
- Daily and intraday results include only `z_score >= 1.5` or `z_score <= -1.5`, including equality.
- Reversal and entry decisions use Z thresholds instead of BOLL positions.
- BOLL rails remain available as reference data; existing database signal columns are not dropped.
- API and frontend no longer expose a signal filter or result signal field.
- Message push uses the shared decision, has no BOLL second gate, and displays Z-Score instead of BOLL break percent.

---

## File Map

- `backend/app/services/indicator_service.py`: calculate SD20, Z-Score, reversal, and entry decisions.
- `backend/tests/test_indicator_service.py`: formula, zero-deviation, threshold, and BOLL-independence tests.
- `backend/app/models/stock_metric.py`: persist nullable daily `z_score`.
- `backend/app/db.py`: add `z_score` to existing SQLite databases.
- `backend/app/services/daily_sync_service.py`: save and update daily Z-Score.
- `backend/app/services/screening_service.py`: expose/filter daily Z values and calculate/filter intraday Z values.
- `backend/app/controllers/*_screening_controller.py`: remove `signal_type` from service interfaces.
- `backend/app/views/*_screening_view.py`: remove the API query parameter.
- `backend/tests/test_models.py`, `backend/tests/test_config.py`, `backend/tests/test_daily_sync_service.py`, `backend/tests/test_api.py`: persistence and API contracts.
- `backend/app/services/message_push_scan_service.py`: derive direction from Z and include it in push content.
- `backend/tests/test_message_push_scan_service.py`: push-direction and content regressions.
- `frontend/src/api.ts`: remove signal types/parameters and add `z_score`.
- `frontend/src/App.tsx`: remove signal controls/column and render Z-Score.
- `README.md`: describe Z-Score screening rather than BOLL-signal screening.

### Task 1: Shared Z-Score and Decision Logic

**Files:**
- Modify: `backend/tests/test_indicator_service.py`
- Modify: `backend/app/services/indicator_service.py`

**Interfaces:**
- Consumes: `calculate_historical_setup(bars: list[DailyPriceBar], current_price: float, boll_period: int = 20, boll_std_multiplier: float = 2)`.
- Produces: `HistoricalSetup.z_score: float | None`, plus reversal and entry fields based on inclusive ±1.5 thresholds.

- [ ] **Step 1: Write failing formula and zero-deviation tests**

Add tests with hand-derived values:

```python
def test_historical_setup_calculates_population_z_score():
    bars = _daily_bars([float(value) for value in range(1, 26)])
    result = calculate_historical_setup(bars, current_price=30)
    expected_ma = 15.5
    expected_sd = (665 / 20) ** 0.5
    assert result.z_score == pytest.approx((30 - expected_ma) / expected_sd)


def test_historical_setup_returns_zero_z_score_when_sd20_is_zero():
    result = calculate_historical_setup(_daily_bars([100.0] * 25), current_price=120)
    assert result.z_score == 0
```

Import `pytest`. These tests catch omission of the square root, sample-deviation division, inclusion of the wrong trading days, and divide-by-zero behavior.

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_indicator_service.py -k "population_z_score or zero_z_score" -v
```

Expected: FAIL because `HistoricalSetup` has no `z_score`.

- [ ] **Step 3: Implement Z-Score minimally**

Add `z_score: float | None` to `HistoricalSetup` and `_empty_historical_setup`. After calculating the current 20-close window:

```python
variance = sum((close - current_ma20) ** 2 for close in closes[-20:]) / 20
sd20 = sqrt(variance)
z_score = 0.0 if sd20 == 0 else (current_price - current_ma20) / sd20
```

Return `z_score` in the populated result.

- [ ] **Step 4: Run the formula tests and verify GREEN**

Run the command from Step 2 and expect both tests to pass.

- [ ] **Step 5: Write failing decision-boundary tests**

Add explicit tests proving:

```python
assert calculate_historical_setup(up_bars, price_for_z_minus_1_5).is_suitable_for_entry == "是"
assert calculate_historical_setup(down_bars, price_for_z_plus_1_5).is_suitable_for_entry == "是"
```

Use `price_for_z_minus_1_5 = ma20 - 1.5 * sd20` and `price_for_z_plus_1_5 = ma20 + 1.5 * sd20`, where `ma20` and `sd20` are hand-derived from the literal fixture. Add BOLL-independence cases where the price satisfies the Z threshold without reaching the relevant BOLL rail. Preserve strict ATR reversal thresholds and assert reversal prices yield `"是"` while the matching entry field yields `"否"`.

- [ ] **Step 6: Run decision tests and verify RED**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_indicator_service.py -k "z_threshold or without_boll" -v
```

Expected: FAIL because decisions still depend on BOLL rails.

- [ ] **Step 7: Replace BOLL gates with Z gates**

Use:

```python
long_z_extreme = z_score <= -1.5
short_z_extreme = z_score >= 1.5
```

Apply these to both reversal and suitable-entry branches. Keep MA direction and ATR-adjusted high/low comparisons unchanged.

- [ ] **Step 8: Run the complete indicator tests**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_indicator_service.py -v
```

Update obsolete tests that explicitly encode BOLL as a decision gate so they assert the new Z behavior. Expect all tests to pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/indicator_service.py backend/tests/test_indicator_service.py
git commit -m "feat: calculate Z-Score stock setup"
```

### Task 2: Daily Persistence and Z-Score Filtering

**Files:**
- Modify: `backend/tests/test_models.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_daily_sync_service.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/app/models/stock_metric.py`
- Modify: `backend/app/db.py`
- Modify: `backend/app/services/daily_sync_service.py`
- Modify: `backend/app/services/screening_service.py`
- Modify: `backend/app/controllers/daily_screening_controller.py`
- Modify: `backend/app/views/daily_screening_view.py`

**Interfaces:**
- Consumes: `HistoricalSetup.z_score`.
- Produces: persisted `StockMetricDaily.z_score: Decimal | None`; daily endpoint without `signal_type`, returning only inclusive ±1.5 rows.

- [ ] **Step 1: Write failing model and schema tests**

Extend model construction to assert `StockMetricDaily(z_score=Decimal("-1.75"), ...)`. Extend the existing old-schema compatibility test so SQLAlchemy inspection contains `"z_score"` after `init_db(engine)`.

- [ ] **Step 2: Run persistence-contract tests and verify RED**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_models.py tests/test_config.py -v
```

Expected: FAIL because the model and compatibility additions lack `z_score`.

- [ ] **Step 3: Add the nullable database field**

Add:

```python
z_score: Mapped[Decimal | None] = mapped_column(Numeric)
```

Add `"z_score": "NUMERIC"` to `_ensure_schema` additions.

- [ ] **Step 4: Add failing daily sync and API tests**

Assert `_build_metric` persists the calculator’s Z value and `_upsert_metric` updates it. Seed three latest-date rows with Z values `1.5`, `-1.5`, and `1.49`, all with `signal_type="none"`, then call the daily endpoint without `signal_type`; assert only the first two rows return and each includes numeric `z_score`.

- [ ] **Step 5: Run daily integration tests and verify RED**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_daily_sync_service.py tests/test_api.py -k "daily" -v
```

Expected: FAIL because Z is neither saved nor used for filtering and the API still declares the signal parameter.

- [ ] **Step 6: Persist, expose, and filter Z-Score**

In `_build_metric`, set `z_score=_decimal_or_none(setup.z_score)` and include `"z_score"` in `_upsert_metric`. Add `"z_score": _to_float(metric.z_score)` to `_metric_row`.

Replace the daily signal predicates with:

```python
or_(
    StockMetricDaily.z_score >= Decimal("1.5"),
    StockMetricDaily.z_score <= Decimal("-1.5"),
)
```

Remove `signal_type` from `_apply_filters`, `get_daily_screenings`, the controller, and the view. Remove response `signal_type` and `break_percent` from `_metric_row` because they are no longer part of the frontend contract; retain database fields.

- [ ] **Step 7: Run daily tests and commit**

Run the model, config, daily sync, and daily API tests. Expect all to pass.

```bash
git add backend/app/models/stock_metric.py backend/app/db.py \
  backend/app/services/daily_sync_service.py backend/app/services/screening_service.py \
  backend/app/controllers/daily_screening_controller.py backend/app/views/daily_screening_view.py \
  backend/tests/test_models.py backend/tests/test_config.py \
  backend/tests/test_daily_sync_service.py backend/tests/test_api.py
git commit -m "feat: filter daily stocks by Z-Score"
```

### Task 3: Intraday Z-Score Selection and API Cleanup

**Files:**
- Modify: `backend/tests/test_api.py`
- Modify: `backend/app/services/screening_service.py`
- Modify: `backend/app/controllers/intraday_screening_controller.py`
- Modify: `backend/app/views/intraday_screening_view.py`

**Interfaces:**
- Consumes: real-time `latest_price` and `HistoricalSetup.z_score`.
- Produces: intraday endpoint without `signal_type`, returning rows only when `abs(z_score) >= 1.5`.

- [ ] **Step 1: Write failing intraday behavior tests**

Create complete provider fixtures where:

- one stock has `z_score == 1.5` but no BOLL crossing;
- one has `z_score == -1.5` but no BOLL crossing;
- one has `abs(z_score) < 1.5`;
- the current-day daily bar is extreme and must be excluded.

Call `/api/intraday-screenings` without `signal_type`. Assert the first two return, the third does not, and returned rows contain `z_score` but no `signal_type` or `break_percent`.

- [ ] **Step 2: Run intraday tests and verify RED**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_api.py -k "intraday" -v
```

Expected: FAIL because BOLL crossings still gate results.

- [ ] **Step 3: Replace the intraday signal gate**

After `setup = calculate_historical_setup(...)`, use:

```python
if setup.z_score is None or -1.5 < setup.z_score < 1.5:
    continue
```

Do not call `detect_boll_signal` or `calculate_break_percent` for row eligibility. Keep BOLL values from `setup.boll_upper`, `setup.boll_mid`, and `setup.boll_lower` as reference output. Add `z_score` and remove `signal_type` and `break_percent` from the row.

Remove `signal_type` from the intraday service, controller, and view signatures.

- [ ] **Step 4: Run API tests and commit**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_api.py -v
```

Expect all API tests to pass.

```bash
git add backend/app/services/screening_service.py \
  backend/app/controllers/intraday_screening_controller.py \
  backend/app/views/intraday_screening_view.py backend/tests/test_api.py
git commit -m "feat: filter intraday stocks by Z-Score"
```

### Task 4: Message Push Uses Shared Z Decisions

**Files:**
- Modify: `backend/tests/test_message_push_scan_service.py`
- Modify: `backend/app/services/message_push_scan_service.py`

**Interfaces:**
- Consumes: `HistoricalSetup.z_score`, `is_suitable_for_entry`, and `has_reversal_trend`.
- Produces: Z-derived `"做多"`/`"做空"` directions and push content containing a two-decimal Z-Score.

- [ ] **Step 1: Write failing direction and content tests**

Construct `HistoricalSetup` fixtures where BOLL position disagrees with the Z direction:

```python
setup = HistoricalSetup(
    ma20_direction="上升",
    z_score=-1.75,
    is_suitable_for_entry="是",
    has_reversal_trend="否",
    ...
)
assert derive_entry_direction(setup) == "做多"
```

Add the symmetric short case. Assert `build_pushplus_message` contains `Z-Score：-1.75` and does not contain `突破幅度`.

- [ ] **Step 2: Run push tests and verify RED**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_message_push_scan_service.py -v
```

Expected: FAIL because direction still checks BOLL and content expects break percent.

- [ ] **Step 3: Remove the BOLL second gate**

Change the interface to:

```python
def derive_entry_direction(setup: HistoricalSetup) -> str | None:
```

Return `"做多"` for suitable, non-reversal, upward MA with `z_score <= -1.5`; return `"做空"` for suitable, non-reversal, downward MA with `z_score >= 1.5`; otherwise return `None`.

Pass `setup.z_score` into the opportunity, remove BOLL-based `boundary` and `break_percent` calculations, and add:

```python
("Z-Score", f"{opportunity['z_score']:.2f}")
```

Retain the three BOLL reference rows.

- [ ] **Step 4: Run push tests and commit**

Run the full push scan test file and expect all tests to pass.

```bash
git add backend/app/services/message_push_scan_service.py \
  backend/tests/test_message_push_scan_service.py
git commit -m "feat: use Z-Score for entry alerts"
```

### Task 5: Frontend Contract and Result Table

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ScreeningRow.z_score: number | null`.
- Produces: requests without `signal_type`, no signal control/column, and a two-decimal Z-Score column.

- [ ] **Step 1: Make the TypeScript contract describe the new API**

Delete `SignalType`, `ScreeningFilters.signal_type`, and `ScreeningRow.signal_type`/`break_percent`. Add:

```typescript
z_score: number | null;
```

Remove `params.set`/constructor data for `signal_type`.

- [ ] **Step 2: Remove obsolete UI and render Z**

Delete `signalOptions`, the signal `SegmentedControl`, `formatSignal`, and signal cell. Add a Z header and:

```tsx
<td className="numeric">{formatZScore(row.z_score)}</td>
```

with:

```typescript
function formatZScore(value: number | null) {
  return value === null ? "-" : value.toFixed(2);
}
```

Remove break-percent display and its formatter if unused. Correct empty `colSpan` after deleting two columns and adding one.

- [ ] **Step 3: Run the frontend build**

```bash
cd frontend
npm run build
```

Expected: TypeScript compilation and Vite build exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts frontend/src/App.tsx
git commit -m "feat: show Z-Score screening results"
```

### Task 6: Documentation and Full Verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: completed backend and frontend behavior.
- Produces: accurate setup/product documentation and fresh verification evidence.

- [ ] **Step 1: Update product documentation**

Replace statements that describe BOLL breakout/breakdown as the result gate with the exact inclusive Z rule. Document the population-SD formula, exclusion of the current trading day, `SD20 = 0 → Z = 0`, and removal of the signal filter. Note that BOLL rails remain reference columns.

- [ ] **Step 2: Run backend verification**

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging -v
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Run frontend verification**

```bash
cd frontend
npm run build
```

Expected: exit 0 with no TypeScript or Vite build errors.

- [ ] **Step 4: Inspect the final diff**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Confirm no whitespace errors, no unrelated user files changed, and every design requirement maps to an implemented diff and test.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md docs/superpowers/plans/2026-07-30-z-score-screening.md
git commit -m "docs: explain Z-Score stock screening"
```
