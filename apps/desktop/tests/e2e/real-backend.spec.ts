
import { test, expect, type Page } from "@playwright/test";
import { SIMULATOR_SCRIPT } from "./fixtures/rust-simulator";

test.describe("Real Backend Logic (Simulated)", () => {
  test.beforeEach(async ({ page }) => {
    // Inject the robust simulator instead of the simple mock
    await page.addInitScript(SIMULATOR_SCRIPT);
    await page.goto("/");
  });

  test("Chat Turn Success - Echo Tool", async ({ page }) => {
    await expect(page.getByTestId("page-chat")).toBeVisible();

    // 1. Send an explicit tool command that the simulator recognizes
    const toolCmd = `/tool shell.exec {"command":"echo", "args":["hello", "world"]}`;
    await page.getByTestId("chat-input").fill(toolCmd);
    await page.getByTestId("chat-send").click();

    // 2. Validate User Message appears
    await expect(page.getByText(toolCmd)).toBeVisible();

    // 3. Validate Engine Response (Simulator output)
    await expect(page.locator('[data-testid^="chat-line-"]').getByText("tool echo 执行成功")).toBeVisible();
    await expect(page.locator('[data-testid^="chat-line-"]').getByText("hello world")).toBeVisible();

    // 4. Validate Inspector details (Structured Events)
    const inspector = page.getByTestId("chat-inspector");
    await expect(inspector).toContainText("engine.turn");
    await expect(inspector).toContainText("toolOk");
    await expect(inspector).toContainText("true");
    await expect(inspector).toContainText("toolAttempts");
    await expect(inspector).toContainText("1");
  });

  test("Chat Turn Failure - Provider Error & Recovery", async ({ page }) => {
    await expect(page.getByTestId("page-chat")).toBeVisible();

    // 1. Trigger a provider timeout scenario
    const errorCmd = `/tool shell.exec {"command":"__provider_error_retry__"}`;
    await page.getByTestId("chat-input").fill(errorCmd);
    await page.getByTestId("chat-send").click();

    // 2. Validate Error Events in Inspector
    const inspector = page.getByTestId("chat-inspector");
    
    // Should show the specific structured error from backend
    await expect(inspector).toContainText("provider.call.error");
    await expect(inspector).toContainText("provider run timeout");
    await expect(inspector).toContainText("ERR_PROVIDER_CALL");
    
    // Should show retry attempts
    await expect(inspector).toContainText("toolAttempts");
    await expect(inspector).toContainText("2");
    await expect(inspector).toContainText("max_attempts_reached");

    // 3. Validate UI didn't crash and shows the final output
    await expect(page.locator('[data-testid^="chat-line-"]').getByText("provider run timeout")).toBeVisible();
  });

  test("Chat Turn Failure - Complex Multi-Stage Errors", async ({ page }) => {
     await expect(page.getByTestId("page-chat")).toBeVisible();

     // 1. Trigger complex error chain
     const errorCmd = `/tool shell.exec {"command":"__emit_errors__"}`;
     await page.getByTestId("chat-input").fill(errorCmd);
     await page.getByTestId("chat-send").click();

     // 2. Validate Corrector Error
     const inspector = page.getByTestId("chat-inspector");
     await expect(inspector).toContainText("corrector.validate_tool_result.error");
     await expect(inspector).toContainText("validator unavailable");
     await expect(inspector).toContainText("ERR_CORRECTOR_VALIDATE_TOOL_RESULT");

     // 3. Validate Memory Error
     await expect(inspector).toContainText("memory.extract.error");
     await expect(inspector).toContainText("apply mutation plan failed");
     await expect(inspector).toContainText("ERR_MEMORY_EXTRACT_APPLY_PLAN");
     
     // 4. Validate Final State
     await expect(page.locator('[data-testid^="chat-line-"]').getByText("tool execution failed")).toBeVisible();
  });
  
  test("Session Management - Real Persistence Simulation", async ({ page }) => {
      // 1. Check default session
      await expect(page.getByTestId("page-chat")).toBeVisible();
      await expect(page.getByTestId("session-default")).toBeVisible();
      
      // 2. Create new session (via UI if button exists, or simulating backend event)
      // The current UI might not have a "Create Session" button visible or hooked up to backend in the same way.
      // But we can check if switching sessions works with the simulator's state.
      
      // Actually, the sidebar lists sessions from `listSessions`.
      // Our simulator has "default". 
      // Let's rely on the fact that if we use the simulator, the state is in memory.
      
      // Send a message
      await page.getByTestId("chat-input").fill("msg1");
      await page.getByTestId("chat-send").click();
      
      // Verify user message (bg-foreground)
      await expect(page.locator('.bg-foreground').getByText("msg1")).toBeVisible();
      
      // 3. Switch to Session 2
      await page.getByTestId("session-s2").click();
      await expect(page.locator('.bg-foreground').getByText("msg1")).not.toBeVisible();
      
      // 4. Switch back to Default
      await page.getByTestId("session-default").click();
      await expect(page.locator('.bg-foreground').getByText("msg1")).toBeVisible(); // Persistence within session lifecycle
  });
});
