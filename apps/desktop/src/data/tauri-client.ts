import type { DesktopClient } from "./client";
import type { BaoEvent, UnlistenFn } from "./events";

// IMPORTANT: This file must remain safe to import in a web-only E2E run.
// We lazy-load @tauri-apps/api at runtime.

type TauriEventApi = {
  listen: (
    event: string,
    handler: (e: { payload: unknown }) => void,
  ) => Promise<{ unlisten: UnlistenFn }>;
};

type TauriInvokeApi = {
  invoke: <T = unknown>(cmd: string, args?: Record<string, unknown>) => Promise<T>;
};

async function loadTauriEventApi(): Promise<TauriEventApi | null> {
  try {
    const mod = (await import("@tauri-apps/api/event")) as unknown;
    const listen = (mod as { listen?: unknown }).listen;
    if (typeof listen !== "function") return null;
    return { listen: listen as TauriEventApi["listen"] };
  } catch {
    return null;
  }
}

async function loadTauriInvokeApi(): Promise<TauriInvokeApi | null> {
  try {
    const mod = (await import("@tauri-apps/api/core")) as unknown;
    const invoke = (mod as { invoke?: unknown }).invoke;
    if (typeof invoke !== "function") return null;
    return { invoke: invoke as TauriInvokeApi["invoke"] };
  } catch {
    return null;
  }
}

function missingTauriError(op: string): Error {
  return new Error(`tauri api unavailable: ${op}`);
}

export function createTauriClient(): DesktopClient {
  return {
    async onBaoEvent(cb) {
      const api = await loadTauriEventApi();
      if (!api) throw missingTauriError("listen");

      // Map payload-only into a BaoEvent shape.
      let nextId = 1;
      const sub = await api.listen("bao:event", (e) => {
        const payload = e.payload;
        const event: BaoEvent = {
          eventId: nextId++,
          type: "bao:event",
          ts: Date.now(),
          payload,
        };
        cb(event);
      });
      return sub.unlisten;
    },

    async listSessions() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listSessions");
      const evt = await api.invoke<{ payload: { sessions: { id: string; title: string }[] } }>(
        "listSessions",
      );
      return { sessions: (evt as { payload: { sessions: { id: string; title: string }[] } }).payload.sessions };
    },

    async listTasks() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listTasks");
      const evt = await api.invoke<{ payload: { tasks: unknown[] } }>("listTasks");
      return { tasks: (evt as { payload: { tasks: unknown[] } }).payload.tasks };
    },

    async createTask(spec) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("createTask");
      await api.invoke("createTask", { spec });
      return { ok: true };
    },

    async enableTask(taskId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("enableTask");
      await api.invoke("enableTask", { taskId });
      return { ok: true };
    },

    async disableTask(taskId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("disableTask");
      await api.invoke("disableTask", { taskId });
      return { ok: true };
    },

    async runTaskNow(taskId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("runTaskNow");
      await api.invoke("runTaskNow", { taskId });
      return { ok: true };
    },

    async listMemories() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listMemories");
      const evt = await api.invoke<{ payload: { memories: unknown[] } }>("listMemories");
      return { memories: (evt as { payload: { memories: unknown[] } }).payload.memories };
    },

    async searchIndex(query, limit) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("searchIndex");
      const evt = await api.invoke<{ payload: { hits: unknown[] } }>("searchIndex", {
        query,
        limit,
      });
      return { hits: (evt as { payload: { hits: unknown[] } }).payload.hits };
    },

    async getItems(ids) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("getItems");
      const evt = await api.invoke<{ payload: { items: unknown[] } }>("getItems", { ids });
      return { items: (evt as { payload: { items: unknown[] } }).payload.items };
    },

    async getTimeline(namespace) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("getTimeline");
      const evt = await api.invoke<{ payload: { timeline: unknown[] } }>("getTimeline", {
        namespace,
      });
      return { timeline: (evt as { payload: { timeline: unknown[] } }).payload.timeline };
    },

    async applyMutationPlan(plan) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("applyMutationPlan");
      await api.invoke("applyMutationPlan", { plan });
      return { ok: true };
    },

    async rollbackVersion(memoryId, versionId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("rollbackVersion");
      await api.invoke("rollbackVersion", { memoryId, versionId });
      return { ok: true };
    },

    async getSettings() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("getSettings");
      const evt = await api.invoke<{ payload: { settings: { key: string; value: unknown }[] } }>(
        "getSettings",
      );
      return {
        settings: (evt as { payload: { settings: { key: string; value: unknown }[] } }).payload
          .settings,
      };
    },

    async updateSettings(key, value) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("updateSettings");
      await api.invoke("updateSettings", { key, value });
      return { ok: true };
    },

    async generatePairingToken() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("generatePairingToken");
      return api.invoke<{ token: string }>("generatePairingToken");
    },

    async gatewayStart() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("gatewayStart");
      await api.invoke("gatewayStart");
    },

    async gatewayStop() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("gatewayStop");
      await api.invoke("gatewayStop");
    },
  };
}
