import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { ChevronDown, Loader2, MessageSquare, Plus, Search, Send, Trash2 } from "lucide-react";
import { useClient } from "@/data/use-client";
import { cn } from "@/lib/utils";
import { buildDefaultSessionTitle, getSessionDisplayTitle } from "@/lib/session-titles";
import {
  parseProviderState,
  PROVIDER_PLACEHOLDER,
  toSettingsMap,
  type ProviderProfile,
} from "@/lib/provider-profiles";
import { MagicCard } from "@/components/ui/magic-card";
import { ShinyButton } from "@/components/ui/shiny-button";
import { useToast } from "@/components/ui/toast";
import { useI18n } from "@/i18n/i18n";

type Session = { id: string; title?: string };
type MessageView = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

type ComposerGuardState = {
  gatewayRunning: boolean;
  selectedProfileReady: boolean;
  providerChecking: boolean;
  providerReady: boolean;
  providerReason: string | null;
};

export function ChatLayout() {
  const { t } = useI18n();
  const sessionLabel = t("chat.action.new_session");
  const client = useClient();
  const { push } = useToast();

  const [sessions, setSessions] = useState<Session[]>([]);
  const [filter, setFilter] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<string>("default");
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [messagesBySession, setMessagesBySession] = useState<Record<string, MessageView[]>>({});
  const [providerProfiles, setProviderProfiles] = useState<ProviderProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [gatewayRunning, setGatewayRunning] = useState(false);
  const [providerChecking, setProviderChecking] = useState(false);
  const [providerReady, setProviderReady] = useState(false);
  const [providerReason, setProviderReason] = useState<string | null>(null);

  const unlistenRef = useRef<null | (() => void)>(null);

  const refreshSessions = useCallback(
    async (preferId?: string) => {
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
    },
    [client],
  );

  const loadProviderProfiles = useCallback(async () => {
    const settings = await client.getSettings();
    const settingsMap = toSettingsMap(settings.settings);
    setGatewayRunning(isGatewayRunningEnabled(settingsMap.get("gateway.running")));
    const providerState = parseProviderState(settingsMap);
    const selectableProfiles = providerState.profiles.filter(isSelectableProviderProfile);
    setProviderProfiles(selectableProfiles);
    if (selectableProfiles.length === 0) {
      setSelectedProfileId("");
      return;
    }
    const selectedId = selectableProfiles.some((item) => item.id === providerState.selectedProfileId)
      ? providerState.selectedProfileId
      : selectableProfiles[0].id;
    setSelectedProfileId(selectedId);
  }, [client]);

  const applyProviderProfile = useCallback(
    async (profileId: string) => {
      const selected = providerProfiles.find((item) => item.id === profileId);
      if (!selected) return;
      setSelectedProfileId(profileId);
      await Promise.all([
        client.updateSettings("provider.selectedProfileId", selected.id),
        client.updateSettings("provider.active", selected.provider),
        client.updateSettings("provider.model", selected.model),
        client.updateSettings("provider.baseUrl", selected.baseUrl),
        client.updateSettings("provider.apiKey", selected.apiKey),
      ]);
    },
    [client, providerProfiles],
  );

  const selectedProfile = useMemo(
    () => providerProfiles.find((item) => item.id === selectedProfileId) ?? null,
    [providerProfiles, selectedProfileId],
  );

  const selectedProfileReady = useMemo(() => {
    if (!selectedProfile) return false;
    return Boolean(
      selectedProfile.provider.trim() &&
        selectedProfile.model.trim() &&
        selectedProfile.baseUrl.trim() &&
        selectedProfile.apiKey.trim(),
    );
  }, [selectedProfile]);

  const refreshProviderReadiness = useCallback(async () => {
    if (!gatewayRunning || !selectedProfileReady) {
      clearProviderReadiness(setProviderChecking, setProviderReady, setProviderReason);
      return;
    }

    setProviderChecking(true);
    try {
      const probe = await client.providerPreflight();
      setProviderReady(probe.ready);
      setProviderReason(probe.ready ? null : (probe.reason ?? t("chat.guard.provider_unreachable")));
    } catch (err) {
      setProviderReady(false);
      setProviderReason(toErrorMessage(err, t("chat.guard.provider_unreachable")));
    } finally {
      setProviderChecking(false);
    }
  }, [client, gatewayRunning, selectedProfileReady, t]);

  useEffect(() => {
    let mounted = true;

    refreshSessions().catch((err) => {
      if (!mounted) return;
      setError(toErrorMessage(err, t("chat.error.load_sessions_failed")));
    });

    loadProviderProfiles().catch(() => {
      if (!mounted) return;
      setProviderProfiles([]);
      setSelectedProfileId("");
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

        if (e.type === "settings.update") {
          const key = typeof payload.key === "string" ? payload.key : "";
          if (key.startsWith("provider.") || key === "gateway.running") {
            void loadProviderProfiles().catch(() => {
              // ignore stream-side refresh errors
            });
          }
        }
      })
      .then((unlisten) => {
        unlistenRef.current = unlisten;
      })
      .catch((err) => {
        if (!mounted) return;
        setError(toErrorMessage(err, t("chat.error.subscribe_failed")));
      });

    return () => {
      mounted = false;
      unlistenRef.current?.();
      unlistenRef.current = null;
    };
  }, [client, loadProviderProfiles, refreshSessions, t]);

  useEffect(() => {
    void refreshProviderReadiness();
  }, [refreshProviderReadiness]);

  const composerGuardReason = useMemo(() => {
    return resolveComposerGuardReason(
      {
        gatewayRunning,
        selectedProfileReady,
        providerChecking,
        providerReady,
        providerReason,
      },
      t,
    );
  }, [gatewayRunning, providerChecking, providerReady, providerReason, selectedProfileReady, t]);

  const composerBlocked = composerGuardReason !== null;

  const getSidebarSessionTitle = useCallback(
    (session: Session) => getSessionDisplayTitle(sessionLabel, session.id, session.title),
    [sessionLabel],
  );

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
    if (!text || sending || composerBlocked) return;
    setSending(true);
    setError(null);
    setComposer("");
    try {
      await client.runEngineTurn(activeSessionId, text);
      await refreshSessions(activeSessionId);
    } catch (err) {
      const message = toErrorMessage(err, t("chat.error.send_failed"));
      setError(message);
      push({
        variant: "error",
        title: t("chat.error.send_failed"),
        description: message,
      });
    } finally {
      setSending(false);
    }
  };

  const createNewSession = useCallback(async () => {
    if (sending) return;
    const sessionId = `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    const title = buildDefaultSessionTitle(sessionLabel, sessions);
    setError(null);
    try {
      await client.createSession(sessionId, title);
      setComposer("");
      await refreshSessions(sessionId);
    } catch (err) {
      const message = toErrorMessage(err, t("chat.error.create_session_failed"));
      setError(message);
      push({
        variant: "error",
        title: t("chat.error.create_session_failed"),
        description: message,
      });
    }
  }, [client, push, refreshSessions, sending, sessionLabel, sessions, t]);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      if (sending) return;
      setError(null);
      try {
        await client.deleteSession(sessionId);
        setMessagesBySession((prev) => {
          const next = { ...prev };
          delete next[sessionId];
          return next;
        });
        await refreshSessions();
      } catch (err) {
        const message = toErrorMessage(err, t("chat.error.delete_session_failed"));
        setError(message);
        push({
          variant: "error",
          title: t("chat.error.delete_session_failed"),
          description: message,
        });
      }
    },
    [client, push, refreshSessions, sending, t],
  );

  return (
    <div
      className="grid h-full min-h-0 min-w-0 grid-cols-[280px_minmax(0,1fr)] items-stretch gap-6 overflow-hidden"
      data-testid="chat-layout"
    >
      <MagicCard
        className="min-w-0 h-full rounded-3xl border border-border/50 bg-background/60 backdrop-blur-xl [&>div:last-child]:h-full"
        data-testid="chat-sessions"
      >
        <section className="flex h-full min-w-0 flex-col p-4">
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/50" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={t("chat.search.placeholder")}
              className="h-10 w-full rounded-xl bg-muted/50 pl-9 pr-4 text-sm outline-none transition-colors focus:bg-muted"
              data-testid="sessions-search"
            />
          </div>
          <div className="flex-1 overflow-y-auto pr-1">
            <motion.div layout="position" initial={false} className="flex flex-col gap-1.5">
              {filtered.map((s) => (
                <motion.div
                  layout="position"
                  initial={false}
                  transition={{ layout: { duration: 0.18, ease: [0.22, 1, 0.36, 1] } }}
                  key={s.id}
                  className={cn(
                    "group flex w-full items-start gap-1 rounded-xl px-1 py-1 transition-all hover:bg-muted/50",
                    s.id === activeSessionId && "bg-muted shadow-sm ring-1 ring-border/50",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setActiveSessionId(s.id);
                    }}
                    className="min-w-0 flex-1 rounded-lg px-2 py-1.5 text-left"
                    data-testid={`session-${s.id}`}
                  >
                    <span
                      className={cn(
                        "block w-full truncate text-sm font-medium transition-colors",
                        s.id === activeSessionId
                          ? "text-foreground"
                          : "text-muted-foreground group-hover:text-foreground",
                      )}
                    >
                      {getSidebarSessionTitle(s)}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={t("chat.action.delete_session")}
                    title={t("chat.action.delete_session")}
                    onClick={() => {
                      void deleteSession(s.id);
                    }}
                    disabled={sending}
                    className="mr-1 mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
                    data-testid={`chat-delete-session-${s.id}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </section>
      </MagicCard>

      <MagicCard
        className="min-w-0 h-full rounded-3xl border border-border/50 bg-background/60 backdrop-blur-xl [&>div:last-child]:h-full"
        data-testid="chat-stream"
      >
        <section className="flex h-full min-h-0 min-w-0 flex-col p-6">
          <div className="mb-4 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center border-b border-border/40 pb-4">
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <MessageSquare className="h-4 w-4" />
              </div>
              <div className="truncate text-sm font-semibold tracking-tight">{activeSessionId}</div>
            </div>
            <div className="relative justify-self-center">
              <select
                value={selectedProfileId}
                onChange={(e) => {
                  void applyProviderProfile(e.target.value).catch((err) => {
                    setError(toErrorMessage(err, t("chat.error.switch_model_failed")));
                  });
                }}
                disabled={providerProfiles.length === 0}
                className="h-8 min-w-[220px] appearance-none rounded-lg bg-muted/50 pl-3 pr-8 text-center text-xs font-medium text-muted-foreground transition-colors hover:bg-muted focus:outline-none focus:ring-1 focus:ring-primary/20"
                data-testid="chat-model-select"
              >
                {providerProfiles.length === 0 ? (
                  <option value="">{PROVIDER_PLACEHOLDER}</option>
                ) : (
                  providerProfiles.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))
                )}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/50" />
            </div>
            <div className="justify-self-end">
              <ShinyButton
                type="button"
                onClick={() => {
                  void createNewSession();
                }}
                disabled={sending}
                className={cn(
                  "h-8 w-8 rounded-xl p-0 text-xs font-medium transition-all",
                  sending
                    ? "opacity-50 cursor-not-allowed bg-muted text-muted-foreground"
                    : "bg-primary text-primary-foreground shadow-md hover:translate-y-[-1px]",
                )}
                data-testid="chat-new-session"
                aria-label={t("chat.action.new_session")}
                title={t("chat.action.new_session")}
              >
                <Plus className="h-3.5 w-3.5" />
              </ShinyButton>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto pr-2 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-muted">
            <StreamingMessages messages={messages} loading={sending} />
          </div>

          <div className="mt-4">
            <div
              className={cn(
                "relative flex items-end gap-2 rounded-2xl bg-muted/30 p-2 ring-1 ring-border/50 transition-all",
                composerBlocked
                  ? "cursor-not-allowed opacity-60"
                  : "focus-within:bg-muted/50 focus-within:ring-primary/30",
              )}
            >
              <textarea
                value={composer}
                onChange={(e) => setComposer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                placeholder={composerGuardReason ?? t("chat.compose.placeholder")}
                className="max-h-32 min-h-[44px] w-full resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground/50"
                data-testid="chat-input"
                rows={1}
                disabled={sending || composerBlocked}
              />
              <ShinyButton
                type="button"
                onClick={() => {
                  void send();
                }}
                disabled={sending || composerBlocked || composer.trim().length === 0}
                className={cn(
                  "mb-0.5 h-9 shrink-0 rounded-xl px-4 text-sm font-medium transition-all",
                  sending || composerBlocked || composer.trim().length === 0
                    ? "opacity-50 cursor-not-allowed bg-muted text-muted-foreground"
                    : "bg-primary text-primary-foreground shadow-md hover:translate-y-[-1px]",
                )}
                data-testid="chat-send"
              >
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </ShinyButton>
            </div>
            {composerGuardReason ? (
              <div className="mt-2 text-xs font-medium text-muted-foreground" data-testid="chat-compose-guard">
                {composerGuardReason}
              </div>
            ) : null}
            {error ? (
              <div className="mt-2 text-xs font-medium text-destructive animate-in fade-in slide-in-from-top-1">
                {error}
              </div>
            ) : null}
          </div>
        </section>
      </MagicCard>
    </div>
  );
}

