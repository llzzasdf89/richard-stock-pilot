# PushPlus Message Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 FastAPI 单进程内每个中国时间整点扫描美股和港股，并将符合既有入场条件的股票通过 PushPlus 逐只推送。

**Architecture:** 新建独立 PushPlus 客户端、市场缓存服务和扫描调度服务。扫描服务复用 `indicator_service.calculate_historical_setup` 等既有公式，生命周期仅负责按配置启动缓存预热和小时循环；US/HK 全程独立容错。

**Tech Stack:** Python 3.12、FastAPI lifespan、httpx、Longbridge SDK、pytest、标准库 asyncio/zoneinfo/logging。

## Global Constraints

- 不修改布林带、MA20、ATR14、前 10 日高低、反转趋势和适合入场的既有公式。
- `message_push_market_cache` 必须按 US/HK 独立保存 `cache_ready`、`trade_date`、`error`、`bars`。
- 长桥交易日接口使用 `Asia/Shanghai` 日期，最多尝试 3 次，异常后才按中国时间工作日降级。
- 每小时重新运行 Screener，最低市值 2000 亿、最低月均成交量 1000 万。
- 只发送 `is_suitable_for_entry == "是"`；一只股票一条；零结果不发送；不跨小时去重。
- 第一版只支持单 FastAPI Worker。

---

### Task 1: 配置和 PushPlus 客户端

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/pushplus_message_service.py`
- Create: `backend/tests/test_pushplus_message_service.py`
- Modify: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `message_push_enabled() -> bool`
- Produces: `PushPlusMessageService.from_environment(http_client=None, sleep=None)`
- Produces: `send_message(title: str, content: str) -> dict[str, Any]`

- [ ] **Step 1: 写失败测试**

覆盖布尔开关默认关闭、常见真值解析、Token 缺失报错、请求包含 `template=html/channel=wechat`、`code=200` 成功、临时错误最多三次、永久错误一次停止。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_pushplus_message_service.py -v`

Expected: FAIL，因为配置函数和 PushPlus 服务尚不存在。

- [ ] **Step 3: 最小实现**

配置函数在调用时读取环境变量，避免测试与运行期缓存错位。PushPlus 服务使用注入的 `httpx.Client`，只重试连接/超时、HTTP 5xx 和可重试平台错误；异常文本不得包含 Token。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_pushplus_message_service.py -v`

Expected: PASS。

### Task 2: 长桥交易日适配和市场缓存

**Files:**
- Modify: `backend/app/services/longbridge_service.py`
- Create: `backend/app/services/message_push_cache_service.py`
- Modify: `backend/tests/test_longbridge_service.py`
- Create: `backend/tests/test_message_push_cache_service.py`

**Interfaces:**
- Produces: `LongbridgeService.get_trading_days(market: str, start: date, end: date) -> set[date]`
- Produces: module-level `message_push_market_cache`
- Produces: `MessagePushCacheService.is_trading_day(market, china_now) -> bool`
- Produces: `prepare_market(market, china_now) -> bool`
- Produces: `screen_with_cached_bars(market, china_now) -> tuple[list[Security], dict[str, list[MarketDataBar]]]`

- [ ] **Step 1: 写交易日失败测试**

用完整伪 SDK 响应验证日期提取、市场映射以及中国日期原样传入。

- [ ] **Step 2: 运行交易日测试确认失败**

Run: `cd backend && uv run pytest tests/test_longbridge_service.py -v`

Expected: FAIL，因为 `get_trading_days` 尚不存在。

- [ ] **Step 3: 实现最小交易日适配**

兼容 SDK 返回的正常交易日与半日交易日集合，并统一成 `set[date]`。

- [ ] **Step 4: 写缓存失败测试**

覆盖三次重试、工作日降级、正常休市不降级、市场独立、临时字典原子发布、同日 ready 不重复、换日清理、Screener 新股票按需补查。

- [ ] **Step 5: 运行缓存测试确认失败**

Run: `cd backend && uv run pytest tests/test_message_push_cache_service.py -v`

Expected: FAIL，因为缓存服务尚不存在。

- [ ] **Step 6: 实现最小缓存服务**

为 US/HK 建独立异步锁；预热使用 30 根日 K 和最多 3 次整轮重试；补查只请求缺失股票并在成功后更新正式缓存。

- [ ] **Step 7: 运行相关测试确认通过**

Run: `cd backend && uv run pytest tests/test_longbridge_service.py tests/test_message_push_cache_service.py -v`

Expected: PASS。

### Task 3: 建仓机会扫描和消息格式

**Files:**
- Create: `backend/app/services/message_push_scan_service.py`
- Create: `backend/tests/test_message_push_scan_service.py`

**Interfaces:**
- Produces: `derive_entry_direction(setup: HistoricalSetup, price: float) -> str | None`
- Produces: `build_pushplus_message(opportunity: dict[str, Any], scan_time: datetime) -> tuple[str, str]`
- Produces: `MessagePushScanService.scan_market(market, china_now) -> ScanSummary`
- Produces: `MessagePushScanService.run_once(china_now=None) -> list[ScanSummary]`

- [ ] **Step 1: 写失败测试**

使用固定 25 根历史日 K 和实时报价，验证做多/做空方向、仅适合入场才发送、每只单独发送、零匹配不发送、单只失败继续、US/HK 独立、正文无详情链接。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_message_push_scan_service.py -v`

