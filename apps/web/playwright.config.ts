import { defineConfig, devices } from "@playwright/test";

// The E2E suite runs against a dedicated API (port 8001, fresh SQLite, mock AI) and a Vite dev
// server (port 5174) proxying /api to it, so it never touches your dev database or a real AI provider.
const API_PORT = process.env.E2E_API_PORT ?? "8001";
const WEB_PORT = 5174;
// E2E_BASE_URL=http://localhost:8080 runs the suite against an already-running stack (e.g. Docker Compose).
const EXTERNAL = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: EXTERNAL ?? `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // E2E_CHANNEL=chrome (or msedge) uses an installed browser instead of Playwright's bundled Chromium.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], ...(process.env.E2E_CHANNEL ? { channel: process.env.E2E_CHANNEL } : {}) } }],
  webServer: EXTERNAL
    ? undefined
    : [
    {
      command: "node e2e/start-api.mjs",
      url: `http://127.0.0.1:${API_PORT}/healthz`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { VITE_API_PROXY: `http://127.0.0.1:${API_PORT}` },
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
