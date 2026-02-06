
import { Page } from "@playwright/test";

// Types matching Rust backend
export type BaoEvent = {
  eventId: number;
  type: string;
  ts: number;
  payload: unknown;
};

type EngineTurnInput = {
  sessionId: string;
  text: string;
};

// Simulator State
type Session = {
  id: string;
  title: string;
  messages: Array<{ role: string; content: string }>;
};

export class RustCoreSimulator {
  private sessions: Map<string, Session> = new Map();
  private eventListeners: Map<string, Map<number, number>> = new Map();
  private callbacks: Map<number, { callback: (payload: unknown) => void; once: boolean }> = new Map();
  private eventIdSeq = 1000;
  private listenerSeq = 1;
  private callbackSeq = 1;

  constructor() {
    this.sessions.set("default", { id: "default", title: "Default", messages: [] });
  }

  // --- Tauri IPC Mock Implementation ---

  async install(page: Page) {
    await page.addInitScript(() => {
      // @ts-ignore
      window.__RUST_SIMULATOR_callbacks__ = new Map();
      // @ts-ignore
      window.__RUST_SIMULATOR_listeners__ = new Map();
    });

    await page.exposeFunction("rustSimulatorEmit", (eventName: string, payload: unknown) => {
       // This function is called by the simulator (Node side) to emit events to the browser
       // But wait, page.exposeFunction exposes Node -> Browser?
       // No, exposeFunction adds a function in Browser that calls back to Node.
       // We want the reverse: Node (Playwright) triggering Browser callback.
       // Actually, we can just use page.evaluate to trigger the callbacks.
    });
    
    // We'll implement the mock entirely in the browser context for simplicity and speed,
    // avoiding serializing everything back and forth to Node unless necessary.
    // The "Simulator" will be a complex InitScript.
  }
}

// We will inject the entire simulator logic as a browser-side script.
// This ensures it runs synchronously with the app's requests and behaves like a fast local backend.

