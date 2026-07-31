import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchMessagePushSettings,
  saveMessagePushSettings,
  type MessagePushSettings
} from "./api";

const savedSettings: MessagePushSettings = {
  interval_minutes: 30,
  min_market_cap: 250_000_000_000,
  min_avg_volume: 12_000_000
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" }
  });
}

describe("message push settings API", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads saved message push settings", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ success: true, code: 200, data: savedSettings })
    );

    await expect(fetchMessagePushSettings()).resolves.toEqual(savedSettings);
    expect(fetch).toHaveBeenCalledWith(
      "/api/message-push-settings",
      expect.objectContaining({ headers: expect.any(Object) })
    );
  });

  it("saves the complete settings object", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ success: true, code: 200, data: savedSettings })
    );

    await expect(saveMessagePushSettings(savedSettings)).resolves.toEqual(savedSettings);
    expect(fetch).toHaveBeenCalledWith(
      "/api/message-push-settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          interval_minutes: 30,
          min_market_cap: 250_000_000_000,
          min_avg_volume: 12_000_000
        })
      })
    );
  });
});
