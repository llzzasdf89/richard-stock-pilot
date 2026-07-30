import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchDailyScreenings,
  fetchIntradayScreenings,
  type Market,
  type ScreeningFilters,
  type ScreeningPayload,
  type ScreeningRow,
  type SignalType,
  type TabKey
} from "./api";

const DEFAULT_FILTERS: ScreeningFilters = {
  market: "US",
  signal_type: "all",
  min_market_cap: 200_000_000_000,
  min_avg_volume: 10_000_000,
  interval: "5m",
  page: 1,
  page_size: 20
};

const marketOptions: Array<{ value: Market; label: string }> = [
  { value: "US", label: "美股" },
  { value: "HK", label: "港股" }
];

const signalOptions: Array<{ value: SignalType; label: string }> = [
  { value: "all", label: "全部" },
  { value: "upper_breakout", label: "上穿 BOLL" },
  { value: "lower_breakdown", label: "下击 BOLL" }
];

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("daily");
  const [filters, setFilters] = useState<ScreeningFilters>(DEFAULT_FILTERS);
  const [dailyData, setDailyData] = useState<ScreeningPayload | null>(null);
  const [intradayData, setIntradayData] = useState<ScreeningPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intradayRequestSeq = useRef(0);

  useEffect(() => {
    if (activeTab !== "daily") return;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      fetchDailyScreenings(filters)
        .then((payload) => {
          if (!cancelled) setDailyData(payload);
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 400);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeTab, filters]);

  useEffect(() => {
    if (activeTab !== "intraday") return;

    void requestIntraday(filters);
  }, [activeTab]);

  const data = activeTab === "daily" ? dailyData : intradayData;
  const titleMeta = useMemo(() => {
    if (activeTab === "daily") {
      return dailyData?.data_date ? `数据日期：${dailyData.data_date}` : "等待日线数据";
    }
    return intradayData?.refreshed_at ? `刷新时间：${formatDateTime(intradayData.refreshed_at)}` : "点击按钮刷新分时数据";
  }, [activeTab, dailyData, intradayData]);

  function updateFilters(next: Partial<ScreeningFilters>) {
    const nextFilters = { ...filters, ...next, page: next.page ?? 1 };
    const changedKeys = Object.keys(next);
    const isPageOnlyChange = changedKeys.length === 1 && changedKeys[0] === "page";
    const shouldClearData = Object.keys(next).some((key) => key !== "page");
    if (shouldClearData) {
      intradayRequestSeq.current += 1;
      setDailyData(null);
      setIntradayData(null);
      setError(null);
    }
    setFilters(nextFilters);
    if (activeTab === "intraday" && isPageOnlyChange && intradayData) {
      void requestIntraday(nextFilters);
    }
  }

  async function requestIntraday(nextFilters: ScreeningFilters) {
    const requestSeq = ++intradayRequestSeq.current;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchIntradayScreenings(nextFilters);
      if (requestSeq === intradayRequestSeq.current) {
        setIntradayData(payload);
      }
    } catch (err) {
      if (requestSeq === intradayRequestSeq.current) {
        setError((err as Error).message);
      }
    } finally {
      if (requestSeq === intradayRequestSeq.current) {
        setLoading(false);
      }
    }
  }

  async function refreshIntraday() {
    await requestIntraday(filters);
  }

  function switchTab(nextTab: TabKey) {
    if (nextTab === activeTab) return;

    intradayRequestSeq.current += 1;
    setError(null);
    setDailyData(null);
    setIntradayData(null);
    setFilters(DEFAULT_FILTERS);
    setActiveTab(nextTab);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Richard Stock Pilot</h1>
          <p>{titleMeta}</p>
        </div>
        <div className="topbar-actions">
          <span className="status-dot" />
          <span>{loading ? "请求中" : "就绪"}</span>
        </div>
      </header>

      <section className="workspace">
        <div className="tabs" role="tablist" aria-label="筛选频道">
          <button className={activeTab === "daily" ? "active" : ""} onClick={() => switchTab("daily")}>
            日线筛选
          </button>
          <button className={activeTab === "intraday" ? "active" : ""} onClick={() => switchTab("intraday")}>
            分时筛选
          </button>
        </div>

        <div className="filters">
          <SegmentedControl
            label="市场"
            options={marketOptions}
            value={filters.market}
            onChange={(market) => updateFilters({ market })}
          />
          <SegmentedControl
            label="信号"
            options={signalOptions}
            value={filters.signal_type}
            onChange={(signal_type) => updateFilters({ signal_type })}
          />
          <RangeFilter
            label="最低市值"
            value={filters.min_market_cap}
            min={50_000_000_000}
            max={2_000_000_000_000}
            step={50_000_000_000}
            formatter={formatLargeMoney}
            onChange={(min_market_cap) => updateFilters({ min_market_cap })}
          />
          <RangeFilter
            label="最低月均成交量"
            value={filters.min_avg_volume}
            min={1_000_000}
            max={100_000_000}
            step={1_000_000}
            formatter={formatVolume}
            onChange={(min_avg_volume) => updateFilters({ min_avg_volume })}
          />
          {activeTab === "intraday" && (
            <button className="refresh-button" onClick={refreshIntraday} disabled={loading}>
              刷新分时数据
            </button>
          )}
        </div>

        {error && <div className="error-banner">{error}</div>}

        <ScreeningTable rows={data?.results ?? []} loading={loading} activeTab={activeTab} />

        <footer className="pagination">
          <span>
            共 {data?.total ?? 0} 条，当前第 {data?.page ?? filters.page} 页
          </span>
          <div>
            <button disabled={filters.page <= 1 || loading} onClick={() => updateFilters({ page: filters.page - 1 })}>
              上一页
            </button>
            <button
              disabled={loading || Boolean(data && filters.page >= data.total_pages)}
              onClick={() => updateFilters({ page: filters.page + 1 })}
            >
              下一页
            </button>
          </div>
        </footer>
      </section>
    </main>
  );
}

