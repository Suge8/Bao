export const SIMULATOR_SCRIPT = `
(function () {
  const SESSIONS = new Map([
    ["default", { id: "default", title: "Default", createdAt: Date.now(), updatedAt: Date.now(), messages: [] }],
    ["s2", { id: "s2", title: "Session 2", createdAt: Date.now(), updatedAt: Date.now(), messages: [] }],
  ]);

  const SETTINGS = new Map([
    ["gateway.allowLan", false],
    ["gateway.running", false],
    [
      "provider.profiles",
      [
        {
          id: "mock-openai",
          name: "openai/gpt-4.1-mini",
          provider: "openai",
          model: "gpt-4.1-mini",
          baseUrl: "https://api.openai.com/v1",
          apiKey: "sk-test",
        },
      ],
    ],
    ["provider.selectedProfileId", "mock-openai"],
    ["provider.active", "openai"],
    ["provider.model", "gpt-4.1-mini"],
    ["provider.baseUrl", "https://api.openai.com/v1"],
    ["provider.apiKey", "sk-test"],
  ]);

  const LISTENERS = new Map();
  const CALLBACKS = new Map();
  const RUNTIME_EVENTS = [];
  const AUDIT_LOGS = [];
  const COMMAND_TRACE = [];

  let EVENT_ID = 1000;
  let LISTENER_ID = 1;
  let CALLBACK_ID = 1;
  let PREV_HASH = null;

  function buildAuditFromEvent(evt) {
    const hash = "hash-" + String(evt.eventId);
    const row = {
      id: evt.eventId,
      ts: evt.ts,
      action: evt.type,
      subjectType: "event",
      subjectId: String(evt.eventId),
      payload: evt.payload,
      prevHash: PREV_HASH,
      hash,
    };
    PREV_HASH = hash;
    return row;
  }

  function emitBaoEvent(type, payload) {
    const evt = {
      eventId: ++EVENT_ID,
      type,
      ts: Date.now(),
      payload,
    };

    RUNTIME_EVENTS.push(evt);
    AUDIT_LOGS.push(buildAuditFromEvent(evt));

    const listeners = LISTENERS.get("bao:event");
    if (!listeners) return evt;

    for (const [listenerId, callbackId] of listeners.entries()) {
      const record = CALLBACKS.get(callbackId);
      if (!record) continue;
      record.callback({ event: "bao:event", id: listenerId, payload: evt });
      if (record.once) {
        CALLBACKS.delete(callbackId);
        listeners.delete(listenerId);
      }
    }

    return evt;
  }

  function listByCursor(items, cursor, limit) {
    const from = typeof cursor === "number" ? cursor : 0;
    const safeLimit = Math.max(1, Math.min(2000, typeof limit === "number" ? limit : 50));
    return items.filter((item) => item.id > from || item.eventId > from).slice(-safeLimit);
  }

  function readSettingString(key) {
    return String(SETTINGS.get(key) || "").trim();
  }

  function hasProviderPreflightConfig() {
    return Boolean(
      readSettingString("provider.active") &&
        readSettingString("provider.model") &&
        readSettingString("provider.baseUrl") &&
        readSettingString("provider.apiKey"),
    );
  }

  const COMMANDS = {
    async get_settings() {
      return {
        payload: {
          settings: Array.from(SETTINGS.entries()).map(([key, value]) => ({ key, value })),
        },
      };
    },

    async update_settings(args) {
      const input = args && typeof args.input === "object" ? args.input : {};
      const key = typeof input.key === "string" ? input.key : "";
      SETTINGS.set(key, input.value);
      emitBaoEvent("settings.update", { key, value: input.value });
      return { ok: true };
    },

    async list_sessions() {
      return {
        payload: {
          sessions: Array.from(SESSIONS.values()).map((s) => ({
            sessionId: s.id,
            title: s.title,
            createdAt: s.createdAt,
            updatedAt: s.updatedAt,
          })),
        },
      };
    },

    async list_messages(args) {
      const input = args && typeof args.input === "object" ? args.input : {};
      const sessionId = typeof input.sessionId === "string" ? input.sessionId : "default";
      const limit = typeof input.limit === "number" ? input.limit : 200;
      const session = SESSIONS.get(sessionId);
      const messages = session ? session.messages.slice(-Math.max(1, Math.min(500, limit))).reverse() : [];
      return { payload: { messages } };
    },

    async create_session(args) {
      const input = args && typeof args.input === "object" ? args.input : {};
      const sessionId = typeof input.sessionId === "string" ? input.sessionId : "";
      if (!sessionId) throw new Error("sessionId is required");
      const title = typeof input.title === "string" && input.title.length > 0 ? input.title : sessionId;
      SESSIONS.set(sessionId, {
        id: sessionId,
        title,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
      });
      emitBaoEvent("sessions.create", { sessionId, title });
      return { ok: true };
    },

    async delete_session(args) {
      const input = args && typeof args.input === "object" ? args.input : {};
      const sessionId = typeof input.sessionId === "string" ? input.sessionId : "";
      if (!sessionId) throw new Error("sessionId is required");
      if (!SESSIONS.has(sessionId)) throw new Error("session not found");
      SESSIONS.delete(sessionId);
      emitBaoEvent("sessions.delete", { sessionId });
      return { ok: true };
    },

    async run_engine_turn(args) {
      const input = args && typeof args.input === "object" ? args.input : {};
      const sessionId = typeof input.sessionId === "string" && input.sessionId ? input.sessionId : "default";
      const text = typeof input.text === "string" ? input.text : "";

      const session =
        SESSIONS.get(sessionId) ||
        { id: sessionId, title: sessionId, createdAt: Date.now(), updatedAt: Date.now(), messages: [] };
      if (!SESSIONS.has(sessionId)) {
        SESSIONS.set(sessionId, session);
      }

      session.messages.push({ messageId: "m-" + Date.now() + "-u", role: "user", content: text, createdAt: Date.now() });
      session.updatedAt = Date.now();
      emitBaoEvent("message.send", { sessionId, text });

      let output = "Echo: " + text;
      let toolName = "shell.exec";
      let toolTriggered = text.includes("/tool");
      let toolOk = !toolTriggered;
      let toolAttempts = toolTriggered ? 2 : 0;
      let toolRetryReason = toolTriggered ? "max_attempts_reached" : null;
      let providerUsed = toolTriggered ? null : "bao.bundled.provider.openai";

      if (text.includes("__provider_error_retry__")) {
        emitBaoEvent("provider.call.error", {
          source: "runEngineTurn",
          stage: "provider.call",
          sessionId,
          code: "ERR_PROVIDER_CALL",
          error: "provider run timeout",
          provider: "openai",
          model: "gpt-4.1-mini",
          attempt: 1,
        });
        output = "provider run timeout";
        toolTriggered = true;
        toolOk = false;
      } else if (text.includes("__emit_errors__")) {
        emitBaoEvent("corrector.validate_tool_result.error", {
          source: "runEngineTurn",
          stage: "corrector.validate_tool_result",
          sessionId,
          code: "ERR_CORRECTOR_VALIDATE_TOOL_RESULT",
          error: "validator unavailable",
          toolName,
          attempt: 1,
        });
        emitBaoEvent("memory.extract.error", {
          source: "runEngineTurn",
          stage: "memory.extract.apply_plan",
          sessionId,
          code: "ERR_MEMORY_EXTRACT_APPLY_PLAN",
          error: "apply mutation plan failed",
          planId: "plan_error",
          mutationCount: 1,
        });
        output = "tool execution failed";
        toolTriggered = true;
        toolOk = false;
      } else if (text.includes("/tool") && text.includes("echo")) {
        output = "tool echo 执行成功\\nhello world";
        toolTriggered = true;
        toolOk = true;
        toolAttempts = 1;
        toolRetryReason = null;
      }

      session.messages.push({
        messageId: "m-" + Date.now() + "-a",
        role: "assistant",
        content: output,
        createdAt: Date.now(),
      });
      session.updatedAt = Date.now();

      emitBaoEvent("engine.turn", {
        sessionId,
        output,
        matched: true,
        needsMemory: false,
        toolName,
        toolTriggered,
        toolOk,
        toolValidationOk: toolOk,
        toolValidationError: toolOk ? null : "tool execution failed",
        toolRetryReason,
        toolAttempts,
        providerUsed,
        memoryPlanId: toolTriggered ? "plan_sim" : null,
        memoryMutationCount: toolTriggered ? 1 : 0,
      });

      return {
        output,
        matched: true,
        needsMemory: false,
        toolName,
        toolTriggered,
        toolOk,
      };
    },

    async provider_preflight() {
      if (!hasProviderPreflightConfig()) {
        return { ready: false, reason: "provider config incomplete" };
      }
      return { ready: true };
    },

    async list_runtime_events(args) {
      const cursor = args && typeof args.cursor === "number" ? args.cursor : undefined;
      const limit = args && typeof args.limit === "number" ? args.limit : undefined;
      return { events: listByCursor(RUNTIME_EVENTS, cursor, limit) };
    },

    async list_audit_logs(args) {
      const cursor = args && typeof args.cursor === "number" ? args.cursor : undefined;
      const limit = args && typeof args.limit === "number" ? args.limit : undefined;
      return { logs: listByCursor(AUDIT_LOGS, cursor, limit) };
    },

    async gateway_start() {
      SETTINGS.set("gateway.running", true);
      emitBaoEvent("settings.update", { key: "gateway.running", value: true });
      return null;
    },

    async gateway_stop() {
      SETTINGS.set("gateway.running", false);
      emitBaoEvent("settings.update", { key: "gateway.running", value: false });
      return null;
    },

    async gateway_set_allow_lan(args) {
      const input = args && typeof args.input === "object" ? args.input : {};
      SETTINGS.set("gateway.allowLan", Boolean(input.allow));
      return null;
    },

    async kill_switch_stop_all() {
      SETTINGS.set("gateway.running", false);
      emitBaoEvent("settings.update", { key: "gateway.running", value: false });
      return null;
    },

    async list_tasks() {
      return { payload: { tasks: [] } };
    },

    async list_dimsums() {
      return { payload: { dimsums: [] } };
    },

    async list_memories() {
      return { payload: { memories: [] } };
    },

    async search_index() {
      return { payload: { hits: [] } };
    },

    async memory_get_items() {
      return { payload: { items: [] } };
    },

    async memory_get_timeline() {
      return { payload: { timeline: [] } };
    },

    async memory_list_versions() {
      return { payload: { versions: [] } };
    },

    async apply_mutation_plan() {
      return { ok: true };
    },

    async memory_rollback_version() {
      return { ok: true };
    },

    "plugin:event|listen": async (args) => {
      const event = String(args && args.event ? args.event : "");
      const callbackId = Number(args && args.handler ? args.handler : 0);
      if (!LISTENERS.has(event)) {
        LISTENERS.set(event, new Map());
      }
      const listenerId = LISTENER_ID++;
      LISTENERS.get(event).set(listenerId, callbackId);
      return listenerId;
    },

    "plugin:event|unlisten": async (args) => {
      const event = String(args && args.event ? args.event : "");
      const listenerId = Number(args && args.eventId ? args.eventId : 0);
      const listeners = LISTENERS.get(event);
      if (listeners) listeners.delete(listenerId);
      return null;
    },
  };

  window.__TAURI_MOCK_TRACE__ = COMMAND_TRACE;

  window.__TAURI_INTERNALS__ = {
    transformCallback: function (callback, once) {
      const id = CALLBACK_ID++;
      CALLBACKS.set(id, { callback: callback, once: Boolean(once) });
      return id;
    },
    unregisterCallback: function (id) {
      CALLBACKS.delete(id);
    },
    invoke: async function (cmd, args) {
      COMMAND_TRACE.push(cmd);
      if (Object.prototype.hasOwnProperty.call(COMMANDS, cmd)) {
        return COMMANDS[cmd](args || {});
      }
      return null;
    },
  };

  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {
    unregisterListener: function () {},
  };
})();
`;