Expected: FAIL，因为扫描服务尚不存在。

- [ ] **Step 3: 实现最小扫描服务**

通过缓存服务取得 Screener 股票与日 K，批量取得最新报价；排除报价市场日期当日未完成日 K；调用现有 `calculate_historical_setup` 和 `calculate_break_percent`；只将合格结果交给 PushPlus 服务。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_message_push_scan_service.py tests/test_indicator_service.py -v`

Expected: PASS，既有指标测试保持不变。

### Task 4: 整点调度和 FastAPI 生命周期

**Files:**
- Create: `backend/app/services/message_push_scheduler.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_message_push_scheduler.py`
- Create: `backend/tests/test_message_push_lifespan.py`

**Interfaces:**
- Produces: `seconds_until_next_china_hour(now: datetime) -> float`
- Produces: `MessagePushScheduler.run_forever() -> None`
- Produces: `start_message_push(app: FastAPI) -> None`
- Produces: `stop_message_push(app: FastAPI) -> None`

- [ ] **Step 1: 写失败测试**

验证下一整点秒数、循环按整点调用、前一轮未完时跳过、开关关闭无初始化、开启时预热两个市场并启动任务、退出时取消任务、配置错误不阻止应用启动。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_message_push_scheduler.py tests/test_message_push_lifespan.py -v`

Expected: FAIL，因为调度器和生命周期接入尚不存在。

- [ ] **Step 3: 实现最小调度与生命周期**

使用 `asyncio.create_task` 和单轮 `asyncio.Lock`。启动预热按市场独立捕获错误，退出时取消并等待后台任务；关闭开关时不构造长桥或 PushPlus 服务。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_message_push_scheduler.py tests/test_message_push_lifespan.py tests/test_api.py -v`

Expected: PASS。

### Task 5: 本地运行配置说明与完整回归

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Documents: `ENABLE_MESSAGE_PUSH`, `MESSAGE_PUSH_PROVIDER`, `PUSHPLUS_TOKEN`
- Documents: 单 Worker、本地电脑需保持开机且禁用休眠。

- [ ] **Step 1: 更新示例配置和运行说明**

只展示占位符，不写入真实 Token；说明 `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`。

- [ ] **Step 2: 检查敏感信息和差异**

Run: `git diff --check`

Expected: 无格式错误，差异中无真实 Token。

- [ ] **Step 3: 运行完整后端测试**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p no:debugging -v`

Expected: 全部通过。

- [ ] **Step 4: 检查工作树**

Run: `git status --short`

Expected: 仅包含本功能计划内文件。
