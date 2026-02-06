import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import type { BaoEvent } from "@/data/events";
import { cn } from "@/lib/utils";

type Session = { id: string; title?: string };
type MessageView = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

export function ChatLayout() {
  const client = useClient();

  const [sessions, setSessions] = useState<Session[]>([]);
  const [filter, setFilter] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<string>("default");
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [events, setEvents] = useState<BaoEvent[]>([]);
  const [messagesBySession, setMessagesBySession] = useState<Record<string, MessageView[]>>({});
  const [inspectorOpen, setInspectorOpen] = useState(true);

  const unlistenRef = useRef<null | (() => void)>(null);

  const refreshSessions = useCallback(async (preferId?: string) => {
    const res = await client.listSessions();
    const list = res.sessions;
    setSessions(list);
    setActiveSessionId((prev) => {
      const wanted = preferId ?? prev;
      if (wanted && list.some((session) => session.id === wanted)) {
        return wanted;
      }
      return list[0]?.id ?? "default";
    });
  }, [client]);

  useEffect(() => {
    let mounted = true;

    refreshSessions().catch((err) => {
      if (!mounted) return;
      setError(err instanceof Error ? err.message : "加载会话失败");
    });

    client
      .onBaoEvent((e) => {
        if (!mounted) return;
        const payload = toPayloadObject(e.payload);
        if (e.type === "message.send") {
          const text = typeof payload.text === "string" ? payload.text : "";
          const sessionId = typeof payload.sessionId === "string" ? payload.sessionId : "";
          if (text && sessionId) {
            setMessagesBySession((prev) => {
              const existing = prev[sessionId] ?? [];
              const next: MessageView[] = [
                {
                  id: `user-${e.eventId}`,
                  role: "user",
                  text,
                },
                ...existing,
              ];
              return { ...prev, [sessionId]: next.slice(0, 200) };
            });
          }
        }

        if (e.type === "engine.turn") {
          const output = typeof payload.output === "string" ? payload.output : "";
          const sessionId = typeof payload.sessionId === "string" ? payload.sessionId : "";
          if (output && sessionId) {
            setMessagesBySession((prev) => {
              const existing = prev[sessionId] ?? [];
              const next: MessageView[] = [
                {
                  id: `assistant-${e.eventId}`,
                  role: "assistant",
                  text: output,
                },
                ...existing,
              ];
              return { ...prev, [sessionId]: next.slice(0, 200) };
            });
          }
        }

        setEvents((prev) => {
          const next = [e, ...prev];
          return next.slice(0, 200);
        });
      })
      .then((unlisten) => {
        unlistenRef.current = unlisten;
      })
      .catch((err) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "订阅事件失败");
      });

    return () => {
      mounted = false;
      unlistenRef.current?.();
      unlistenRef.current = null;
    };
  }, [client, refreshSessions]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter(
      (s) => (s.title ?? "").toLowerCase().includes(q) || s.id.toLowerCase().includes(q),
    );
  }, [filter, sessions]);

  const messages = useMemo(() => {
    return messagesBySession[activeSessionId] ?? [];
  }, [activeSessionId, messagesBySession]);

  const send = async () => {
    const text = composer.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    try {
      await client.runEngineTurn(activeSessionId, text);
      setComposer("");
      await refreshSessions(activeSessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="grid min-h-0 grid-cols-[260px_1fr_auto] gap-4" data-testid="chat-layout">
      <section className="rounded-2xl bg-foreground/5 p-3" data-testid="chat-sessions">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="搜索会话"
          className="h-10 w-full rounded-xl bg-background px-3 text-sm outline-none"
          data-testid="sessions-search"
        />
        <motion.div layout className="mt-3 flex flex-col gap-1">
          {filtered.map((s) => (
            <motion.button
              layout
              key={s.id}
              type="button"
              onClick={() => {
                setActiveSessionId(s.id);
              }}
              className={cn(
                "flex items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition hover:bg-foreground/10",
                s.id === activeSessionId && "bg-foreground/10",
              )}
              data-testid={`session-${s.id}`}
            >
              <span className="truncate">{s.title ?? s.id}</span>
              <span className="ml-2 text-xs text-muted-foreground">{s.id}</span>
            </motion.button>
          ))}
        </motion.div>
      </section>

      <section className="flex min-h-0 flex-col rounded-2xl bg-foreground/5 p-4" data-testid="chat-stream">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">{activeSessionId}</div>
          <button
            type="button"
            className="rounded-xl px-3 py-2 text-xs text-muted-foreground transition hover:bg-foreground/10"
            onClick={() => setInspectorOpen((v) => !v)}
            data-testid="inspector-toggle"
          >
            Inspector
          </button>
        </div>

        <div className="mt-3 flex-1 overflow-auto rounded-xl bg-background p-3">
          <StreamingMessages messages={messages} eventCount={events.length} />
        </div>

        <div className="mt-3 rounded-xl bg-background p-2">
          <div className="flex items-center gap-2">
            <input
              value={composer}
              onChange={(e) => setComposer(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder="输入消息并回车发送"
              className="h-10 flex-1 rounded-xl bg-foreground/5 px-3 text-sm outline-none"
              data-testid="chat-input"
            />
            <button
              type="button"
              onClick={() => {
                void send();
              }}
              disabled={sending || composer.trim().length === 0}
              className={cn(
                "h-10 rounded-xl px-4 text-sm transition",
                sending || composer.trim().length === 0
                  ? "cursor-not-allowed bg-foreground/10 text-muted-foreground"
                  : "bg-foreground text-background hover:opacity-90",
              )}
              data-testid="chat-send"
            >
              {sending ? "发送中" : "发送"}
            </button>
          </div>
          {error ? <div className="mt-2 text-xs text-red-500">{error}</div> : null}
        </div>
      </section>

      <motion.section
        animate={{ width: inspectorOpen ? 360 : 0, opacity: inspectorOpen ? 1 : 0 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className={cn(
          "overflow-hidden rounded-2xl bg-foreground/5 p-3",
          !inspectorOpen && "p-0",
        )}
        data-testid="chat-inspector"
      >
        <div className="text-sm font-semibold">Events</div>
        <div className="mt-2 space-y-2 overflow-auto text-xs text-muted-foreground">
          {events.slice(0, 30).map((e) => (
            <div key={e.eventId} className="rounded-xl bg-background p-2">
              <div className="text-foreground">{e.type}</div>
              <pre className="mt-1 whitespace-pre-wrap break-words">{safeJson(e.payload)}</pre>
            </div>
          ))}
        </div>
      </motion.section>
    </div>
  );
}

function StreamingMessages({
  messages,
  eventCount,
}: {
  messages: MessageView[];
  eventCount: number;
}) {
  const lines = useMemo(() => {
    if (messages.length > 0) {
      return messages;
    }
    return [
      {
        id: "assistant-ready",
        role: "assistant" as const,
        text: "assistant: ready",
      },
      {
        id: "events-counter",
        role: "assistant" as const,
        text: `events: ${String(eventCount)}`,
      },
    ];
  }, [eventCount, messages]);

  return (
    <div className="space-y-2">
      {lines.map((line, idx) => (
        <motion.div
          key={line.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18, ease: "easeOut", delay: idx * 0.03 }}
          className={cn(
            "rounded-xl p-3 text-sm",
            line.role === "user" ? "bg-foreground text-background" : "bg-foreground/5",
          )}
          data-testid={`chat-line-${idx}`}
        >
          {line.text}
        </motion.div>
      ))}
    </div>
  );
}

function toPayloadObject(payload: unknown): Record<string, unknown> {
  if (payload && typeof payload === "object") {
    return payload as Record<string, unknown>;
  }
  return {};
}

function safeJson(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
