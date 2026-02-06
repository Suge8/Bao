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
        const raw = e.payload as Partial<{ eventId: number; type: string; ts: number; payload: unknown }>;
        const event: BaoEvent = {
          eventId: typeof raw.eventId === "number" ? raw.eventId : nextId++,
          type: typeof raw.type === "string" ? raw.type : "bao:event",
          ts: typeof raw.ts === "number" ? raw.ts : Date.now(),
          payload: "payload" in raw ? raw.payload : e.payload,
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
      const sessions = (evt as { payload: { sessions: unknown[] } }).payload.sessions
        .map((s) => {
          const raw = s as {
            sessionId?: string;
            title?: string | null;
            id?: string;
          };
          return {
            id: raw.sessionId ?? raw.id ?? "",
            title: raw.title ?? raw.sessionId ?? raw.id ?? "",
          };
        })
        .filter((s) => s.id.length > 0);
      return { sessions };
    },

    async createSession(sessionId, title) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("createSession");
      await api.invoke("createSession", { sessionId, title });
      return { ok: true };
    },

    async sendMessage(sessionId, text) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("sendMessage");
      await api.invoke("sendMessage", { sessionId, text });
      return { ok: true };
    },

    async runEngineTurn(sessionId, text) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("runEngineTurn");
      return api.invoke<{
        output: string;
        matched: boolean;
        needsMemory: boolean;
        toolName?: string;
        toolTriggered: boolean;
        toolOk?: boolean;
      }>("runEngineTurn", { sessionId, text });
    },

    async mcpListTools(server) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("mcpListTools");
      return api.invoke<{ tools?: unknown[]; transport?: string }>("mcpListTools", { server });
    },

    async mcpCallTool(server, name, argumentsValue) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("mcpCallTool");
      return api.invoke<{ result?: unknown; transport?: string }>("mcpCallTool", {
        server,
        name,
        arguments: argumentsValue,
      });
    },

    async resourceList(namespace, prefix) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("resourceList");
      return api.invoke<{ items?: unknown[] }>("resourceList", { namespace, prefix });
    },

    async resourceRead(namespace, path) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("resourceRead");
      return api.invoke<Record<string, unknown>>("resourceRead", { namespace, path });
    },

    async listTasks() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listTasks");
      const evt = await api.invoke<{ payload: { tasks: unknown[] } }>("listTasks");
      return { tasks: (evt as { payload: { tasks: unknown[] } }).payload.tasks };
    },

    async listDimsums() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listDimsums");
      const evt = await api.invoke<{ payload: { dimsums: unknown[] } }>("listDimsums");
      return { dimsums: (evt as { payload: { dimsums: unknown[] } }).payload.dimsums };
    },

    async createTask(spec) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("createTask");
      await api.invoke("createTask", { spec });
      return { ok: true };
    },

    async updateTask(spec) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("updateTask");
      await api.invoke("updateTask", { spec });
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

    async enableDimsum(dimsumId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("enableDimsum");
      await api.invoke("enableDimsum", { dimsumId });
      return { ok: true };
    },

    async disableDimsum(dimsumId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("disableDimsum");
      await api.invoke("disableDimsum", { dimsumId });
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

    async listMemoryVersions(memoryId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listMemoryVersions");
      const evt = await api.invoke<{ payload: { versions: unknown[] } }>("listMemoryVersions", {
        memoryId,
      });
      return { versions: (evt as { payload: { versions: unknown[] } }).payload.versions };
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

    async gatewaySetAllowLan(allow) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("gatewaySetAllowLan");
      await api.invoke("gatewaySetAllowLan", { allow });
    },

    async killSwitchStopAll() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("killSwitchStopAll");
      await api.invoke("killSwitchStopAll");
    },
  };
}
