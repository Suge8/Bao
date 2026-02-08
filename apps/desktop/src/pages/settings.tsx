import { useI18n } from "@/i18n/i18n";
import { cn } from "@/lib/utils";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useClient } from "@/data/use-client";
import { ShinyButton } from "@/components/ui/shiny-button";
import { MagicCard } from "@/components/ui/magic-card";
import { useToast } from "@/components/ui/toast";
import {
  createProfileDraft,
  parseProviderState,
  toSettingsMap,
  PROVIDER_PLACEHOLDER,
  type ProviderProfile,
} from "@/lib/provider-profiles";
import { FileText, Globe, Key, Plus, RefreshCw, Server, Trash2 } from "lucide-react";

const initialProviderProfile = createProfileDraft();

export default function SettingsPage() {
  const { t, locale, setLocale } = useI18n();
  const client = useClient();
  const { push } = useToast();

  const [providerProfiles, setProviderProfiles] = useState<ProviderProfile[]>([initialProviderProfile]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>(initialProviderProfile.id);
  const [providerSaving, setProviderSaving] = useState(false);
  const [logsModalOpen, setLogsModalOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    client
      .getSettings()
      .then((res) => {
        if (!mounted) return;
        const entries = toSettingsMap(res.settings);

        const providerState = parseProviderState(entries);
        setProviderProfiles(providerState.profiles);
        setSelectedProfileId(providerState.selectedProfileId);
      })
      .catch(() => {
        // ignore errors in non-tauri contexts
      });
    return () => {
      mounted = false;
    };
  }, [client]);

  const selectedProfile = useMemo(() => {
    return providerProfiles.find((item) => item.id === selectedProfileId) ?? providerProfiles[0] ?? null;
  }, [providerProfiles, selectedProfileId]);

  const updateProfileField = <K extends keyof ProviderProfile>(key: K, value: ProviderProfile[K]) => {
    setProviderProfiles((prev) =>
      prev.map((item) => (item.id === selectedProfileId ? { ...item, [key]: value } : item)),
    );
  };

  const addProviderProfile = () => {
    const draft = createProfileDraft();
    setProviderProfiles((prev) => [...prev, draft]);
    setSelectedProfileId(draft.id);
  };

  const deleteProviderProfile = async () => {
    if (!selectedProfile) {
      push({
        variant: "error",
        title: t("settings.provider.toast.delete_failed"),
        description: t("settings.provider.toast.delete_empty"),
      });
      return;
    }

    const remaining = providerProfiles.filter((item) => item.id !== selectedProfile.id);
    const normalizedRemaining = normalizeProviderProfiles(remaining);
    const persistable = normalizedRemaining.filter(isCompleteProfile);
    const nextSelectedLocal = normalizedRemaining[0] ?? createProfileDraft();
    const nextSelectedPersisted = persistable[0] ?? null;

    setProviderSaving(true);
    try {
      await persistProviderState(client, {
        profiles: persistable,
        selectedProfile: nextSelectedPersisted,
      });

      setProviderProfiles(normalizedRemaining.length > 0 ? normalizedRemaining : [nextSelectedLocal]);
      setSelectedProfileId(nextSelectedLocal.id);

      push({
        variant: "success",
        title: t("settings.provider.toast.deleted"),
        description: selectedProfile.name || PROVIDER_PLACEHOLDER,
      });
    } catch (err) {
      push({
        variant: "error",
        title: t("settings.provider.toast.delete_failed"),
        description: toErrorMessage(err),
      });
    } finally {
      setProviderSaving(false);
    }
  };

  const saveProviderSettings = async () => {
    if (!selectedProfile) {
      push({
        variant: "error",
        title: t("settings.provider.toast.save_failed"),
        description: t("settings.provider.toast.save_missing_config"),
      });
      return;
    }

    const normalizedProfiles = normalizeProviderProfiles(providerProfiles);
    const active = selectedProfile.provider.trim();
    const model = selectedProfile.model.trim();
    const baseUrl = selectedProfile.baseUrl.trim();
    const name = selectedProfile.name.trim();

    if (!name || !active || !model || !baseUrl) {
      push({
        variant: "error",
        title: t("settings.provider.toast.save_failed"),
        description: t("settings.provider.toast.save_fields_required"),
      });
      return;
    }

    setProviderSaving(true);
    try {
      const persistable = normalizedProfiles.filter(isCompleteProfile);
      if (persistable.length === 0) {
        throw new Error(t("settings.provider.toast.no_persistable"));
      }
      if (!persistable.some((item) => item.id === selectedProfile.id)) {
        throw new Error(t("settings.provider.toast.incomplete_selected"));
      }

      await persistProviderState(client, {
        profiles: persistable,
        selectedProfile: {
          ...selectedProfile,
          provider: active,
          model,
          baseUrl,
          apiKey: selectedProfile.apiKey.trim(),
        },
      });

      setProviderProfiles(normalizedProfiles);
      push({
        variant: "success",
        title: t("settings.provider.toast.saved"),
        description: `${t("settings.provider.toast.current_model_prefix")}${active}/${model}`,
      });
    } catch (err) {
      push({
        variant: "error",
        title: t("settings.provider.toast.save_failed"),
        description: toErrorMessage(err),
        durationMs: 7000,
      });
    } finally {
      setProviderSaving(false);
    }
  };

  const providerItemBaseClass = "w-full rounded-lg px-3 py-2 text-left transition-all";
  const providerItemActiveClass = "bg-background text-foreground ring-1 ring-border/50";
  const providerItemInactiveClass = "text-muted-foreground hover:bg-muted/50 hover:text-foreground";

  const languageButtonBaseClass = "rounded-lg px-4 py-1.5 text-xs font-medium transition-all";
  const languageButtonActiveClass = "bg-background shadow-sm text-foreground";
  const languageButtonInactiveClass = "text-muted-foreground hover:text-foreground";

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col overflow-hidden" data-testid="page-settings">
      <div className="mb-4 shrink-0">
        <h1 className="text-2xl font-bold tracking-tight">{t("page.settings.title")}</h1>
        <p className="text-muted-foreground mt-1">{t("settings.description")}</p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1 lg:overflow-hidden lg:pr-0">
        <div className="grid min-h-full gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_320px]">
          <MagicCard className="min-h-0 overflow-hidden rounded-3xl border border-border/50 bg-background/60 backdrop-blur-sm">
            <div className="flex h-full min-h-0 flex-col p-5">
              <div className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Server className="h-4 w-4" />
                  </div>
                  <div className="text-base font-semibold">{t("settings.provider.title")}</div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <ShinyButton
                    type="button"
                    className="h-7 rounded-lg px-2 text-xs gap-1"
                    onClick={addProviderProfile}
                    data-testid="settings-provider-add"
                  >
                    <Plus className="h-3 w-3" />
                    {t("settings.provider.add")}
                  </ShinyButton>
                  <ShinyButton
                    type="button"
                    className="h-7 rounded-lg px-2 text-xs gap-1"
                    onClick={() => {
                      void deleteProviderProfile();
                    }}
                    disabled={providerSaving}
                    data-testid="settings-provider-delete"
                  >
                    <Trash2 className="h-3 w-3" />
                    {t("settings.provider.delete")}
                  </ShinyButton>
                </div>
              </div>

              <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[minmax(0,200px)_minmax(0,1fr)]">
                <div className="min-h-0 min-w-0 space-y-1 rounded-xl bg-muted/30 p-2 ring-1 ring-border/50 md:overflow-y-auto">
                  {providerProfiles.map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      onClick={() => setSelectedProfileId(item.id)}
                      className={cn(
                        providerItemBaseClass,
                        item.id === selectedProfileId ? providerItemActiveClass : providerItemInactiveClass,
                      )}
                      data-testid={`settings-provider-item-${item.id}`}
                    >
                      <div className="truncate text-xs font-medium">{item.name || PROVIDER_PLACEHOLDER}</div>
                      <div className="truncate text-[10px] text-muted-foreground/70">
                        {item.provider && item.model ? `${item.provider}/${item.model}` : PROVIDER_PLACEHOLDER}
                      </div>
                    </button>
                  ))}
                </div>

                <div className="min-w-0 space-y-3 md:overflow-y-auto md:pr-1">
                  <InputField
                    label={t("settings.provider.profile_name")}
                    value={selectedProfile?.name ?? ""}
                    onChange={(value) => updateProfileField("name", value)}
                    placeholder={PROVIDER_PLACEHOLDER}
                  />
                  <InputField
                    label={t("settings.provider.provider")}
                    value={selectedProfile?.provider ?? ""}
                    onChange={(value) => updateProfileField("provider", value)}
                    placeholder={PROVIDER_PLACEHOLDER}
                  />
                  <InputField
                    label={t("settings.provider.model_id")}
                    value={selectedProfile?.model ?? ""}
                    onChange={(value) => updateProfileField("model", value)}
                    placeholder={PROVIDER_PLACEHOLDER}
                  />
                  <InputField
                    label={t("settings.provider.base_url")}
                    value={selectedProfile?.baseUrl ?? ""}
                    onChange={(value) => updateProfileField("baseUrl", value)}
                    placeholder={PROVIDER_PLACEHOLDER}
                  />
                  <div className="space-y-1.5">
                    <div className="text-xs font-medium text-muted-foreground">{t("settings.provider.api_key")}</div>
                    <div className="relative">
                      <input
                        type="password"
                        value={selectedProfile?.apiKey ?? ""}
                        onChange={(e) => updateProfileField("apiKey", e.target.value)}
                        className="h-9 w-full rounded-xl bg-muted/30 px-3 text-xs outline-none ring-1 ring-border/50 focus:ring-primary/30 transition-all"
                        placeholder={PROVIDER_PLACEHOLDER}
                      />
                      <Key className="absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/50" />
                    </div>
                  </div>

                  <div className="pt-2">
                    <ShinyButton
                      type="button"
                      onClick={() => {
                        void saveProviderSettings();
                      }}
                      disabled={providerSaving}
                      className="w-full h-9 rounded-xl text-xs font-medium"
                      data-testid="settings-provider-save"
                    >
                      {providerSaving ? t("settings.provider.saving") : t("settings.provider.save")}
                    </ShinyButton>
                  </div>
                </div>
              </div>
            </div>
          </MagicCard>

          <div className="flex min-h-0 flex-col gap-4">
            <MagicCard className="rounded-3xl border border-border/50 bg-background/60 backdrop-blur-sm">
              <div className="flex items-center justify-between gap-4 p-5">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-base font-semibold">{t("settings.logs.title")}</div>
                    <p className="text-xs text-muted-foreground">{t("settings.logs.description")}</p>
                  </div>
                </div>
                <ShinyButton
                  type="button"
                  className="h-9 rounded-xl px-4 text-xs font-medium"
                  onClick={() => setLogsModalOpen(true)}
                  data-testid="settings-open-logs"
                >
                  {t("settings.logs.open")}
                </ShinyButton>
              </div>
            </MagicCard>

            <MagicCard className="rounded-3xl border border-border/50 bg-background/60 backdrop-blur-sm">
              <div className="flex items-center justify-between gap-4 p-5">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Globe className="h-4 w-4" />
                  </div>
                  <div className="text-base font-semibold">{t("settings.language")}</div>
                </div>

                <div className="flex rounded-xl bg-muted/30 p-1 ring-1 ring-border/50">
                  <button
                    type="button"
                    onClick={() => setLocale("zh")}
                    className={cn(
                      languageButtonBaseClass,
                      locale === "zh" ? languageButtonActiveClass : languageButtonInactiveClass,
                    )}
                  >
                    中文
                  </button>
                  <button
                    type="button"
                    onClick={() => setLocale("en")}
                    className={cn(
                      languageButtonBaseClass,
                      locale === "en" ? languageButtonActiveClass : languageButtonInactiveClass,
                    )}
                  >
                    English
                  </button>
                </div>
              </div>
            </MagicCard>
          </div>
        </div>
      </div>
      <LogsModal open={logsModalOpen} onClose={() => setLogsModalOpen(false)} />
    </div>
  );
}

