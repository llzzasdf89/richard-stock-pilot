import { useEffect, useMemo, useRef, useState } from "react";
import { Alert } from "antd";
import {
  fetchDailyScreenings,
  fetchIntradayScreenings,
  type ScreeningFilters as ScreeningFilterValues,
  type ScreeningPayload,
  type TabKey
} from "../api";
import { AVG_VOLUME_SPEC, MARKET_CAP_SPEC } from "../filterSpecifications";
import ScreeningFilters from "./ScreeningFilters";
import ScreeningTable from "./ScreeningTable";

const DEFAULT_FILTERS: ScreeningFilterValues = {
  market: "US",
  min_market_cap: MARKET_CAP_SPEC.defaultValue,
  min_avg_volume: AVG_VOLUME_SPEC.defaultValue,
  interval: "5m",
  page: 1,
  page_size: 20
};

export interface ScreeningStatus {
  loading: boolean;
  meta: string;
}

interface ScreeningWorkspaceProps {
  mode: TabKey;
  onStatusChange?: (status: ScreeningStatus) => void;
}

export default function ScreeningWorkspace({
  mode,
  onStatusChange
}: ScreeningWorkspaceProps) {
  const [filters, setFilters] = useState<ScreeningFilterValues>(DEFAULT_FILTERS);
  const [data, setData] = useState<ScreeningPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intradayRequestSeq = useRef(0);

  useEffect(() => {
    if (mode !== "daily") return;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      fetchDailyScreenings(filters)
        .then((payload) => {
          if (!cancelled) setData(payload);
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
  }, [filters, mode]);

  useEffect(() => {
    if (mode !== "intraday") return;

    void requestIntraday(filters);
    return () => {
      intradayRequestSeq.current += 1;
    };
  }, [mode]);

  const meta = useMemo(() => {
    if (mode === "daily") {
      return data?.data_date ? `数据日期：${data.data_date}` : "等待日线数据";
    }
    return data?.refreshed_at
      ? `刷新时间：${formatDateTime(data.refreshed_at)}`
      : "点击按钮刷新分时数据";
  }, [data, mode]);

  useEffect(() => {
    onStatusChange?.({ loading, meta });
  }, [loading, meta, onStatusChange]);

  function updateFilters(next: Partial<ScreeningFilterValues>) {
    const nextFilters = { ...filters, ...next, page: next.page ?? 1 };
    const changedKeys = Object.keys(next);
    const isPageOnlyChange = changedKeys.length === 1 && changedKeys[0] === "page";
    const shouldClearData = changedKeys.some((key) => key !== "page");

    if (shouldClearData) {
      intradayRequestSeq.current += 1;
      setData(null);
      setError(null);
    }

    setFilters(nextFilters);
    if (mode === "intraday" && isPageOnlyChange && data) {
      void requestIntraday(nextFilters);
    }
  }

  async function requestIntraday(nextFilters: ScreeningFilterValues) {
    const requestSeq = ++intradayRequestSeq.current;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchIntradayScreenings(nextFilters);
      if (requestSeq === intradayRequestSeq.current) {
        setData(payload);
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

  return (
    <div className="screening-workspace">
      <ScreeningFilters
        filters={filters}
        mode={mode}
        loading={loading}
        onChange={updateFilters}
        onRefreshIntraday={() => requestIntraday(filters)}
      />

      {error && (
        <Alert
          className="screening-error"
          type="error"
          showIcon
          title="筛选请求失败"
          description={error}
        />
      )}

      <ScreeningTable
        data={data}
        filters={filters}
        loading={loading}
        mode={mode}
        onPageChange={(page) => updateFilters({ page })}
      />
    </div>
  );
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
