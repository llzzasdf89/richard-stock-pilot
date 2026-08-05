import { App as AntdApp } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  fetchDailyScreenings,
  fetchIntradayScreenings,
  fetchMessagePushSettings,
  saveMessagePushSettings,
  type MessagePushSettings as MessagePushSettingsData,
  type ScreeningPayload
} from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchDailyScreenings: vi.fn(),
    fetchIntradayScreenings: vi.fn(),
    fetchMessagePushSettings: vi.fn(),
    saveMessagePushSettings: vi.fn()
  };
});

const databaseSettings: MessagePushSettingsData = {
  interval_minutes: 60,
  min_market_cap: 200_000_000_000,
  min_avg_volume: 10_000_000,
  updated_at: "2026-07-31T10:00:00+08:00"
};

const emptyScreeningPayload: ScreeningPayload = {
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 0,
  results: []
};

function renderApp(initialTab?: "daily" | "intraday" | "settings") {
  return render(
    <AntdApp>
      <App initialTab={initialTab} />
    </AntdApp>
  );
}

async function changeIntervalTo70(user: ReturnType<typeof userEvent.setup>) {
  const slider = await screen.findByRole("slider", { name: "推送间隔" });
  await user.click(slider);
  fireEvent.keyDown(slider, { key: "ArrowRight", keyCode: 39 });
  expect(screen.getByRole("slider", { name: "推送间隔" })).toHaveAttribute(
    "aria-valuenow",
    "70"
  );
}

describe("MessagePushSettings", () => {
  beforeEach(() => {
    vi.mocked(fetchDailyScreenings).mockReset();
    vi.mocked(fetchIntradayScreenings).mockReset();
    vi.mocked(fetchMessagePushSettings).mockReset();
    vi.mocked(saveMessagePushSettings).mockReset();
    vi.mocked(fetchDailyScreenings).mockResolvedValue(emptyScreeningPayload);
    vi.mocked(fetchIntradayScreenings).mockResolvedValue(emptyScreeningPayload);
    vi.mocked(fetchMessagePushSettings).mockResolvedValue(databaseSettings);
    vi.mocked(saveMessagePushSettings).mockResolvedValue(databaseSettings);
  });

  it("reloads database settings every time the tab is entered", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("tab", { name: "后台消息设置" }));
    await screen.findByRole("slider", { name: "推送间隔" });
    expect(fetchMessagePushSettings).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("tab", { name: "日线筛选" }));
    await user.click(screen.getByRole("tab", { name: "后台消息设置" }));

    await waitFor(() => {
      expect(fetchMessagePushSettings).toHaveBeenCalledTimes(2);
    });
  });

  it("shows no settings values after a failed load and retries the database request", async () => {
    vi.mocked(fetchMessagePushSettings)
      .mockRejectedValueOnce(new Error("数据库暂时不可用"))
      .mockResolvedValueOnce(databaseSettings);
    const user = userEvent.setup();

    renderApp("settings");

    expect(await screen.findByRole("alert")).toHaveTextContent("配置读取失败");
    expect(screen.getByRole("alert")).toHaveTextContent("数据库暂时不可用");
    expect(screen.queryByRole("slider", { name: "推送间隔" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /重\s*试/ }));

    expect(await screen.findByRole("slider", { name: "推送间隔" })).toHaveAttribute(
      "aria-valuenow",
      "60"
    );
    expect(fetchMessagePushSettings).toHaveBeenCalledTimes(2);
  });

  it("keeps a failed-save draft and resets it from the database on re-entry", async () => {
    vi.mocked(saveMessagePushSettings).mockRejectedValueOnce(new Error("保存失败"));
    const user = userEvent.setup();
    renderApp("settings");

    await changeIntervalTo70(user);
    await user.click(screen.getByRole("button", { name: "保存设置" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("配置保存失败");
    expect(screen.getByRole("slider", { name: "推送间隔" })).toHaveAttribute(
      "aria-valuenow",
      "70"
    );

    await user.click(screen.getByRole("tab", { name: "日线筛选" }));
    await user.click(screen.getByRole("tab", { name: "后台消息设置" }));

    await waitFor(() => {
      expect(fetchMessagePushSettings).toHaveBeenCalledTimes(2);
      expect(screen.getByRole("slider", { name: "推送间隔" })).toHaveAttribute(
        "aria-valuenow",
        "60"
      );
    });
  });

  it("saves the complete draft and replaces it with the server response", async () => {
    vi.mocked(saveMessagePushSettings).mockResolvedValueOnce({
      interval_minutes: 80,
      min_market_cap: 250_000_000_000,
      min_avg_volume: 12_000_000,
      updated_at: "2026-07-31T10:05:00+08:00"
    });
    const user = userEvent.setup();
    renderApp("settings");

    await changeIntervalTo70(user);
    await user.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() => {
      expect(saveMessagePushSettings).toHaveBeenCalledWith({
        interval_minutes: 70,
        min_market_cap: 200_000_000_000,
        min_avg_volume: 10_000_000
      });
    });
    expect(await screen.findByText("设置已保存，将从下一个固定钟点生效")).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "推送间隔" })).toHaveAttribute(
      "aria-valuenow",
      "80"
    );
    expect(screen.getByRole("slider", { name: "最低市值" })).toHaveAttribute(
      "aria-valuenow",
      "250000000000"
    );
    expect(screen.getByRole("slider", { name: "最低月均成交量" })).toHaveAttribute(
      "aria-valuenow",
      "12000000"
    );
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
  });

  it("does not request stock screening while settings is active", async () => {
    renderApp("settings");

    expect(
      await screen.findByRole("tab", { name: "后台消息设置", selected: true })
    ).toBeInTheDocument();
    await screen.findByRole("slider", { name: "推送间隔" });
    expect(fetchDailyScreenings).not.toHaveBeenCalled();
    expect(fetchIntradayScreenings).not.toHaveBeenCalled();
  });
});
