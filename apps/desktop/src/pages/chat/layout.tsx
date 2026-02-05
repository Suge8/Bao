import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";
import type { BaoEvent } from "@/data/events";
import { cn } from "@/lib/utils";

type Session = { id: string; title: string };

export function ChatLayout() {
  const client = useClient();

  const [sessions, setSessions] = useState<Session[]>([]);
  const [filter, setFilter] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<string>("s1");

  const [events, setEvents] = useState<BaoEvent[]>([]);
  const [inspectorOpen, setInspectorOpen] = useState(true);

  const unlistenRef = useRef<null | (() => void)>(null);

  useEffect(() => {
    let mounted = true;
    client.listSessions().then((res) => {
      if (!mounted) return;
      setSessions(res.sessions);
    });

    client.onBaoEvent((e) => {
      setEvents((prev) => {
        const next = [e, ...prev];
        return next.slice(0, 200);
      });
    }).then((unlisten) => {
      unlistenRef.current = unlisten;
    });

    return () => {
      mounted = false;
      unlistenRef.current?.();
      unlistenRef.current = null;
    };
  }, [client]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => s.title.toLowerCase().includes(q) || s.id.toLowerCase().includes(q));
  }, [filter, sessions]);

  return (
    <div className="grid min-h-0 grid-cols-[260px_1fr_auto] gap-4">
      <section className="rounded-2xl bg-foreground/5 p-3" data-testid="chat-sessions">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search"
          className="h-10 w-full rounded-xl bg-background px-3 text-sm outline-none"
          data-testid="sessions-search"
        />
        <motion.div layout className="mt-3 flex flex-col gap-1">
          {filtered.map((s) => (
            <motion.button
              layout
              key={s.id}
              type="button"
              onClick={() => setActiveSessionId(s.id)}
              className={cn(
                "flex items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition hover:bg-foreground/10",
                s.id === activeSessionId && "bg-foreground/10",
              )}
              data-testid={`session-${s.id}`}
            >
              <span className="truncate">{s.title}</span>
              <span className="ml-2 text-xs text-muted-foreground">{s.id}</span>
            </motion.button>
          ))}
        </motion.div>
      </section>

      <section className="rounded-2xl bg-foreground/5 p-4" data-testid="chat-stream">
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

        <div className="mt-3 max-h-[calc(100%-3.5rem)] overflow-auto rounded-xl bg-background p-3">
          <StreamingMock events={events} />
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
              <pre className="mt-1 whitespace-pre-wrap break-words">
                {safeJson(e.payload)}
              </pre>
            </div>
          ))}
        </div>
      </motion.section>
    </div>
  );
}

function StreamingMock({ events }: { events: BaoEvent[] }) {
  const lines = useMemo(() => {
    const base = ["assistant: ready", "events: " + String(events.length)];
    return base;
  }, [events.length]);

  return (
    <div className="space-y-2">
      {lines.map((line, idx) => (
        <motion.div
          key={line}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18, ease: "easeOut", delay: idx * 0.03 }}
          className="rounded-xl bg-foreground/5 p-3 text-sm"
          data-testid={`chat-line-${idx}`}
        >
          {line}
        </motion.div>
      ))}
    </div>
  );
}

function safeJson(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
