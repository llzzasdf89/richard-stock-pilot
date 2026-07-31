import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchDailyScreenings,
  fetchIntradayScreenings,
  type ScreeningPayload,
  type ScreeningRow
} from "../api";
import ScreeningWorkspace from "./ScreeningWorkspace";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchDailyScreenings: vi.fn(),
    fetchIntradayScreenings: vi.fn()
  };
});

const stock: ScreeningRow = {
  symbol: "AAPL.US",
  name: "Apple",
  market: "US",
  currency: "USD",
  earnings_date: "2026-08-05",
  trade_date: "2026-07-31",
  interval: "5m",
  close: 208.125,
  latest_price: 209.375,
  market_cap: 3_120_000_000_000,
  avg_volume_1m: 56_400_000,
  boll_upper: 212.4567,
  boll_mid: 202.5,
  boll_lower: 192.5432,
  ma20_direction: "上升",
  z_score: -1.754,
  atr14: 4.267,
  previous_10d_low: 193.1111,
  previous_10d_high: 211.9999,
  has_reversal_trend: "是",
  is_suitable_for_entry: "是",
  data_time: "2026-07-31T10:30:00+08:00"
};

function payload(overrides: Partial<ScreeningPayload> = {}): ScreeningPayload {
  return {
    data_date: "2026-07-31",
    refreshed_at: "2026-07-31T10:30:00+08:00",
    interval: "5m",
    page: 1,
    page_size: 20,
    total: 21,
    total_pages: 2,
    results: [stock],
    ...overrides
  };
}

const dailyColumns = [
  "代码",
  "名称",
  "市场",
  "货币",
  "近期财报日期（未来几天内）",
  "收盘价",
  "市值",
  "月均成交量",
  "BOLL 上轨价格",
  "BOLL 中轨价格",
  "BOLL 下轨价格",
  "MA20均线方向",
  "Z-Score",
  "平均波动幅度 ATR14",
  "前10个交易日最低点",
  "前10个交易日最高点",
  "是否存在逆转趋势",
  "是否适合建仓",
  "数据时间"
];

describe("ScreeningWorkspace", () => {
  beforeEach(() => {
    vi.mocked(fetchDailyScreenings).mockReset();
    vi.mocked(fetchIntradayScreenings).mockReset();
    vi.mocked(fetchDailyScreenings).mockResolvedValue(payload());
    vi.mocked(fetchIntradayScreenings).mockResolvedValue(payload());
  });

  it("shows every daily stock column, preserves formatting, and paginates through Table", async () => {
    const user = userEvent.setup();

    render(<ScreeningWorkspace mode="daily" />);

    expect(await screen.findByText("AAPL.US")).toBeInTheDocument();
    for (const column of dailyColumns) {
      expect(screen.getByRole("columnheader", { name: column })).toBeInTheDocument();
    }
    expect(screen.getByText("3.12万亿")).toBeInTheDocument();
    expect(screen.getByText("5640万")).toBeInTheDocument();
    expect(screen.getByText("-1.75")).toBeInTheDocument();
    expect(screen.getByText("4.27")).toBeInTheDocument();
    expect(screen.getByText("193.111")).toBeInTheDocument();
    expect(screen.getByText("212.457")).toBeInTheDocument();
    expect(screen.getByText("共 21 条")).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "最低市值" })).toHaveAttribute(
      "aria-valuenow",
      "200000000000"
    );
    expect(screen.getByRole("slider", { name: "最低月均成交量" })).toHaveAttribute(
      "aria-valuenow",
      "10000000"
    );

    await user.click(screen.getByTitle("2"));

    await waitFor(() => {
      expect(fetchDailyScreenings).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2, page_size: 20 })
      );
    });
  });

  it("keeps intraday filter changes pending until the refresh button", async () => {
    const user = userEvent.setup();

    render(<ScreeningWorkspace mode="intraday" />);

    expect(await screen.findByText("AAPL.US")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "昨日收盘价" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "最新价格" })).toBeInTheDocument();
    expect(fetchIntradayScreenings).toHaveBeenCalledTimes(1);

    await user.click(screen.getByText("港股"));
    expect(fetchIntradayScreenings).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "刷新分时数据" }));

    await waitFor(() => {
      expect(fetchIntradayScreenings).toHaveBeenCalledTimes(2);
      expect(fetchIntradayScreenings).toHaveBeenLastCalledWith(
        expect.objectContaining({ market: "HK", page: 1 })
      );
    });
  });

  it("shows request failures in an alert and an empty result through the table", async () => {
    vi.mocked(fetchDailyScreenings)
      .mockRejectedValueOnce(new Error("日线请求失败"))
      .mockResolvedValueOnce(payload({ total: 0, total_pages: 0, results: [] }));
    const user = userEvent.setup();

    render(<ScreeningWorkspace mode="daily" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("日线请求失败");

    await user.click(screen.getByText("港股"));

    expect(await screen.findByText("暂无符合条件的股票")).toBeInTheDocument();
  });
});
