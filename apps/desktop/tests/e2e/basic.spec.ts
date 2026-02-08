import { test, expect } from "@playwright/test";
import { SIMULATOR_SCRIPT } from "./fixtures/rust-simulator";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(SIMULATOR_SCRIPT);
  await page.goto("/");
});

test("topbar should keep global controls without model badge", async ({ page }) => {
  await expect(page.getByTestId("topbar-new")).toBeVisible();
  await expect(page.getByTestId("topbar-gateway-toggle")).toBeVisible();
  await expect(page.getByTestId("topbar-kill")).toBeVisible();
  await expect(page.getByTestId("topbar-model")).toHaveCount(0);
});

test("settings locale toggle should still work", async ({ page }) => {
  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("page-settings")).toBeVisible();

  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByTestId("nav-chat")).toHaveAttribute("aria-label", "Chat");

  await page.getByRole("button", { name: "中文" }).click();
  await expect(page.getByTestId("nav-chat")).toHaveAttribute("aria-label", "对话");
});

test("chat should keep messages by session", async ({ page }) => {
  await expect(page.getByTestId("page-chat")).toBeVisible();

  await page.getByTestId("chat-input").fill("hello default");
  await page.getByTestId("chat-send").click();
  await expect(
    page.locator('[data-testid^="chat-line-"]').filter({ hasText: "hello default" }).first(),
  ).toBeVisible();

  await page.getByTestId("session-s2").click();
  await page.getByTestId("chat-input").fill("hello s2");
  await page.getByTestId("chat-send").click();
  await expect(
    page.locator('[data-testid^="chat-line-"]').filter({ hasText: "hello s2" }).first(),
  ).toBeVisible();

  await page.getByTestId("session-default").click();
  await expect(
    page.locator('[data-testid^="chat-line-"]').filter({ hasText: "hello default" }).first(),
  ).toBeVisible();
});

test("settings logs modal should open, switch tabs and close", async ({ page }) => {
  await page.getByTestId("nav-settings").click();
  await page.getByTestId("settings-open-logs").click();

  await expect(page.getByTestId("settings-logs-modal")).toBeVisible();
  await page.getByTestId("settings-logs-tab-runtime").click();
  await page.getByTestId("settings-logs-tab-audit").click();

  await page.keyboard.press("Escape");
  await expect(page.getByTestId("settings-logs-modal")).toHaveCount(0);
});

test("logs modal should show runtime and audit entries", async ({ page }) => {
  await page.getByTestId("chat-input").fill('/tool shell.exec {"command":"__provider_error_retry__"}');
  await page.getByTestId("chat-send").click();

  await page.getByTestId("nav-settings").click();
  await page.getByTestId("settings-open-logs").click();

  await page.getByTestId("settings-logs-tab-runtime").click();
  await expect(page.getByTestId("settings-logs-modal")).toContainText("engine.turn");

  await page.getByTestId("settings-logs-tab-audit").click();
  await expect(page.getByTestId("settings-logs-modal")).toContainText("provider.call.error");

  await page.mouse.click(5, 5);
  await expect(page.getByTestId("settings-logs-modal")).toHaveCount(0);
});
