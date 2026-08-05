import { useEffect, useRef, useState } from "react";
import { Button, Segmented, Slider } from "antd";
import type { Market, ScreeningFilters as ScreeningFilterValues } from "../api";
import {
  AVG_VOLUME_SPEC,
  MARKET_CAP_SPEC,
  formatLargeMoney,
  formatVolume
} from "../filterSpecifications";

const marketOptions: Array<{ value: Market; label: string }> = [
  { value: "US", label: "美股" },
  { value: "HK", label: "港股" }
];

interface ScreeningFiltersProps {
  filters: ScreeningFilterValues;
  mode: "daily" | "intraday";
  loading: boolean;
  onChange: (next: Partial<ScreeningFilterValues>) => void;
  onRefreshIntraday: () => void;
}

export default function ScreeningFilters({
  filters,
  mode,
  loading,
  onChange,
  onRefreshIntraday
}: ScreeningFiltersProps) {
  const [marketCap, setMarketCap] = useState(filters.min_market_cap);
  const [avgVolume, setAvgVolume] = useState(filters.min_avg_volume);
  const marketCapTimer = useRef<number | null>(null);
  const avgVolumeTimer = useRef<number | null>(null);

  useEffect(() => {
    setMarketCap(filters.min_market_cap);
    setAvgVolume(filters.min_avg_volume);
  }, [filters.min_avg_volume, filters.min_market_cap]);

  useEffect(() => {
    return () => {
      if (marketCapTimer.current !== null) window.clearTimeout(marketCapTimer.current);
      if (avgVolumeTimer.current !== null) window.clearTimeout(avgVolumeTimer.current);
    };
  }, []);

  function updateMarketCap(value: number) {
    setMarketCap(value);
    if (marketCapTimer.current !== null) window.clearTimeout(marketCapTimer.current);
    marketCapTimer.current = window.setTimeout(() => {
      onChange({ min_market_cap: value });
    }, 600);
  }

  function updateAvgVolume(value: number) {
    setAvgVolume(value);
    if (avgVolumeTimer.current !== null) window.clearTimeout(avgVolumeTimer.current);
    avgVolumeTimer.current = window.setTimeout(() => {
      onChange({ min_avg_volume: value });
    }, 600);
  }

  return (
    <div className="filters">
      <div className="filter-control filter-market">
        <span className="filter-heading">市场</span>
        <Segmented
          aria-label="市场"
          block
          options={marketOptions}
          value={filters.market}
          onChange={(market) => onChange({ market: market as Market })}
        />
      </div>

      <div className="filter-control">
        <span className="filter-heading">
          <span>最低市值</span>
          <strong className="filter-value">{formatLargeMoney(marketCap)}</strong>
        </span>
        <Slider
          ariaLabelForHandle="最低市值"
          min={MARKET_CAP_SPEC.min}
          max={MARKET_CAP_SPEC.max}
          step={MARKET_CAP_SPEC.step}
          value={marketCap}
          tooltip={{ formatter: (value) => (value === undefined ? "" : formatLargeMoney(value)) }}
          onChange={updateMarketCap}
        />
      </div>

      <div className="filter-control">
        <span className="filter-heading">
          <span>最低月均成交量</span>
          <strong className="filter-value">{formatVolume(avgVolume)}</strong>
        </span>
        <Slider
          ariaLabelForHandle="最低月均成交量"
          min={AVG_VOLUME_SPEC.min}
          max={AVG_VOLUME_SPEC.max}
          step={AVG_VOLUME_SPEC.step}
          value={avgVolume}
          tooltip={{ formatter: (value) => (value === undefined ? "" : formatVolume(value)) }}
          onChange={updateAvgVolume}
        />
      </div>

      {mode === "intraday" && (
        <Button type="primary" loading={loading} onClick={onRefreshIntraday}>
          刷新分时数据
        </Button>
      )}
    </div>
  );
}
