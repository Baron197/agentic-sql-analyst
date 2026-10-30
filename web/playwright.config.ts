import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { defineConfig, devices } from "@playwright/test";

// The smoke test signs in as the demo analyst. Its password comes from the environment (CI)
// or the repo's .env (local); it is never printed, and traces (which record typed text) are off.
function demoPassword(): string {
  if (process.env.DEMO_ANALYST_PASSWORD) return process.env.DEMO_ANALYST_PASSWORD;
  try {
    const env = readFileSync(resolve(import.meta.dirname, "..", ".env"), "utf-8");
    return /^DEMO_ANALYST_PASSWORD=(.*)$/m.exec(env)?.[1].trim() ?? "";
  } catch {
    return "";
  }
}
process.env.DEMO_ANALYST_PASSWORD = demoPassword();

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Postgres must already be running with the data, index, and app schema (`uv run poe db-reset`).
  webServer: [
    {
      command: "uv run poe api",
      cwd: "..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
