import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for E2E browser tests.
 *
 * Run tests with: npm run test:e2e
 * Run tests in UI mode: npx playwright test --ui
 */

export default defineConfig({
  // Test directory
  testDir: "./e2e",

  // Run all tests in parallel
  fullyParallel: true,

  // Fail build on CI if test.only is left in source
  forbidOnly: !!process.env.CI,

  // Retry failed tests on CI
  retries: process.env.CI ? 2 : 0,

  // Use 1 worker on CI, more locally
  workers: process.env.CI ? 1 : undefined,

  // Reporter configuration
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
  ],

  // Shared settings for all tests
  use: {
    // Base URL for tests
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5275",

    // Collect trace on failure
    trace: "on-first-retry",

    // Screenshot on failure
    screenshot: "only-on-failure",

    // Video on failure
    video: "on-first-retry",

    // Timeout for each action
    actionTimeout: 10000,

    // Browser context options
    contextOptions: {
      // Ignore HTTPS errors for local testing
      ignoreHTTPSErrors: true,
    },
  },

  // Configure projects for different browsers
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    // Uncomment to test on other browsers
    // {
    //   name: "firefox",
    //   use: { ...devices["Desktop Firefox"] },
    // },
    // {
    //   name: "webkit",
    //   use: { ...devices["Desktop Safari"] },
    // },
  ],

  // Local development server - not started automatically
  // Tests assume the dev server is already running
  // webServer: undefined,
});
