import { test, expect } from "@playwright/test";
import { SIMULATOR_SCRIPT } from "./fixtures/rust-simulator";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(SIMULATOR_SCRIPT);
  await page.goto("/");
});

test("error chain should be visible in runtime logs", async ({ page }) => {
  await page.getByTestId("chat-input").fill('/tool shell.exec {"command":"__emit_errors__"}');
  await page.getByTestId("chat-send").click();

  await page.getByTestId("nav-settings").click();
  await page.getByTestId("settings-open-logs").click();
  await page.getByTestId("settings-logs-tab-runtime").click();

  const modal = page.getByTestId("settings-logs-modal");
  await expect(modal).toContainText("corrector.validate_tool_result.error");
  await expect(modal).toContainText("memory.extract.error");
});

test("gateway toggle and kill buttons should call different commands", async ({ page }) => {
  await page.getByTestId("topbar-gateway-toggle").click();
  await page.getByTestId("topbar-kill").click();

  const trace = await page.evaluate(() => {
    const win = window as unknown as { __TAURI_MOCK_TRACE__?: string[] };
    return Array.isArray(win.__TAURI_MOCK_TRACE__) ? win.__TAURI_MOCK_TRACE__ : [];
  });

  expect(trace).toContain("gateway_start");
  expect(trace).toContain("kill_switch_stop_all");
});