export const SIMULATOR_SCRIPT = `
(function() {
  const SESSIONS = new Map([
    ["default", { id: "default", title: "Default", messages: [] }],
    ["s2", { id: "s2", title: "Session 2", messages: [] }]
  ]);
  const LISTENERS = new Map(); // event -> Map<id, callbackId>
  const CALLBACKS = new Map(); // callbackId -> {cb, once}
  let EVENT_ID = 1000;
  let LISTENER_ID = 1;
  let CALLBACK_ID = 1;

  // --- Helpers ---
  function emit(eventName, payload) {
    const listeners = LISTENERS.get(eventName);
    if (!listeners) return;
    
    // Wrap in standard Tauri event envelope
    const eventObj = {
      event: eventName,
      payload: {
        eventId: ++EVENT_ID,
        type: payload.type || eventName,
        ts: Date.now(),
        payload: payload.payload || payload
      }
    };
    
    // In Tauri v2, the listener callback receives the Event object
    // but our tauri-client.ts wrapper expects { payload: ... } or just payload depending on implementation.
    // client.ts: 
    // const raw = e.payload ...
    // So we should match what tauri-client.ts expects.
    // tauri-client.ts line 53: const raw = e.payload ...
    
    for (const [lid, cid] of listeners.entries()) {
      const record = CALLBACKS.get(cid);
      if (record) {
        // The mock in basic.spec.ts passes { event, id, payload }
        // tauri-client.ts uses api.listen which returns an unlisten function.
        // The callback passed to api.listen receives an event object.
        record.callback(eventObj);
        if (record.once) {
          CALLBACKS.delete(cid);
          listeners.delete(lid);
        }
      }
    }
  }

  function errorPayload(source, stage, code, error, extra = {}) {
    return {
        source,
        stage,
        code,
        error: String(error),
        ...extra
    };
  }

  // --- Commands ---

  const COMMANDS = {
    async listSessions() {
      return { payload: { sessions: Array.from(SESSIONS.values()).map(s => ({ sessionId: s.id, title: s.title })) } };
    },
    
    async createSession({ sessionId, title }) {
      SESSIONS.set(sessionId, { id: sessionId, title: title || sessionId, messages: [] });
      return { payload: { eventId: ++EVENT_ID, type: "session.created", ts: Date.now(), payload: { sessionId } } };
    },

    async sendMessage({ sessionId, text }) {
      const session = SESSIONS.get(sessionId);
      if (session) {
        session.messages.push({ role: "user", content: text });
      }
      return { ok: true };
    },

    async runEngineTurn({ sessionId, text }) {
      // 1. Emit message.send
      emit("bao:event", {
        type: "message.send",
        payload: { sessionId, text }
      });

      // 2. Router Simulation
      let matched = true;
      let toolName = null;
      let toolArgs = null;
      let needsMemory = false;
      let output = "";
      
      // Simple Router Rules
      if (text.includes("/tool ")) {
         // Explicit tool call
         const parts = text.split(" ");
         toolName = parts[1];
         try {
           const jsonStr = text.substring(text.indexOf("{"));
           toolArgs = JSON.parse(jsonStr);
         } catch (e) {
           toolArgs = {};
         }
      } else if (text.includes("memory")) {
         needsMemory = true;
      }

      // 3. Tool Execution & Failure Simulation
      let toolTriggered = false;
      let toolOk = undefined;
      let toolValidationOk = undefined;
      let toolValidationError = undefined;
      let toolRetryReason = undefined;
      let toolAttempts = 0;
      let providerUsed = null;

      if (toolName) {
        toolTriggered = true;
        
        // --- Failure Scenarios ---
        if (toolArgs?.command === "__emit_errors__") {
          // Simulate Corrector Error
          emit("bao:event", {
            type: "corrector.validate_tool_result.error",
            payload: errorPayload("runEngineTurn", "corrector.validate_tool_result", "ERR_CORRECTOR_VALIDATE_TOOL_RESULT", "validator unavailable", { sessionId, toolName, attempt: 1 })
          });
          
          // Simulate Memory Extract Error
          emit("bao:event", {
            type: "memory.extract.error",
            payload: errorPayload("runEngineTurn", "memory.extract.apply_plan", "ERR_MEMORY_EXTRACT_APPLY_PLAN", "apply mutation plan failed", { sessionId, planId: "plan_error", mutationCount: 1 })
          });
          
          output = "tool execution failed";
          toolOk = false;
        } 
        else if (toolArgs?.command === "__provider_error_retry__") {
           // Simulate Provider Timeout
           emit("bao:event", {
             type: "provider.call.error",
             payload: errorPayload("runEngineTurn", "provider.call", "ERR_PROVIDER_CALL", "provider run timeout", { sessionId, provider: "openai", model: "gpt-4", attempt: 1 })
           });
           output = "provider run timeout";
           toolAttempts = 2;
           toolRetryReason = "max_attempts_reached";
        }
        else if (toolArgs?.command === "__provider_unauthorized__") {
           emit("bao:event", {
             type: "provider.call.error",
             payload: errorPayload("runEngineTurn", "provider.call", "ERR_PROVIDER_CALL", "provider unauthorized", { sessionId, provider: "openai", model: "gpt-4", attempt: 1 })
           });
           output = "provider unauthorized";
           toolAttempts = 2;
           toolRetryReason = "max_attempts_reached";
        }
        else if (toolArgs?.command === "echo") {
           // Success
           toolOk = true;
           toolValidationOk = true;
           output = "tool echo 执行成功\\n" + (toolArgs.args ? toolArgs.args.join(" ") : "hi");
           toolAttempts = 1;
        }
        else {
           // Default tool failure
           toolOk = false;
           output = "tool execution failed";
           toolAttempts = 2;
           toolRetryReason = "max_attempts_reached";
        }
      } else {
        // Chat Turn (Provider)
        providerUsed = "bao.bundled.provider.openai";
        output = "Echo: " + text;
      }

      // 4. Emit engine.turn
      const turnPayload = {
        sessionId,
        output,
        matched,
        needsMemory,
        toolName,
        toolTriggered,
        toolOk,
        toolValidationOk,
        toolValidationError,
        toolRetryReason,
        toolAttempts,
        providerUsed,
        memoryPlanId: toolTriggered ? "plan_sim" : null,
        memoryMutationCount: toolTriggered ? 1 : 0
      };

      emit("bao:event", {
        type: "engine.turn",
        payload: turnPayload
      });

      return {
        output,
        matched,
        needsMemory,
        toolName,
        toolTriggered,
        toolOk
      };
    },

    "plugin:event|listen": async (args) => {
       const event = args.event;
       const callbackId = args.handler;
       if (!LISTENERS.has(event)) {
         LISTENERS.set(event, new Map());
       }
       const listenerId = LISTENER_ID++;
       LISTENERS.get(event).set(listenerId, callbackId);
       return listenerId;
    },

    "plugin:event|unlisten": async (args) => {
       // Implementation detail
       return null;
    }
  };

  // --- Inject ---
  window.__TAURI_INTERNALS__ = {
    transformCallback: (callback, once = false) => {
      const id = CALLBACK_ID++;
      CALLBACKS.set(id, { callback, once });
      return id;
    },
    unregisterCallback: (id) => {
      CALLBACKS.delete(id);
    },
    invoke: async (cmd, args) => {
      // console.log("Invoke:", cmd, args);
      if (COMMANDS[cmd]) {
        return COMMANDS[cmd](args);
      }
      // console.warn("Unknown command:", cmd);
      return null;
    }
  };
  
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {
      unregisterListener: () => {}
  };
})();
`;
