import type { DesktopClient, GatewayDevice } from "./client";
import type { BaoEvent, UnlistenFn } from "./events";
import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";

// IMPORTANT: This file must remain safe to import in a web-only E2E run.
// We keep static imports to avoid Tauri/Vite dynamic-import warnings,
// but gate runtime calls behind __TAURI_INTERNALS__ availability checks.

type TauriEventApi = {
  listen: (
    event: string,
    handler: (e: { payload: unknown }) => void,
  ) => Promise<UnlistenFn>;
};

type TauriInvokeApi = {
  invoke: <T = unknown>(cmd: string, args?: Record<string, unknown>) => Promise<T>;
};

async function loadTauriEventApi(): Promise<TauriEventApi | null> {
  if (!hasTauriInternals()) return null;
  return { listen };
}

async function loadTauriInvokeApi(): Promise<TauriInvokeApi | null> {
  if (!hasTauriInternals()) return null;
  return { invoke };
}

function hasTauriInternals(): boolean {
  if (typeof window === "undefined") return false;
  return "__TAURI_INTERNALS__" in (window as unknown as Record<string, unknown>);
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
      return sub;
    },

    async listRuntimeEvents(cursor, limit) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listRuntimeEvents");
      return api.invoke<{ events: BaoEvent[] }>("list_runtime_events", { cursor, limit });
    },

    async listAuditLogs(cursor, limit) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listAuditLogs");
      return api.invoke<{
        logs: {
          id: number;
          ts: number;
          action: string;
          subjectType: string;
          subjectId: string;
          payload: unknown;
          prevHash?: string | null;
          hash: string;
        }[];
      }>("list_audit_logs", { cursor, limit });
    },

    async listSessions() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listSessions");
      const evt = await api.invoke<{ payload: { sessions: { id: string; title: string }[] } }>(
        "list_sessions",
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
      const input: { sessionId: string; title?: string } = { sessionId };
      if (typeof title === "string" && title.trim().length > 0) {
        input.title = title;
      }
      await api.invoke("create_session", { input });
      return { ok: true };
    },

    async deleteSession(sessionId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("deleteSession");
      await api.invoke("delete_session", { input: { sessionId } });
      return { ok: true };
    },

    async sendMessage(sessionId, text) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("sendMessage");
      await api.invoke("send_message", { sessionId, text });
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
      }>("run_engine_turn", { input: { sessionId, text } });
    },

    async providerPreflight() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("providerPreflight");
      return api.invoke<{ ready: boolean; reason?: string }>("provider_preflight");
    },

    async mcpListTools(server) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("mcpListTools");
      return api.invoke<{ tools?: unknown[]; transport?: string }>("mcp_list_tools", { server });
    },

    async mcpCallTool(server, name, argumentsValue) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("mcpCallTool");
      return api.invoke<{ result?: unknown; transport?: string }>("mcp_call_tool", {
        server,
        name,
        arguments: argumentsValue,
      });
    },

    async resourceList(namespace, prefix) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("resourceList");
      return api.invoke<{ items?: unknown[] }>("resource_list", { namespace, prefix });
    },

    async resourceRead(namespace, path) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("resourceRead");
      return api.invoke<Record<string, unknown>>("resource_read", { namespace, path });
    },

    async listTasks() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listTasks");
      const evt = await api.invoke<{ payload: { tasks: unknown[] } }>("list_tasks");
      return { tasks: (evt as { payload: { tasks: unknown[] } }).payload.tasks };
    },

    async listDimsums() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listDimsums");
      const evt = await api.invoke<{ payload: { dimsums: unknown[] } }>("list_dimsums");
      return { dimsums: (evt as { payload: { dimsums: unknown[] } }).payload.dimsums };
    },

    async createTask(spec) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("createTask");
      await api.invoke("create_task", { spec });
      return { ok: true };
    },

    async updateTask(spec) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("updateTask");
      await api.invoke("update_task", { spec });
      return { ok: true };
    },

    async enableTask(taskId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("enableTask");
      await api.invoke("enable_task", { taskId });
      return { ok: true };
    },

    async disableTask(taskId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("disableTask");
      await api.invoke("disable_task", { taskId });
      return { ok: true };
    },

    async runTaskNow(taskId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("runTaskNow");
      await api.invoke("run_task_now", { taskId });
      return { ok: true };
    },

    async enableDimsum(dimsumId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("enableDimsum");
      await api.invoke("enable_dimsum", { dimsumId });
      return { ok: true };
    },

    async disableDimsum(dimsumId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("disableDimsum");
      await api.invoke("disable_dimsum", { dimsumId });
      return { ok: true };
    },

    async listMemories() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listMemories");
      const evt = await api.invoke<{ payload: { memories: unknown[] } }>("list_memories");
      return { memories: (evt as { payload: { memories: unknown[] } }).payload.memories };
    },

    async searchIndex(query, limit) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("searchIndex");
      const evt = await api.invoke<{ payload: { hits: unknown[] } }>("search_index", {
        query,
        limit,
      });
      return { hits: (evt as { payload: { hits: unknown[] } }).payload.hits };
    },

    async getItems(ids) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("getItems");
      const evt = await api.invoke<{ payload: { items: unknown[] } }>("memory_get_items", { ids });
      return { items: (evt as { payload: { items: unknown[] } }).payload.items };
    },

    async getTimeline(namespace) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("getTimeline");
      const evt = await api.invoke<{ payload: { timeline: unknown[] } }>("memory_get_timeline", {
        namespace,
      });
      return { timeline: (evt as { payload: { timeline: unknown[] } }).payload.timeline };
    },

    async listMemoryVersions(memoryId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listMemoryVersions");
      const evt = await api.invoke<{ payload: { versions: unknown[] } }>("memory_list_versions", {
        memoryId,
      });
      return { versions: (evt as { payload: { versions: unknown[] } }).payload.versions };
    },

    async applyMutationPlan(plan) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("applyMutationPlan");
      await api.invoke("memory_apply_mutation_plan", { plan });
      return { ok: true };
    },

    async rollbackVersion(memoryId, versionId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("rollbackVersion");
      await api.invoke("memory_rollback_version", { memoryId, versionId });
      return { ok: true };
    },

    async getSettings() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("getSettings");
      const evt = await api.invoke<{ payload: { settings: { key: string; value: unknown }[] } }>(
        "get_settings",
      );
      return {
        settings: (evt as { payload: { settings: { key: string; value: unknown }[] } }).payload
          .settings,
      };
    },

    async updateSettings(key, value) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("updateSettings");
      await api.invoke("update_settings", { input: { key, value } });
      return { ok: true };
    },

    async generatePairingToken() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("generatePairingToken");
      return api.invoke<{ token: string }>("gateway_generate_pairing_token");
    },

    async pairingQr() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("pairingQr");
      return api.invoke<{ token: string; wsUrl: string; qrText: string }>("gateway_pairing_qr");
    },

    async listGatewayDevices() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("listGatewayDevices");
      return api.invoke<{ devices: GatewayDevice[] }>("gateway_list_devices");
    },

    async revokeGatewayDevice(deviceId) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("revokeGatewayDevice");
      await api.invoke("gateway_revoke_device", { input: { deviceId } });
    },

    async gatewayStart() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("gatewayStart");
      await api.invoke("gateway_start");
    },

    async gatewayStop() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("gatewayStop");
      await api.invoke("gateway_stop");
    },

    async gatewaySetAllowLan(allow) {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("gatewaySetAllowLan");
      await api.invoke("gateway_set_allow_lan", { input: { allow } });
    },

    async killSwitchStopAll() {
      const api = await loadTauriInvokeApi();
      if (!api) throw missingTauriError("killSwitchStopAll");
      await api.invoke("kill_switch_stop_all");
    },
  };
}
