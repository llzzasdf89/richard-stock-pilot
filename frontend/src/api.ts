export type Market = "all" | "US" | "HK";
export type SignalType = "all" | "upper_breakout" | "lower_breakdown";
export type TabKey = "daily" | "intraday";

export interface ScreeningFilters {
  market: Market;
  signal_type: SignalType;
  min_market_cap: number;
  min_avg_volume: number;
  interval: string;
  page: number;
  page_size: number;
}

export interface ScreeningRow {
  symbol: string;
  name: string;
  market: "US" | "HK";
  currency: string;
  signal_type: "upper_breakout" | "lower_breakdown" | "none";
  trade_date?: string;
  interval?: string;
  close: number;
  latest_price: number;
  market_cap: number;
  avg_volume_1m: number;
  boll_upper: number;
  boll_mid: number;
  boll_lower: number;
  break_percent: number | null;
  data_time: string;
}

export interface ScreeningPayload {
  data_date?: string | null;
  refreshed_at?: string | null;
  interval?: string;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  results: ScreeningRow[];
}

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  code: number;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function fetchDailyScreenings(filters: ScreeningFilters): Promise<ScreeningPayload> {
  return fetchScreenings("/api/daily-screenings", filters);
}

export async function fetchIntradayScreenings(filters: ScreeningFilters): Promise<ScreeningPayload> {
  return fetchScreenings("/api/intraday-screenings", filters);
}

async function fetchScreenings(path: string, filters: ScreeningFilters): Promise<ScreeningPayload> {
  const params = new URLSearchParams({
    market: filters.market,
    signal_type: filters.signal_type,
    min_market_cap: String(filters.min_market_cap),
    min_avg_volume: String(filters.min_avg_volume),
    page: String(filters.page),
    page_size: String(filters.page_size)
  });

  if (path.includes("intraday")) {
    params.set("interval", filters.interval);
  }

  const requestId = crypto.randomUUID();
  const response = await fetch(`${API_BASE}${path}?${params.toString()}`, {
    headers: {
      "X-Request-ID": requestId
    }
  });
  const body = (await response.json()) as ApiResponse<ScreeningPayload | { message: string; request_id: string }>;

  if (!body.success || body.code !== 200) {
    const errorData = body.data as { message?: string; request_id?: string };
    throw new Error(`${errorData.message ?? "请求失败"}，请求ID：${errorData.request_id ?? requestId}`);
  }

  return body.data as ScreeningPayload;
}
