export type Market = "US" | "HK";
export type TabKey = "daily" | "intraday";

export interface ScreeningFilters {
  market: Market;
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
  earnings_date: string | null;
  trade_date?: string;
  interval?: string;
  close: number;
  latest_price: number;
  market_cap: number;
  avg_volume_1m: number;
  boll_upper: number;
  boll_mid: number;
  boll_lower: number;
  ma20_direction: "上升" | "下降" | "横盘" | "-" | null;
  z_score: number | null;
  atr14: number | null;
  previous_10d_low: number | null;
  previous_10d_high: number | null;
  has_reversal_trend: "是" | "否" | null;
  is_suitable_for_entry: "是" | "否" | null;
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

export interface MessagePushSettings {
  interval_minutes: number;
  min_market_cap: number;
  min_avg_volume: number;
  updated_at?: string | null;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function fetchDailyScreenings(filters: ScreeningFilters): Promise<ScreeningPayload> {
  return fetchScreenings("/api/daily-screenings", filters);
}

export async function fetchIntradayScreenings(filters: ScreeningFilters): Promise<ScreeningPayload> {
  return fetchScreenings("/api/intraday-screenings", filters);
}

export async function fetchMessagePushSettings(): Promise<MessagePushSettings> {
  return requestApi("/api/message-push-settings");
}

export async function saveMessagePushSettings(settings: MessagePushSettings): Promise<MessagePushSettings> {
  return requestApi("/api/message-push-settings", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      interval_minutes: settings.interval_minutes,
      min_market_cap: settings.min_market_cap,
      min_avg_volume: settings.min_avg_volume
    })
  });
}

async function fetchScreenings(path: string, filters: ScreeningFilters): Promise<ScreeningPayload> {
  const params = new URLSearchParams({
    market: filters.market,
    min_market_cap: String(filters.min_market_cap),
    min_avg_volume: String(filters.min_avg_volume),
    page: String(filters.page),
    page_size: String(filters.page_size)
  });

  if (path.includes("intraday")) {
    params.set("interval", filters.interval);
  }

  return requestApi(`${path}?${params.toString()}`);
}

async function requestApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const requestId = crypto.randomUUID();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      "X-Request-ID": requestId
    }
  });
  const body = (await response.json()) as ApiResponse<T | { message: string; request_id: string }>;

  if (!body.success || body.code !== 200) {
    const errorData = body.data as { message?: string; request_id?: string };
    throw new Error(`${errorData.message ?? "请求失败"}，请求ID：${errorData.request_id ?? requestId}`);
  }

  return body.data as T;
}
