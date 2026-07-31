# Message Push Settings and Ant Design Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent background message settings, make the scheduler use them at fixed China-time boundaries, and replace the entire hand-written frontend UI with Ant Design 6.

**Architecture:** A singleton SQLAlchemy model and focused settings service own the persisted configuration. GET/PUT endpoints expose the configuration and notify an in-process scheduler event after successful saves; each scan receives one immutable settings snapshot. The React app uses Ant Design as its only component library, with shared filter specifications but independent screening and settings state.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, SQLite, pytest, React 19, TypeScript 5.9, Vite 7, Ant Design 6, Vitest, Testing Library, jsdom.

## Global Constraints

- `interval_minutes` is 10–120 inclusive, in increments of 10, default 60.
- `min_market_cap` is 50,000,000,000–2,000,000,000,000 inclusive, in increments of 50,000,000,000, default 200,000,000,000.
- `min_avg_volume` is 1,000,000–100,000,000 inclusive, in increments of 1,000,000, default 10,000,000.
- The database is the only source of saved settings; entering the settings tab always reloads it.
- Saving does not scan immediately; it reschedules from the next boundary strictly after the current China time.
- Each US/HK scan round uses one settings snapshot.
- Ant Design 6 is the only frontend UI component library.
- Remove replaced hand-written components, native table/pagination UI, obsolete CSS, compatibility branches, and commented-out implementations.
- Keep the existing top header, horizontal tabs, filter/settings area, and stock table information structure.

---

### Task 1: Persistent settings model and service

**Files:**
- Create: `backend/app/models/message_push_setting.py`
- Create: `backend/app/services/message_push_settings_service.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_message_push_settings_service.py`

**Interfaces:**
- Produces: `MessagePushSetting`, `MessagePushSettingsSnapshot`, `get_message_push_settings(session)`, `save_message_push_settings(session, snapshot)`, and shared numeric constants.
- Consumes: SQLAlchemy `Session` and the existing declarative `Base`.

- [ ] **Step 1: Write failing persistence and validation tests**

```python
def test_get_creates_default_singleton(session):
    settings = get_message_push_settings(session)
    assert settings == MessagePushSettingsSnapshot(
        interval_minutes=60,
        min_market_cap=Decimal("200000000000"),
        min_avg_volume=Decimal("10000000"),
        updated_at=settings.updated_at,
    )
    assert session.scalar(select(func.count(MessagePushSetting.id))) == 1


def test_save_survives_a_new_session(session_factory):
    with session_factory() as session:
        save_message_push_settings(
            session,
            MessagePushSettingsSnapshot(
                interval_minutes=30,
                min_market_cap=Decimal("250000000000"),
                min_avg_volume=Decimal("12000000"),
                updated_at=None,
            ),
        )
    with session_factory() as session:
        saved = get_message_push_settings(session)
    assert saved.interval_minutes == 30
    assert saved.min_market_cap == Decimal("250000000000")
    assert saved.min_avg_volume == Decimal("12000000")


@pytest.mark.parametrize("interval", [0, 11, 130])
def test_rejects_invalid_interval(session, interval):
    with pytest.raises(ValueError):
        save_message_push_settings(session, valid_snapshot(interval_minutes=interval))
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_settings_service.py -v`

Expected: collection fails because the model and service do not exist.

- [ ] **Step 3: Implement the singleton model and settings service**

```python
@dataclass(frozen=True)
class MessagePushSettingsSnapshot:
    interval_minutes: int
    min_market_cap: Decimal
    min_avg_volume: Decimal
    updated_at: datetime | None


def get_message_push_settings(session: Session) -> MessagePushSettingsSnapshot:
    row = session.get(MessagePushSetting, SETTINGS_ID)
    if row is None:
        row = MessagePushSetting(
            id=SETTINGS_ID,
            interval_minutes=DEFAULT_INTERVAL_MINUTES,
            min_market_cap=DEFAULT_MIN_MARKET_CAP,
            min_avg_volume=DEFAULT_MIN_AVG_VOLUME,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return snapshot_from_row(row)
```

