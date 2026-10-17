import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  timeout: 45000,
  use: {
    baseURL: process.env.WORKFORCE_BASE_URL ?? "http://localhost:8080",
    browserName: "chromium",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
      args: process.env.WORKFORCE_BROWSER_NO_SANDBOX === "1" ? ["--no-sandbox"] : [],
    },
  },
  reporter: "line",
  workers: 1,
});