function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange
}: {
  label: string;
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented-block">
      <span className="filter-label">{label}</span>
      <div className="segmented">
        {options.map((option) => (
          <button
            key={option.value}
            className={option.value === value ? "selected" : ""}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RangeFilter({
  label,
  value,
  min,
  max,
  step,
  formatter,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  formatter: (value: number) => string;
  onChange: (value: number) => void;
}) {
  const [draftValue, setDraftValue] = useState(value);
  const debounceTimer = useRef<number | null>(null);

  useEffect(() => {
    setDraftValue(value);
  }, [value]);

  useEffect(() => {
    return () => {
      if (debounceTimer.current !== null) {
        window.clearTimeout(debounceTimer.current);
      }
    };
  }, []);

  function updateDraftValue(nextValue: number) {
    setDraftValue(nextValue);
    if (debounceTimer.current !== null) {
      window.clearTimeout(debounceTimer.current);
    }
    debounceTimer.current = window.setTimeout(() => {
      onChange(nextValue);
    }, 600);
  }

  return (
    <label className="range-filter">
      <span>
        {label}
        <strong>{formatter(draftValue)}</strong>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={draftValue}
        onChange={(event) => updateDraftValue(Number(event.target.value))}
      />
    </label>
  );
}

function ScreeningTable({
  rows,
  loading,
  activeTab
}: {
  rows: ScreeningRow[];
  loading: boolean;
  activeTab: TabKey;
}) {
  const closeLabel = activeTab === "daily" ? "收盘价" : "昨日收盘价";
  const showLatestPrice = activeTab === "intraday";
  const emptyColSpan = showLatestPrice ? 21 : 20;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th>市场</th>
            <th>货币</th>
            <th>信号</th>
            <th>近期财报日期（未来几天内）</th>
            <th className="numeric">{closeLabel}</th>
            {showLatestPrice && <th className="numeric">最新价格</th>}
            <th className="numeric">市值</th>
            <th className="numeric">月均成交量</th>
            <th className="numeric">BOLL 上轨价格</th>
            <th className="numeric">BOLL 中轨价格</th>
            <th className="numeric">BOLL 下轨价格</th>
            <th>MA20均线方向</th>
            <th className="numeric">平均波动幅度 ATR14</th>
            <th className="numeric">前10个交易日最低点</th>
            <th className="numeric">前10个交易日最高点</th>
            <th>是否存在逆转趋势</th>
            <th>是否适合建仓</th>
            <th className="numeric">突破幅度</th>
            <th>数据时间</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.symbol}-${row.data_time}-${row.signal_type}`}>
              <td className="symbol">{row.symbol}</td>
              <td>{row.name}</td>
              <td>{row.market === "US" ? "美股" : "港股"}</td>
              <td>{row.currency}</td>
              <td>
                <span className={`signal ${row.signal_type}`}>{formatSignal(row.signal_type)}</span>
              </td>
              <td>{row.earnings_date ?? "-"}</td>
              <td className="numeric">{formatPrice(row.close)}</td>
              {showLatestPrice && <td className="numeric">{formatPrice(row.latest_price)}</td>}
              <td className="numeric">{formatLargeMoney(row.market_cap)}</td>
              <td className="numeric">{formatVolume(row.avg_volume_1m)}</td>
              <td className="numeric">{formatPrice(row.boll_upper)}</td>
              <td className="numeric">{formatPrice(row.boll_mid)}</td>
              <td className="numeric">{formatPrice(row.boll_lower)}</td>
              <td>{row.ma20_direction ?? "-"}</td>
              <td className="numeric">{formatAtr14(row.atr14)}</td>
              <td className="numeric">{formatPrice(row.previous_10d_low)}</td>
              <td className="numeric">{formatPrice(row.previous_10d_high)}</td>
              <td>{row.has_reversal_trend ?? "-"}</td>
              <td>{row.is_suitable_for_entry ?? "-"}</td>
              <td className="numeric">{formatPercent(row.break_percent)}</td>
              <td>{row.data_time}</td>
            </tr>
          ))}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={emptyColSpan} className="empty">
                暂无符合条件的股票
              </td>
            </tr>
          )}
          {loading && (
            <tr>
              <td colSpan={emptyColSpan} className="empty">
                正在加载筛选结果
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function formatSignal(signal: ScreeningRow["signal_type"]) {
  if (signal === "upper_breakout") return "上穿 BOLL";
  if (signal === "lower_breakdown") return "下击 BOLL";
  return "无信号";
}

function formatPrice(value: number | null) {
  if (value === null) return "-";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 }).format(value);
}

function formatAtr14(value: number | null) {
  if (value === null) return "-";
  return value.toFixed(2);
}

function formatLargeMoney(value: number) {
  if (value >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(2)}万亿`;
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(0)}亿`;
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatVolume(value: number) {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}亿`;
  if (value >= 10_000) return `${(value / 10_000).toFixed(0)}万`;
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatPercent(value: number | null) {
  if (value === null) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export default App;