function StreamingMessages({
  messages,
  loading,
}: {
  messages: MessageView[];
  loading: boolean;
}) {
  const { t } = useI18n();
  const lines = useMemo(() => {
    if (messages.length > 0) {
      return messages;
    }
    return [
      {
        id: "assistant-ready",
        role: "assistant" as const,
        text: t("chat.streaming.ready"),
      },
    ];
  }, [messages, t]);

  return (
    <div className="flex flex-col-reverse gap-4 py-4">
      {loading ? (
        <div
          className="self-start rounded-2xl rounded-bl-sm border border-border/50 bg-muted/80 px-4 py-3 shadow-sm"
          data-testid="chat-loading"
        >
          <div className="flex items-center gap-1.5">
            {[0, 1, 2].map((idx) => (
              <motion.span
                key={idx}
                className="h-1.5 w-1.5 rounded-full bg-muted-foreground/70"
                animate={{ opacity: [0.25, 1, 0.25], y: [0, -2, 0] }}
                transition={{
                  duration: 0.9,
                  repeat: Number.POSITIVE_INFINITY,
                  ease: "easeInOut",
                  delay: idx * 0.12,
                }}
              />
            ))}
          </div>
        </div>
      ) : null}
      {lines.map((line, idx) => (
        <motion.div
          key={line.id}
          initial={{ opacity: 0, y: 10, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1], delay: idx * 0.05 }}
          className={cn(
            "max-w-[85%] rounded-2xl p-4 text-sm leading-relaxed shadow-sm",
            line.role === "user"
              ? "self-end bg-primary text-primary-foreground rounded-br-sm"
              : "self-start bg-muted/80 text-foreground rounded-bl-sm border border-border/50",
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

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message.trim()) return err.message;
  if (typeof err === "string" && err.trim()) return err;
  if (err && typeof err === "object") {
    const raw = err as Record<string, unknown>;
    if (typeof raw.message === "string" && raw.message.trim()) return raw.message;
    if (typeof raw.error === "string" && raw.error.trim()) return raw.error;
  }
  try {
    const serialized = JSON.stringify(err);
    return serialized && serialized !== "{}" ? serialized : fallback;
  } catch {
    return fallback;
  }
}

function isSelectableProviderProfile(item: ProviderProfile): boolean {
  return Boolean(item.provider.trim() && item.model.trim() && item.baseUrl.trim());
}

function isGatewayRunningEnabled(value: unknown): boolean {
  return value === true;
}

function clearProviderReadiness(
  setProviderChecking: React.Dispatch<React.SetStateAction<boolean>>,
  setProviderReady: React.Dispatch<React.SetStateAction<boolean>>,
  setProviderReason: React.Dispatch<React.SetStateAction<string | null>>,
) {
  setProviderChecking(false);
  setProviderReady(false);
  setProviderReason(null);
}

function resolveComposerGuardReason(state: ComposerGuardState, t: (key: string) => string): string | null {
  if (!state.gatewayRunning) {
    return t("chat.guard.gateway_required");
  }
  if (!state.selectedProfileReady) {
    return t("chat.guard.model_required");
  }
  if (state.providerChecking) {
    return t("chat.guard.provider_checking");
  }
  if (!state.providerReady) {
    return state.providerReason ?? t("chat.guard.provider_unreachable");
  }
  return null;
}
