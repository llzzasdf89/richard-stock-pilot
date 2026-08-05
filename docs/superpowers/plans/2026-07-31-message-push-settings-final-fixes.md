# Message Push Settings Final Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final review findings around daily boundary scheduling, recoverable scheduler failures, concurrent singleton creation, timezone-aware API timestamps, and operator documentation.

**Architecture:** Keep the existing singleton settings model, scheduler event, and no-overlap lock. Cap each calculated boundary at the next China midnight, validate every database snapshot, recover schedule-planning failures through the existing injected wait boundary, and create defaults with a database-atomic insert-if-absent operation.

**Tech Stack:** Python 3.12+, asyncio, FastAPI, SQLAlchemy 2, SQLite, pytest.

## Global Constraints

- Legal intervals remain 10–120 inclusive in increments of 10.
- Every calendar day re-anchors at China time `00:00`.
- A settings read or boundary-calculation failure must never run the scanner with guessed values.
- The scheduler task must remain retryable after transient persistence or corrupt-data failures.
- Concurrent first reads must both return defaults and leave exactly one singleton row.
- Existing no-overlap behavior remains unchanged.
- Execution is inline on the current branch, as selected by the review dispatch.

---

### Task 1: Daily-reanchored boundary calculation

**Files:**
- Modify: `backend/tests/test_message_push_scheduler.py`
- Modify: `backend/app/services/message_push_scheduler.py`

**Interfaces:**
- Consumes: `seconds_until_next_china_boundary(interval_minutes, now)`
- Produces: A next boundary no later than the next China midnight.

- [ ] **Step 1: Write the failing edge test**

Add a literal table for China time `2026-07-31 23:50` and intervals `50`, `70`, `100`, and `110`, asserting `600` seconds for every case.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd backend
UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_scheduler.py::test_non_divisor_intervals_reanchor_at_next_china_midnight -v
```

Expected: all four cases fail because the current result extends the prior day's interval grid past midnight.

- [ ] **Step 3: Implement the minimal boundary cap**

Calculate `next_midnight = midnight + timedelta(days=1)` and choose `min(calculated_boundary, next_midnight)`.

- [ ] **Step 4: Run scheduler tests and verify GREEN**

Run:

```bash
cd backend
UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_scheduler.py -v
```

Expected: all scheduler tests pass.

### Task 2: Recoverable scheduler planning and shutdown

**Files:**
- Modify: `backend/tests/test_message_push_scheduler.py`
- Modify: `backend/tests/test_message_push_lifespan.py`
- Modify: `backend/app/services/message_push_scheduler.py`
- Modify: `backend/app/services/message_push_settings_service.py`

**Interfaces:**
- Consumes: `MessagePushScheduler.run_forever()`, `stop_message_push(app)`, and database rows returned by `get_message_push_settings(session)`.
- Produces: Logged, wait-backed retry after settings/boundary errors; validated read snapshots; contained failed-task shutdown.

- [ ] **Step 1: Write failing deterministic recovery tests**

Use the scheduler's injected `wait_for_next` to prove:

- a transient loader exception logs, waits once, retries, and does not scan before a valid schedule;
- an invalid zero interval logs, waits, retries, and does not scan;
- shutdown awaits and contains an already-failed task.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_message_push_scheduler.py \
  tests/test_message_push_lifespan.py -v
```

Expected: `run_forever` propagates planning errors and `stop_message_push` propagates a failed task.

- [ ] **Step 3: Implement minimal recovery**

Catch settings-load and boundary-calculation exceptions separately, log them, wait for either a short retry delay or `settings_changed`, clear the event when consumed, and restart the loop without scanning. Validate snapshots built from database rows with the existing service validator. Catch and log non-cancellation task failures during shutdown.

- [ ] **Step 4: Run scheduler, lifespan, and settings tests and verify GREEN**

Run:

```bash
cd backend
UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_message_push_scheduler.py \
  tests/test_message_push_lifespan.py \
  tests/test_message_push_settings_service.py -v
```

Expected: all selected tests pass.

### Task 3: Atomic defaults and timezone-aware API timestamps

**Files:**
- Modify: `backend/tests/test_message_push_settings_service.py`
- Modify: `backend/tests/test_message_push_settings_api.py`
- Modify: `backend/app/services/message_push_settings_service.py`

**Interfaces:**
- Consumes: `get_message_push_settings(session)` and the GET API serializer.
- Produces: Atomic insert-if-absent for the fixed singleton primary key and aware UTC snapshots.

- [ ] **Step 1: Write failing concurrency and timestamp tests**

Run two real SQLite sessions in worker threads, synchronize their start and ORM flushes, and assert both callers receive the default snapshot while one row exists. Parse GET `updated_at` with `datetime.fromisoformat` and assert it has a non-`None` UTC offset.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_message_push_settings_service.py::test_concurrent_first_reads_return_defaults_and_create_one_row \
  tests/test_message_push_settings_api.py::test_get_updated_at_includes_timezone_offset -v
```

Expected: one concurrent caller raises a uniqueness error and SQLite returns a naive timestamp.

- [ ] **Step 3: Implement the minimal persistence fix**

Use SQLite/PostgreSQL conflict-ignore inserts for their native dialects and a generic insert-with-`IntegrityError` recovery path elsewhere. Normalize SQLite's naive UTC value to an aware UTC datetime when building a snapshot, then validate the snapshot before returning it.

- [ ] **Step 4: Run service and API tests and verify GREEN**

Run:

```bash
cd backend
UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging \
  tests/test_message_push_settings_service.py \
  tests/test_message_push_settings_api.py -v
```

Expected: all selected tests pass.

### Task 4: Documentation, report, and final verification

**Files:**
- Modify: `README.md`
- Create: `.superpowers/sdd/2026-07-31-message-push-settings-and-antd/final-fixes-report.md`

**Interfaces:**
- Produces: Current API inventory, configurable fixed-boundary scheduling explanation, and exact TDD/verification evidence.

- [ ] **Step 1: Update human documentation**

List both message-push settings endpoints and explain that saved intervals align from China midnight, re-anchor daily, and take effect at the next fixed boundary.

- [ ] **Step 2: Run complete backend and frontend verification**

Run:

```bash
cd backend
UV_CACHE_DIR=.uv-cache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging -v

cd ../frontend
npm test -- --run
npm run build
```

- [ ] **Step 3: Self-review and write the final report**

Review the diff against every finding, record every RED/GREEN/full command and result, note that scheduled no-overlap remains intact, and document any residual concerns.

- [ ] **Step 4: Commit**

```bash
git add README.md backend docs/superpowers/plans/2026-07-31-message-push-settings-final-fixes.md .superpowers/sdd/2026-07-31-message-push-settings-and-antd/final-fixes-report.md
git commit -m "fix: harden message push scheduling settings"
```