Validate all three values before mutating the row. Roll back and re-raise on commit failure. Export the new model from `app.models` so `Base.metadata.create_all()` creates the table.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_settings_service.py -v`

Expected: all service tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/message_push_setting.py backend/app/models/__init__.py backend/app/services/message_push_settings_service.py backend/tests/test_message_push_settings_service.py
git commit -m "feat: persist message push settings"
```

### Task 2: Settings GET/PUT API

**Files:**
- Create: `backend/app/controllers/message_push_settings_controller.py`
- Create: `backend/app/views/message_push_settings_view.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_message_push_settings_api.py`

**Interfaces:**
- Consumes: Task 1 service functions and `request.app.state.message_push_scheduler`.
- Produces: `GET /api/message-push-settings` and `PUT /api/message-push-settings`.

- [ ] **Step 1: Write failing API tests**

```python
def test_get_returns_persisted_settings(client):
    body = client.get("/api/message-push-settings").json()
    assert body["success"] is True
    assert body["data"]["interval_minutes"] == 60
    assert body["data"]["min_market_cap"] == 200000000000


def test_put_saves_full_settings_and_notifies_scheduler(client, scheduler):
    body = client.put(
        "/api/message-push-settings",
        json={
            "interval_minutes": 30,
            "min_market_cap": 250000000000,
            "min_avg_volume": 12000000,
        },
    ).json()
    assert body["success"] is True
    assert body["data"]["interval_minutes"] == 30
    assert scheduler.settings_changed.is_set()


def test_put_rejects_off_step_value(client):
    body = client.put(
        "/api/message-push-settings",
        json={
            "interval_minutes": 35,
            "min_market_cap": 250000000000,
            "min_avg_volume": 12000000,
        },
    ).json()
    assert body["success"] is False
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_settings_api.py -v`

Expected: 404 because the router is not registered.

- [ ] **Step 3: Implement request schema, controller, view, and router registration**

Use a Pydantic request model with exact bounds and `multiple_of`. Serialize decimals as JSON numbers and `updated_at` as ISO-8601. On a successful commit, call:

```python
scheduler = getattr(request.app.state, "message_push_scheduler", None)
if scheduler is not None:
    scheduler.notify_settings_changed()
```

Return existing `api_success` / `api_error` envelopes and preserve request logging behavior.

- [ ] **Step 4: Run API and regression tests**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_settings_api.py tests/test_api.py -v`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/controllers/message_push_settings_controller.py backend/app/views/message_push_settings_view.py backend/app/main.py backend/tests/test_message_push_settings_api.py
git commit -m "feat: expose message push settings API"
```

### Task 3: Dynamic boundary scheduler

**Files:**
- Modify: `backend/app/services/message_push_scheduler.py`
- Modify: `backend/tests/test_message_push_scheduler.py`
- Modify: `backend/tests/test_message_push_lifespan.py`

**Interfaces:**
- Consumes: `session_factory` and `get_message_push_settings`.
- Produces: `seconds_until_next_china_boundary(interval_minutes, now)`, `MessagePushScheduler.notify_settings_changed()`, and event-aware `run_forever()`.

- [ ] **Step 1: Write failing boundary and rescheduling tests**

```python
@pytest.mark.parametrize(
    ("now", "interval", "seconds"),
    [
        (datetime(2026, 7, 30, 10, 15, 30, tzinfo=CHINA_TIMEZONE), 10, 270),
        (datetime(2026, 7, 30, 10, 15, 30, tzinfo=CHINA_TIMEZONE), 30, 870),
        (datetime(2026, 7, 30, 10, 0, 0, tzinfo=CHINA_TIMEZONE), 60, 3600),
        (datetime(2026, 7, 30, 10, 15, 30, tzinfo=CHINA_TIMEZONE), 120, 6270),
    ],
)
def test_next_boundary(now, interval, seconds):
    assert seconds_until_next_china_boundary(interval, now) == seconds


def test_settings_change_wakes_scheduler_without_scanning():
    scanner = RecordingScanner()
    scheduler = MessagePushScheduler(scanner, settings_loader=lambda: snapshot(60))
    assert scheduler.settings_changed.is_set() is False
    scheduler.notify_settings_changed()
    assert scheduler.settings_changed.is_set() is True
    assert scanner.calls == 0
```

