import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";

const frontendDir = process.cwd();
const loadConfigScript = `
  import { loadConfigFromFile } from "vite";
  const loaded = await loadConfigFromFile(
    { command: "serve", mode: "development" },
    "vite.config.ts"
  );
  if (!loaded) throw new Error("Vite config did not load");
  console.log(loaded.config.server.proxy["/api"]);
`;

function loadProxyTarget(backendPort?: string) {
  const env = { ...process.env };
  if (backendPort === undefined) {
    delete env.VITE_BACKEND_PORT;
  } else {
    env.VITE_BACKEND_PORT = backendPort;
  }

  return execFileSync(
    process.execPath,
    ["--input-type=module", "-e", loadConfigScript],
    { cwd: frontendDir, env, encoding: "utf-8" }
  ).trim();
}

describe("Vite API proxy", () => {
  it("targets the custom backend port from the startup environment", () => {
    expect(loadProxyTarget("8010")).toBe("http://127.0.0.1:8010");
  });

  it("defaults to backend port 8000 when no custom port is provided", () => {
    expect(loadProxyTarget()).toBe("http://127.0.0.1:8000");
  });
});
