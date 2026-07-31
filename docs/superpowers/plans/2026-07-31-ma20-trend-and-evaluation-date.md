# MA20 Trend and Evaluation Date Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize the five-trading-day MA20 change by ATR14 and make live historical windows use the query-time market date.

**Architecture:** Keep indicator calculations centralized in `calculate_historical_setup`. Pass an explicit query timestamp into live screening so each market derives `T` from the query time rather than the quote time; message scanning already receives a query timestamp and will use it the same way.

**Tech Stack:** Python, FastAPI service layer, pytest, React/TypeScript.

## Global Constraints

- `趋势值 = (MA20(T-1) - MA20(T-6)) / ATR14`.
- Values greater than `0.1` are `上升`; values below `-0.1` are `下降`.
- Values in `[-0.1, 0.1]`, including both boundaries, are `横盘`.
- ATR14 equal to zero produces `-`.
- Live `T` is the query-time date in the target market timezone.
- Historical indicators never include a daily bar whose market date equals `T`.
- The latest quote remains the source of current price and displayed data time.

---

### Task 1: ATR-normalized MA20 direction

**Files:**
- Modify: `backend/tests/test_indicator_service.py`
- Modify: `backend/app/services/indicator_service.py`

**Interfaces:**
- Consumes: `calculate_historical_setup(bars, current_price, boll_period=20, boll_std_multiplier=2)`.
- Produces: `HistoricalSetup.ma20_direction` with `上升 | 下降 | 横盘 | - | None`.

- [ ] **Step 1: Write failing direction tests**

Add literal fixtures whose last 25 closes and high/low spreads independently yield normalized values above, below, on, and inside the thresholds. Add a zero-range constant fixture for ATR14 zero.

```python
@pytest.mark.parametrize(
    ("closes", "spread", "expected"),
    [
        ([100.0] * 5 + [100.5] * 20, 1, "上升"),
        ([100.5] * 5 + [100.0] * 20, 1, "下降"),
        ([100.0] * 5 + [100.02] * 20, 1, "横盘"),
    ],
)
def test_calculate_historical_setup_normalizes_ma20_direction_by_atr14(
    closes, spread, expected
):
    result = calculate_historical_setup(_daily_bars(closes, spread=spread), 100)
    assert result.ma20_direction == expected


def test_calculate_historical_setup_returns_dash_when_atr14_is_zero():
    result = calculate_historical_setup(_daily_bars([100.0] * 25, spread=0), 100)
    assert result.ma20_direction == "-"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_indicator_service.py -v`

Expected: direction assertions fail because production still compares the unnormalized MA delta with zero.

- [ ] **Step 3: Implement minimal normalized direction logic**

Move direction classification after ATR14 calculation:

```python
atr14 = sum(true_ranges) / 14
if atr14 == 0:
    ma20_direction = "-"
else:
    trend_value = ma_delta / atr14
    if trend_value > 0.1:
        ma20_direction = "上升"
    elif trend_value < -0.1:
        ma20_direction = "下降"
    else:
        ma20_direction = "横盘"
```

- [ ] **Step 4: Run indicator tests and verify GREEN**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_indicator_service.py -v`

Expected: all indicator tests pass after updating old flat expectations to `横盘`.

### Task 2: Query-time market date for live scans

**Files:**
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_message_push_scan_service.py`
- Modify: `backend/app/services/screening_service.py`
- Modify: `backend/app/services/message_push_scan_service.py`
- Modify callers if required by the discovered `screen_intraday` signature.

**Interfaces:**
- Consumes: query timestamp supplied by the API/service call and `china_now` already supplied to message scans.
- Produces: `evaluation_date = _market_date(query_time, market)`.

- [ ] **Step 1: Write failing live-window tests**

Create cases where the query date is July 31 in the market timezone but the latest quote timestamp is July 30. Include a July 30 daily bar and assert it remains in the historical setup input/output rather than being filtered out.

For message scanning, pass `china_now` corresponding to July 31 market-local time while the quote time remains July 30 and assert the resulting opportunity uses indicators derived through July 30.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_api.py tests/test_message_push_scan_service.py -v
```

Expected: the stale-quote cases fail because production currently derives `evaluation_date` from `latest_time` or `quote.time`.

- [ ] **Step 3: Use query time for `T`**

In screening, capture or accept the query timestamp once and derive each market date from it:

```python
evaluation_date = _market_date(query_time, row_market)
```

In message scanning, derive the market date from the supplied scan time:

```python
evaluation_date = _market_date(china_now, market)
```

Keep `latest_price`, `latest_time`, `refreshed_at`, and `data_time` sourced from the quote.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_api.py tests/test_message_push_scan_service.py -v
```

Expected: all focused tests pass.

### Task 3: Type compatibility and full verification

**Files:**
- Modify: `frontend/src/api.ts`
- Modify any backend tests whose old fixture assumes only `上升 | 下降 | 需人工判断`.

**Interfaces:**
- Consumes: backend `ma20_direction` strings.
- Produces: frontend union `"上升" | "下降" | "横盘" | "-" | null`.

- [ ] **Step 1: Update the frontend response type**

```typescript
ma20_direction: "上升" | "下降" | "横盘" | "-" | null;
```

- [ ] **Step 2: Run backend regression tests**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging -v`

Expected: all backend tests pass.

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`

Expected: TypeScript and the production build complete successfully.

- [ ] **Step 4: Inspect the final diff**

Run: `git diff --check && git diff --stat && git status --short`

Expected: no whitespace errors; only the approved algorithm, live-date, test, type, and plan changes are present.