Add an async `run_forever` test with an injected wait function that returns `"settings_changed"` on its first call and `"boundary"` on its second. Assert the loader receives two calls while the scanner receives exactly one call, proving that the notification recomputes the boundary without scanning.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_scheduler.py tests/test_message_push_lifespan.py -v`

Expected: failures because interval boundaries and change notification do not exist.

- [ ] **Step 3: Implement China-midnight boundary math and event-aware waiting**

```python
def seconds_until_next_china_boundary(interval_minutes: int, now: datetime | None = None) -> float:
    china_now = normalize_china_time(now)
    midnight = china_now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = (china_now - midnight).total_seconds() / 60
    boundary_index = math.floor(elapsed_minutes / interval_minutes) + 1
    next_boundary = midnight + timedelta(minutes=boundary_index * interval_minutes)
    return (next_boundary - china_now).total_seconds()
```

`run_forever()` races `asyncio.sleep(delay)` against `settings_changed.wait()`. A settings change clears the event and recomputes without scanning; the sleep winning triggers one protected scan. Keep the overlap lock and cancellation behavior.

- [ ] **Step 4: Run scheduler tests and verify GREEN**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_scheduler.py tests/test_message_push_lifespan.py -v`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/message_push_scheduler.py backend/tests/test_message_push_scheduler.py backend/tests/test_message_push_lifespan.py
git commit -m "feat: reschedule message push from database settings"
```

### Task 4: Apply one settings snapshot to cache warm-up and US/HK scans

**Files:**
- Modify: `backend/app/services/message_push_cache_service.py`
- Modify: `backend/app/services/message_push_scan_service.py`
- Modify: `backend/app/services/message_push_scheduler.py`
- Modify: `backend/tests/test_message_push_cache_service.py`
- Modify: `backend/tests/test_message_push_scan_service.py`

**Interfaces:**
- Consumes: `MessagePushSettingsSnapshot`.
- Produces: `prepare_market(market, now, settings)`, `screen_with_cached_bars(market, now, settings)`, and `run_once(settings, china_now=None)`.

- [ ] **Step 1: Write failing threshold propagation tests**

```python
def test_cache_uses_snapshot_thresholds():
    settings = snapshot(min_market_cap="250000000000", min_avg_volume="12000000")
    asyncio.run(service.prepare_market("US", now, settings))
    assert longbridge.screen_calls == [
        ("US", Decimal("250000000000"), Decimal("12000000"))
    ]


def test_both_markets_receive_the_same_snapshot():
    settings = snapshot(interval_minutes=30)
    asyncio.run(service.run_once(settings, now))
    assert cache.settings_by_market == {"US": settings, "HK": settings}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_cache_service.py tests/test_message_push_scan_service.py -v`

Expected: signature mismatch or fixed-threshold assertions fail.

- [ ] **Step 3: Thread the immutable snapshot through scanner and cache**

Remove `MIN_MARKET_CAP` and `MIN_AVG_VOLUME` runtime usage from the cache service. Pass snapshot values to initial warm-up, hourly screening, and missing-symbol fills. The scheduler loads exactly once immediately before each scan and passes that object to `scanner.run_once(settings)`.

If settings loading fails, log `message_push_settings_read result=error` and return without calling the scanner.

- [ ] **Step 4: Run message-push backend tests**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging tests/test_message_push_cache_service.py tests/test_message_push_scan_service.py tests/test_message_push_scheduler.py tests/test_message_push_lifespan.py -v`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/message_push_cache_service.py backend/app/services/message_push_scan_service.py backend/app/services/message_push_scheduler.py backend/tests/test_message_push_cache_service.py backend/tests/test_message_push_scan_service.py
git commit -m "feat: apply saved filters to message scans"
```

### Task 5: Frontend test harness, Ant Design root, shared filter specifications, and API client

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/filterSpecifications.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/api.test.ts`

**Interfaces:**
- Produces: `MARKET_CAP_SPEC`, `AVG_VOLUME_SPEC`, `PUSH_INTERVAL_SPEC`, formatters, `MessagePushSettings`, `fetchMessagePushSettings()`, and `saveMessagePushSettings(settings)`.
- Consumes: existing unified API envelope.

