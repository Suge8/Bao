import { test, expect } from "@playwright/test";

test("open -> chat -> switch tabs -> settings -> toggle language", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("topbar-title")).toBeVisible();

  await expect(page.getByTestId("page-chat")).toBeVisible();
  await page.getByTestId("nav-tasks").click();
  await expect(page.getByTestId("page-tasks")).toBeVisible();

  await page.getByTestId("nav-dimsums").click();
  await expect(page.getByTestId("page-dimsums")).toBeVisible();

  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("page-settings")).toBeVisible();

  // Toggle language: zh -> en
  await page.getByRole("button", { name: /en/i }).click();
  await expect(page.getByTestId("nav-chat")).toHaveAttribute("aria-label", "Chat");

  // Toggle back: en -> zh
  await page.getByRole("button", { name: /zh/i }).click();
  await expect(page.getByTestId("nav-chat")).toHaveAttribute("aria-label", "对话");
});