type RuntimeEventRecord = {
  eventId: number;
  ts: number;
  type: string;
  payload: unknown;
};

type AuditLogRecord = {
  id: number;
  ts: number;
  action: string;
  subjectType: string;
  subjectId: string;
  payload: unknown;
  prevHash?: string | null;
  hash: string;
};

function LogsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const client = useClient();
  const { push } = useToast();

  const [tab, setTab] = useState<"runtime" | "audit">("runtime");
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [runtimeEvents, setRuntimeEvents] = useState<RuntimeEventRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [expandedRuntimeId, setExpandedRuntimeId] = useState<number | null>(null);
  const [expandedAuditId, setExpandedAuditId] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [runtimeRes, auditRes] = await Promise.all([
        client.listRuntimeEvents(undefined, 120),
        client.listAuditLogs(undefined, 120),
      ]);
      setRuntimeEvents(
        Array.isArray(runtimeRes.events) ? (runtimeRes.events as RuntimeEventRecord[]) : [],
      );
      setAuditLogs(Array.isArray(auditRes.logs) ? (auditRes.logs as AuditLogRecord[]) : []);
    } catch (err) {
      push({
        variant: "error",
        title: t("settings.logs.refresh"),
        description: toErrorMessage(err),
      });
    } finally {
      setLoading(false);
    }
  }, [client, push, t]);

  useEffect(() => {
    if (!open) return;
    void fetchData();
  }, [open, fetchData]);

  useEffect(() => {
    if (!open || !autoRefresh) return;
    const timer = setInterval(() => {
      void fetchData();
    }, 3000);
    return () => clearInterval(timer);
  }, [open, autoRefresh, fetchData]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      setExpandedRuntimeId(null);
      setExpandedAuditId(null);
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
      data-testid="settings-logs-overlay"
    >
      <button
        type="button"
        className="absolute inset-0 cursor-pointer"
        onClick={onClose}
        aria-label={t("settings.logs.close_overlay")}
      />

      <div
        className="relative z-10 flex h-[80vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-background ring-1 ring-border/60"
        data-testid="settings-logs-modal"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border/40 bg-muted/30 px-5 py-4">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            <div>
              <div className="text-sm font-semibold">{t("settings.logs.title")}</div>
              <div className="text-xs text-muted-foreground">{t("settings.logs.description")}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setAutoRefresh((v) => !v)}
              className={cn(
                "flex h-8 items-center gap-1 rounded-lg border px-2 text-xs",
                autoRefresh
                  ? "border-primary/30 bg-primary/10 text-primary"
                  : "border-border bg-background text-muted-foreground",
              )}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", autoRefresh && "animate-spin")} />
              {t("settings.logs.auto_refresh")}
            </button>
            <button
              type="button"
              onClick={() => {
                void fetchData();
              }}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-background text-muted-foreground"
              aria-label={t("settings.logs.refresh")}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            </button>
          </div>
        </div>

        <div className="flex shrink-0 border-b border-border/40 bg-background px-5 pt-2">
          <div className="flex gap-6">
            <button
              type="button"
              onClick={() => setTab("runtime")}
              className={cn(
                "relative py-3 text-sm font-semibold",
                tab === "runtime"
                  ? "text-primary after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-primary"
                  : "text-muted-foreground",
              )}
              data-testid="settings-logs-tab-runtime"
            >
              {t("settings.logs.runtime")}
            </button>
            <button
              type="button"
              onClick={() => setTab("audit")}
              className={cn(
                "relative py-3 text-sm font-semibold",
                tab === "audit"
                  ? "text-primary after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-primary"
                  : "text-muted-foreground",
              )}
              data-testid="settings-logs-tab-audit"
            >
              {t("settings.logs.audit")}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-background/40 p-0">
          {tab === "runtime" ? (
            runtimeEvents.length === 0 ? (
              <div className="p-4 text-xs text-muted-foreground">{t("settings.logs.empty_runtime")}</div>
            ) : (
              <div className="divide-y divide-border/30">
                {runtimeEvents.map((event) => (
                  <div key={event.eventId} className="px-4 py-3">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 text-left"
                      onClick={() =>
                        setExpandedRuntimeId((prev) => toggleExpandedId(prev, event.eventId))
                      }
                    >
                      <div className="text-sm font-medium">{event.type}</div>
                      <div className="text-[11px] text-muted-foreground">
                        {new Date(event.ts).toLocaleTimeString()}
                      </div>
                    </button>
                    {expandedRuntimeId === event.eventId ? (
                      <pre className="mt-2 overflow-x-auto rounded-lg bg-muted/40 p-2 text-[11px] leading-5 text-muted-foreground">
                        {safeStringify(event.payload)}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            )
          ) : auditLogs.length === 0 ? (
            <div className="p-4 text-xs text-muted-foreground">{t("settings.logs.empty_audit")}</div>
          ) : (
            <div className="divide-y divide-border/30">
              {auditLogs.map((log) => (
                <div key={log.id} className="px-4 py-3">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 text-left"
                    onClick={() => setExpandedAuditId((prev) => toggleExpandedId(prev, log.id))}
                  >
                    <div className="text-sm font-medium">{log.action}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {new Date(log.ts).toLocaleTimeString()}
                    </div>
                  </button>
                  {expandedAuditId === log.id ? (
                    <pre className="mt-2 overflow-x-auto rounded-lg bg-muted/40 p-2 text-[11px] leading-5 text-muted-foreground">
                      {safeStringify(log.payload)}
                    </pre>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InputField({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-xl bg-muted/30 px-3 text-xs outline-none ring-1 ring-border/50 focus:ring-primary/30 transition-all placeholder:text-muted-foreground/30"
        placeholder={placeholder}
      />
    </label>
  );
}

function normalizeProviderProfiles(items: ProviderProfile[]): ProviderProfile[] {
  return items.map((item) => ({
    ...item,
    name: item.name.trim() || PROVIDER_PLACEHOLDER,
    provider: item.provider.trim(),
    model: item.model.trim(),
    baseUrl: item.baseUrl.trim(),
    apiKey: item.apiKey.trim(),
  }));
}

function isCompleteProfile(item: ProviderProfile) {
  return Boolean(item.name.trim() && item.provider.trim() && item.model.trim() && item.baseUrl.trim());
}

async function persistProviderState(
  client: ReturnType<typeof useClient>,
  options: {
    profiles: ProviderProfile[];
    selectedProfile: ProviderProfile | null;
  },
) {
  const { profiles, selectedProfile } = options;
  await updateSettingStrict(client, "provider.profiles", profiles);
  await updateSettingStrict(client, "provider.selectedProfileId", selectedProfile?.id ?? "");
  await updateSettingStrict(client, "provider.active", selectedProfile?.provider ?? "");
  await updateSettingStrict(client, "provider.model", selectedProfile?.model ?? "");
  await updateSettingStrict(client, "provider.baseUrl", selectedProfile?.baseUrl ?? "");
  await updateSettingStrict(client, "provider.apiKey", selectedProfile?.apiKey ?? "");
}

async function updateSettingStrict(
  client: ReturnType<typeof useClient>,
  key: string,
  value: unknown,
) {
  try {
    await client.updateSettings(key, value);
  } catch (err) {
    throw new Error(`${key} 写入失败：${toErrorMessage(err)}`);
  }
}

function toErrorMessage(err: unknown): string {
  if (err instanceof Error && err.message.trim()) return err.message;
  if (typeof err === "string" && err.trim()) return err;
  try {
    return JSON.stringify(err);
  } catch {
    return "unknown error";
  }
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function toggleExpandedId(current: number | null, next: number): number | null {
  return current === next ? null : next;
}