- [ ] **Step 1: Install Ant Design and the test dependencies**

Run:

```bash
cd frontend
npm install antd
npm install --save-dev vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Write failing API client tests**

```typescript
it("loads saved message push settings", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({
    success: true,
    code: 200,
    data: savedSettings
  }));
  await expect(fetchMessagePushSettings()).resolves.toEqual(savedSettings);
  expect(fetch).toHaveBeenCalledWith(
    "/api/message-push-settings",
    expect.objectContaining({ headers: expect.any(Object) })
  );
});

it("saves the complete settings object", async () => {
  await saveMessagePushSettings(savedSettings);
  expect(fetch).toHaveBeenCalledWith(
    "/api/message-push-settings",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({
        interval_minutes: 30,
        min_market_cap: 250000000000,
        min_avg_volume: 12000000
      })
    })
  );
});
```

- [ ] **Step 3: Run tests and verify RED**

Run: `cd frontend && npm test -- --run src/api.test.ts`

Expected: imports fail because the settings API functions do not exist.

- [ ] **Step 4: Add test configuration, Ant Design root providers, shared specs, and API functions**

Configure Vitest with `environment: "jsdom"` and `setupFiles: "./src/test/setup.ts"`. Add `"test": "vitest"` to scripts. Wrap the root:

```tsx
<ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: "#177e89", borderRadius: 8 } }}>
  <AntdApp>
    <App />
  </AntdApp>
</ConfigProvider>
```

Keep validation numbers in `filterSpecifications.ts`, not duplicated in page components.

- [ ] **Step 5: Run tests and build**

Run: `cd frontend && npm test -- --run src/api.test.ts && npm run build`

Expected: API tests and production build pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/main.tsx frontend/src/api.ts frontend/src/filterSpecifications.ts frontend/src/test/setup.ts frontend/src/api.test.ts
git commit -m "build: add Ant Design and frontend tests"
```

### Task 6: Replace screening UI completely with Ant Design

**Files:**
- Create: `frontend/src/components/ScreeningFilters.tsx`
- Create: `frontend/src/components/ScreeningTable.tsx`
- Create: `frontend/src/components/ScreeningWorkspace.tsx`
- Create: `frontend/src/components/ScreeningWorkspace.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: existing screening API functions and Task 5 filter specifications.
- Produces: Ant Design daily/intraday channels with unchanged request behavior and columns.

- [ ] **Step 1: Write failing behavior tests**

```typescript
it("shows all existing stock columns and paginates through Table", async () => {
  render(<ScreeningWorkspace mode="daily" />);
  expect(await screen.findByText("AAPL.US")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Z-Score" })).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "是否适合建仓" })).toBeInTheDocument();
});

it("refreshes intraday only from the refresh button", async () => {
  const user = userEvent.setup();
  render(<ScreeningWorkspace mode="intraday" />);
  await user.click(screen.getByRole("button", { name: "刷新分时数据" }));
  expect(fetchIntradayScreenings).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && npm test -- --run src/components/ScreeningWorkspace.test.tsx`

Expected: component imports fail.

- [ ] **Step 3: Implement the Ant Design screening workspace**

Use `Segmented`, `Slider`, `Button`, `Alert`, and `Table`. Define typed `TableColumnsType<ScreeningRow>` and preserve all existing columns and formatter behavior. Use Table pagination:

```tsx
pagination={{
  current: filters.page,
  pageSize: filters.page_size,
  total: data?.total ?? 0,
  showSizeChanger: false,
  showTotal: (total) => `共 ${total} 条`,
  onChange: (page) => updateFilters({ page })
}}
scroll={{ x: 1800 }}
```

Delete `SegmentedControl`, `RangeFilter`, the native table, custom pagination JSX, and their CSS. Retain only layout CSS with no duplicate button, table, slider, alert, segmented, or pagination skinning.

- [ ] **Step 4: Run component tests and build**

Run: `cd frontend && npm test -- --run src/components/ScreeningWorkspace.test.tsx && npm run build`

Expected: tests and build pass with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/ScreeningFilters.tsx frontend/src/components/ScreeningTable.tsx frontend/src/components/ScreeningWorkspace.tsx frontend/src/components/ScreeningWorkspace.test.tsx frontend/src/styles.css
git commit -m "refactor: replace screening UI with Ant Design"
```

### Task 7: Ant Design settings page and tab reload behavior

**Files:**
- Create: `frontend/src/components/MessagePushSettings.tsx`
- Create: `frontend/src/components/MessagePushSettings.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 5 settings API and shared specifications.
- Produces: a settings tab that reloads on every entry, tracks saved/draft state, and saves complete settings.

- [ ] **Step 1: Write failing page behavior tests**

```typescript
it("reloads database settings every time the tab is entered", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("tab", { name: "后台消息设置" }));
  expect(fetchMessagePushSettings).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("tab", { name: "日线筛选" }));
  await user.click(screen.getByRole("tab", { name: "后台消息设置" }));
  expect(fetchMessagePushSettings).toHaveBeenCalledTimes(2);
});

