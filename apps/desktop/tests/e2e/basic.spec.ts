import { test, expect, type Page } from "@playwright/test";

async function installTauriMock(page: Page) {
  await page.addInitScript(() => {
    type CallbackRecord = {
      callback: (payload: unknown) => void;
      once: boolean;
    };

    const callbacks = new Map<number, CallbackRecord>();
    const eventListeners = new Map<string, Map<number, number>>();

    let callbackSeq = 1;
    let listenerSeq = 1;
    let baoEventSeq = 100;

    const emitEvent = (eventName: string, payload: unknown) => {
      const listeners = eventListeners.get(eventName);
      if (!listeners) return;

      for (const [listenerId, callbackId] of listeners.entries()) {
        const record = callbacks.get(callbackId);
        if (!record) continue;

        record.callback({ event: eventName, id: listenerId, payload });

        if (record.once) {
          callbacks.delete(callbackId);
          listeners.delete(listenerId);
        }
      }
    };

    const mockInvoke = async (cmd: string, args?: Record<string, unknown>) => {
      if (cmd === "plugin:event|listen") {
        const event = String(args?.event ?? "");
        const callbackId = Number(args?.handler ?? 0);
        if (!eventListeners.has(event)) {
          eventListeners.set(event, new Map());
        }
        const listenerId = listenerSeq++;
        eventListeners.get(event)?.set(listenerId, callbackId);
        return listenerId;
      }

      if (cmd === "plugin:event|unlisten") {
        const event = String(args?.event ?? "");
        const listenerId = Number(args?.eventId ?? 0);
        eventListeners.get(event)?.delete(listenerId);
        return null;
      }

      if (cmd === "listSessions") {
        return {
          payload: {
            sessions: [
              { sessionId: "default", title: "Default" },
              { sessionId: "s2", title: "Session 2" },
            ],
          },
        };
      }

      if (cmd === "runEngineTurn") {
        const sessionId = String(args?.sessionId ?? "default");
        const text = String(args?.text ?? "");
        const shouldEmitErrors = text.includes("__emit_errors__");
        const providerErrorType = text.includes("__provider_unauthorized__")
          ? "unauthorized"
          : text.includes("__provider_rate_limit__")
            ? "rate_limit"
            : text.includes("__provider_timeout__") || text.includes("__provider_error_retry__")
              ? "timeout"
              : null;
        const shouldEmitProviderError = providerErrorType !== null;

        emitEvent("bao:event", {
          eventId: ++baoEventSeq,
          type: "message.send",
          ts: Date.now(),
          payload: {
            sessionId,
            text,
          },
        });

        if (shouldEmitErrors) {
          emitEvent("bao:event", {
            eventId: ++baoEventSeq,
            type: "corrector.validate_tool_result.error",
            ts: Date.now(),
            payload: {
              source: "runEngineTurn",
              stage: "corrector.validate_tool_result",
              sessionId,
              code: "ERR_CORRECTOR_VALIDATE_TOOL_RESULT",
              error: "validator unavailable",
              toolName: "shell.exec",
              attempt: 1,
            },
          });

          emitEvent("bao:event", {
            eventId: ++baoEventSeq,
            type: "memory.extract.error",
            ts: Date.now(),
            payload: {
              source: "runEngineTurn",
              stage: "memory.extract.apply_plan",
              sessionId,
              code: "ERR_MEMORY_EXTRACT_APPLY_PLAN",
              error: "apply mutation plan failed",
              planId: "plan_ui_e2e_error",
              mutationCount: 1,
            },
          });
        }

        if (shouldEmitProviderError) {
          const providerErrorMessage =
            providerErrorType === "unauthorized"
              ? "provider unauthorized"
              : providerErrorType === "rate_limit"
                ? "provider rate limit"
                : "provider run timeout";

          emitEvent("bao:event", {
            eventId: ++baoEventSeq,
            type: "provider.call.error",
            ts: Date.now(),
            payload: {
              source: "runEngineTurn",
              stage: "provider.call",
              sessionId,
              code: "ERR_PROVIDER_CALL",
              error: providerErrorMessage,
              provider: "openai",
              model: "gpt-4.1",
              attempt: 1,
            },
          });
        }

        emitEvent("bao:event", {
          eventId: ++baoEventSeq,
          type: "engine.turn",
          ts: Date.now(),
          payload: {
            sessionId,
            output: shouldEmitProviderError ? "provider 调用失败，已停止重试" : "tool shell.exec 执行失败",
            matched: true,
            needsMemory: false,
            toolName: "shell.exec",
            toolTriggered: true,
            toolOk: false,
            toolValidationOk: false,
            toolValidationError: "tool execution failed",
            toolRetryReason: "max_attempts_reached",
            toolAttempts: 2,
            providerUsed: shouldEmitProviderError ? null : null,
            memoryPlanId: shouldEmitErrors ? "plan_ui_e2e_error" : "plan_ui_e2e",
            memoryMutationCount: 1,
          },
        });

        return {
          output: shouldEmitProviderError ? "provider 调用失败，已停止重试" : "tool shell.exec 执行失败",
          matched: true,
          needsMemory: false,
          toolName: "shell.exec",
          toolTriggered: true,
          toolOk: false,
        };
      }

      if (cmd === "sendMessage") {
        return { ok: true };
      }

      return null;
    };

    (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {
      transformCallback: (callback: (payload: unknown) => void, once = false) => {
        const id = callbackSeq++;
        callbacks.set(id, { callback, once });
        return id;
      },
      unregisterCallback: (id: number) => {
        callbacks.delete(id);
      },
      invoke: mockInvoke,
    };

    (window as unknown as { __TAURI_EVENT_PLUGIN_INTERNALS__?: unknown }).__TAURI_EVENT_PLUGIN_INTERNALS__ = {
      unregisterListener: (_event: string, _eventId: number) => {},
    };
  });
}

test("open -> chat -> switch tabs -> settings -> toggle language", async ({ page }) => {
  await installTauriMock(page);

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
  await page.getByRole("button", { name: /^en(\s*\(|\s*$)/i }).click();
  await expect(page.getByTestId("nav-chat")).toHaveAttribute("aria-label", "Chat");

  // Toggle back: en -> zh
  await page.getByRole("button", { name: /^zh(\s*\(|\s*$)/i }).click();
  await expect(page.getByTestId("nav-chat")).toHaveAttribute("aria-label", "对话");
});

test("chat should keep history per session when switching", async ({ page }) => {
  await installTauriMock(page);

  await page.goto("/");
  await expect(page.getByTestId("page-chat")).toBeVisible();

  await page.evaluate(async () => {
    const tauri = (window as unknown as { __TAURI_INTERNALS__?: { invoke?: Function } })
      .__TAURI_INTERNALS__;
    if (!tauri?.invoke) return;
    await tauri.invoke("runEngineTurn", { sessionId: "default", text: "hello default" });
    await tauri.invoke("runEngineTurn", { sessionId: "s2", text: "hello s2" });
  });

  await expect(page.locator('[data-testid^="chat-line-"]').getByText("hello default")).toBeVisible();

  await page.getByTestId("session-s2").click();
  await expect(page.locator('[data-testid^="chat-line-"]').getByText("hello s2")).toBeVisible();

  await page.getByTestId("session-default").click();
  await expect(page.locator('[data-testid^="chat-line-"]').getByText("hello default")).toBeVisible();
});

test("chat inspector should show retry and memory extraction fields", async ({ page }) => {
  await installTauriMock(page);

  await page.goto("/");
  await expect(page.getByTestId("page-chat")).toBeVisible();

  await page.getByTestId("chat-input").fill('/tool shell.exec {"command":"echo hi"}');
  await page.getByTestId("chat-send").click();

  const inspector = page.getByTestId("chat-inspector");
  await expect(inspector).toContainText("engine.turn");
  await expect(inspector).toContainText("toolAttempts");
  await expect(inspector).toContainText("2");
  await expect(inspector).toContainText("toolRetryReason");
  await expect(inspector).toContainText("max_attempts_reached");
  await expect(inspector).toContainText("memoryPlanId");
  await expect(inspector).toContainText("plan_ui_e2e");
});

test("chat inspector should show corrector and memory extract errors", async ({ page }) => {
  await installTauriMock(page);

  await page.goto("/");
  await expect(page.getByTestId("page-chat")).toBeVisible();

  await page.getByTestId("chat-input").fill('/tool shell.exec {"command":"__emit_errors__"}');
  await page.getByTestId("chat-send").click();

  const inspector = page.getByTestId("chat-inspector");
  await expect(inspector).toContainText("corrector.validate_tool_result.error");
  await expect(inspector).toContainText("validator unavailable");
  await expect(inspector).toContainText("memory.extract.error");
  await expect(inspector).toContainText("apply mutation plan failed");
  await expect(inspector).toContainText("plan_ui_e2e_error");
});

test("chat inspector should show provider error with retry stop", async ({ page }) => {
  await installTauriMock(page);

  await page.goto("/");
  await expect(page.getByTestId("page-chat")).toBeVisible();

  await page.getByTestId("chat-input").fill('/tool shell.exec {"command":"__provider_error_retry__"}');
  await page.getByTestId("chat-send").click();

  const inspector = page.getByTestId("chat-inspector");
  await expect(inspector).toContainText("provider.call.error");
  await expect(inspector).toContainText("provider run timeout");
  await expect(inspector).toContainText("engine.turn");
  await expect(inspector).toContainText("toolAttempts");
  await expect(inspector).toContainText("2");
  await expect(inspector).toContainText("toolRetryReason");
  await expect(inspector).toContainText("max_attempts_reached");
  await expect(inspector).toContainText("providerUsed");
  await expect(inspector).toContainText("null");
});


test("chat inspector should show provider unauthorized with retry stop", async ({ page }) => {
  await installTauriMock(page);

  await page.goto("/");
  await expect(page.getByTestId("page-chat")).toBeVisible();

  await page.getByTestId("chat-input").fill('/tool shell.exec {"command":"__provider_unauthorized__"}');
  await page.getByTestId("chat-send").click();

  const inspector = page.getByTestId("chat-inspector");
  await expect(inspector).toContainText("provider.call.error");
  await expect(inspector).toContainText("provider unauthorized");
  await expect(inspector).toContainText("toolAttempts");
  await expect(inspector).toContainText("2");
  await expect(inspector).toContainText("toolRetryReason");
  await expect(inspector).toContainText("max_attempts_reached");
});


test("chat inspector should show provider rate limit with retry stop", async ({ page }) => {
  await installTauriMock(page);

  await page.goto("/");
  await expect(page.getByTestId("page-chat")).toBeVisible();

  await page.getByTestId("chat-input").fill('/tool shell.exec {"command":"__provider_rate_limit__"}');
  await page.getByTestId("chat-send").click();

  const inspector = page.getByTestId("chat-inspector");
  await expect(inspector).toContainText("provider.call.error");
  await expect(inspector).toContainText("provider rate limit");
  await expect(inspector).toContainText("toolAttempts");
  await expect(inspector).toContainText("2");
  await expect(inspector).toContainText("toolRetryReason");
  await expect(inspector).toContainText("max_attempts_reached");
});
