# Message Push Market Cache Design

## Goal

Add an optional in-memory daily-bar cache for future background message-push scans. The cache must preserve all existing technical-indicator formulas while avoiding repeated historical candlestick requests during hourly US and HK market scans.

## Scope

This change covers:

- the `ENABLE_MESSAGE_PUSH` feature switch;
- FastAPI lifespan initialization of the message-push cache;
- independent US and HK cache state;
- per-market Screener discovery and daily-bar preloading;
- lazy daily-bar loading for symbols that enter a later Screener result;
- bounded retries and diagnostic logging.

This change does not add a WeChat provider, a recurring scheduler, notification persistence, or message delivery. Those components may consume this cache later.

## Configuration

The environment variable is:

```env
ENABLE_MESSAGE_PUSH=false
```

It defaults to `false`. When disabled, FastAPI performs no message-push Screener requests, daily-bar preloading, or cache maintenance.

The Python configuration value is named `enable_message_push`.

## Cache Ownership and Shape

The process-local cache variable is named `message_push_market_cache`.

US and HK are managed independently:

```python
message_push_market_cache = {
    "US": {
        "cache_ready": False,
        "trade_date": None,
        "error": None,
        "bars": {},
    },
    "HK": {
        "cache_ready": False,
        "trade_date": None,
        "error": None,
        "bars": {},
    },
}
```

`bars` maps a symbol to its recent daily bars. Each value contains the latest 30 daily bars returned by Longbridge. Indicator calculation continues to exclude the current, incomplete market date and uses the same historical windows and formulas as today.

`trade_date` is the market date for which the cache was initialized. `cache_ready` states whether that market's complete preload succeeded. `error` is `None` after success and contains the final failure message after an unsuccessful initialization round.

## FastAPI Lifespan Initialization

When `ENABLE_MESSAGE_PUSH=false`, lifespan skips all cache work.

When enabled, lifespan initializes US and HK independently. For each market:

1. If `cache_ready` is true and `trade_date` matches the current market trade date, return without querying Longbridge.
2. Otherwise run the existing Screener with the background-push defaults:
   - minimum market capitalization: 200 billion;
   - minimum average monthly volume: 10 million.
3. Fetch 30 daily bars for every returned symbol under the existing Longbridge SDK rate control.
4. Build a temporary symbol-to-bars mapping.
5. Publish the temporary mapping atomically only after every symbol succeeds.
6. Set `trade_date`, clear `error`, and set `cache_ready=true`.

Initialization of one market does not depend on the other. FastAPI itself still starts if one or both market preloads fail. A later message-push task may process every ready market; it skips message delivery only when neither market is ready.

## Retries and Failures

Each market gets at most three attempts per initialization round.

- A failed attempt is logged and retried.
- After the third failure, `cache_ready` remains false and `error` records the final exception text.
- A successful market is not reloaded because the other market failed.
- The next hourly message-push scan may start a new, three-attempt initialization round for a failed market.

A partially filled temporary mapping is discarded after failure and is never exposed as a ready cache.

## Trading-Day Rollover

Before scanning a market, compare its cached `trade_date` with the current market trade date.

When they differ:

1. mark only that market as not ready;
2. clear only that market's bars and error;
3. initialize that market again.

US rollover never clears HK data, and HK rollover never clears US data. Market dates must use the existing market-aware date conversion rather than the server's local calendar date.

## Hourly Scan Cache Use

Every hourly scan reruns Screener independently for US and HK so that boundary symbols can enter or leave as market capitalization and volume conditions change.

For every returned symbol:

- use cached daily bars when present;
- fetch and cache 30 daily bars when absent;
- retain bars for a symbol that leaves the current Screener result, because it may re-enter later that trading day.

Lazy additions are performed under a per-market lock and are published only after a successful Longbridge response.

## Indicator Invariants

This cache changes data acquisition only. It must not change:

- 20-day Bollinger Band calculation;
- MA20 direction calculation;
- ATR14 calculation;
- previous 10-day high and low;
- reversal-trend and entry-suitability rules;
- the comparison between previous close, current real-time price, and the historical daily Bollinger Band.

The existing intraday screening API remains unchanged.

## Logging

Every initialization attempt logs an outcome. Logs include:

- operation name;
- market;
- market trade date;
- attempt number;
- Screener symbol count when available;
- cached symbol count when available;
- duration;
- success or failure;
- failure message when applicable.

Logs must not include Longbridge credentials or access tokens.

Lazy cache misses and trading-day cache resets also produce structured logs with market, symbol count, and outcome.

## Concurrency

Each market has an independent lock. Cache readiness checks use double-checked locking so concurrent scans cannot initialize the same market twice. Temporary mappings prevent readers from observing a half-built cache.

The first implementation assumes one FastAPI worker. Multiple workers would each own and initialize a separate cache; a future multi-worker deployment should move ownership to a dedicated scheduler process or a shared cache.

## Tests

Automated tests cover:

- disabled message push performs no preload;
- US and HK initialize independently;
- one ready market remains usable when the other fails;
- both failed markets cause a push scan to skip;
- a market stops after three failed attempts and records the final error;
- success and failure attempts are logged;
- an already-ready cache for the current trade date is not reloaded;
- a new trade date clears and reloads only the affected market;
- a later Screener entrant triggers a single lazy daily-bar request;
- a preload failure never publishes partial bars;
- existing indicator and API tests remain unchanged and pass.