it("keeps a failed-save draft and resets it from the database on re-entry", async () => {
  saveMessagePushSettings.mockRejectedValueOnce(new Error("保存失败"));
  // Change interval, save, assert draft remains visible.
  // Leave and re-enter, assert GET response restores the database value.
});

it("does not request stock screening while settings is active", async () => {
  render(<App initialTab="settings" />);
  await screen.findByText("后台消息设置");
  expect(fetchDailyScreenings).not.toHaveBeenCalled();
  expect(fetchIntradayScreenings).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && npm test -- --run src/components/MessagePushSettings.test.tsx`

Expected: settings component and tab are missing.

- [ ] **Step 3: Implement load, draft comparison, save, retry, and feedback**

Use Ant Design `Card`, `Form`, `Slider`, `Button`, `Alert`, `Skeleton`, and `message`. Mount a new `MessagePushSettings` instance when the settings tab becomes active so its effect always calls GET. Disable save when:

```typescript
const dirty = saved !== null
  && (
    draft.interval_minutes !== saved.interval_minutes
    || draft.min_market_cap !== saved.min_market_cap
    || draft.min_avg_volume !== saved.min_avg_volume
  );
```

On successful PUT, replace both states from the server response and show `设置已保存，将从下一个固定钟点生效`. On GET failure, show an Alert and retry button without populating default values.

- [ ] **Step 4: Run all frontend tests and build**

Run: `cd frontend && npm test -- --run && npm run build`

Expected: all frontend tests and build pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/api.ts frontend/src/components/MessagePushSettings.tsx frontend/src/components/MessagePushSettings.test.tsx frontend/src/styles.css
git commit -m "feat: add background message settings page"
```

### Task 8: Full verification and browser visual QA

**Files:**
- Verify: all files touched by Tasks 1–7.

**Interfaces:**
- Consumes: the complete backend and frontend.
- Produces: verified behavior with no obsolete UI code.

- [ ] **Step 1: Run the complete backend suite**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging -v`

Expected: all tests pass.

- [ ] **Step 2: Run the complete frontend suite and production build**

Run: `cd frontend && npm test -- --run && npm run build`

Expected: all tests pass and Vite emits a successful production build.

- [ ] **Step 3: Scan for obsolete UI remnants**

Run:

```bash
rg -n '<table|className="(segmented|range-filter|refresh-button|pagination|error-banner)|function (SegmentedControl|RangeFilter)' frontend/src
```

Expected: no matches.

- [ ] **Step 4: Start the application and perform browser QA**

Run from repository root: `BACKEND_PORT=8010 FRONTEND_PORT=5179 ./start.sh`

Verify in the in-app browser:

- desktop and narrow view;
- all three horizontal tabs;
- daily automatic load and filter controls;
- intraday explicit refresh;
- table horizontal scrolling and pagination;
- settings GET on every entry;
- settings loading, error/retry, dirty state, save success, and save failure;
- no legacy UI or CSS artifacts.

- [ ] **Step 5: Apply only evidence-driven corrections and rerun affected tests**

For each defect, first add or adjust a test that fails for the observed behavior, then make the smallest correction and rerun the focused test plus the full frontend build.

- [ ] **Step 6: Final commit**

```bash
git add backend frontend
git commit -m "test: verify message settings and Ant Design migration"
```
