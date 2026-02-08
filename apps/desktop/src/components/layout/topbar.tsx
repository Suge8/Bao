import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Play, Plus, QrCode, Square, Trash2, Wifi } from "lucide-react";
import QRCode from "qrcode";
import { useNavigate } from "react-router-dom";
import { useClient } from "@/data/use-client";
import type { GatewayDevice } from "@/data/client";
import { MagicCard } from "@/components/ui/magic-card";
import { ShinyButton } from "@/components/ui/shiny-button";
import { useToast } from "@/components/ui/toast";
import { useI18n } from "@/i18n/i18n";

const GATEWAY_DEVICE_EVENT_TYPES = new Set([
  "auth.paired",
  "auth.device.connected",
  "auth.device.disconnected",
  "auth.device.revoked",
]);

export function Topbar({ title }: { title: string }) {
  const { t } = useI18n();
  const client = useClient();
  const navigate = useNavigate();
  const { push } = useToast();
  const [gatewayAllowLan, setGatewayAllowLan] = useState<boolean | null>(null);
  const [gatewayRunning, setGatewayRunning] = useState<boolean | null>(null);
  const [gatewayDevices, setGatewayDevices] = useState<GatewayDevice[]>([]);
  const [gatewayBusy, setGatewayBusy] = useState(false);
  const [gatewayPanelOpen, setGatewayPanelOpen] = useState(false);
  const [pairingModalOpen, setPairingModalOpen] = useState(false);
  const [pairingQrImage, setPairingQrImage] = useState("");
  const [sessionCreating, setSessionCreating] = useState(false);

  const refreshGatewaySettings = useCallback(
    async (isMounted: () => boolean = () => true) => {
      try {
        const res = await client.getSettings();
        if (!isMounted()) return;
        const entries = new Map(res.settings.map((s) => [s.key, s.value] as const));
        const allowLan = entries.get("gateway.allowLan");
        const runningValue = entries.get("gateway.running");
        setGatewayAllowLan(typeof allowLan === "boolean" ? allowLan : null);
        setGatewayRunning(typeof runningValue === "boolean" ? runningValue : null);
      } catch {
        if (!isMounted()) return;
        setGatewayAllowLan(null);
        setGatewayRunning(null);
      }
    },
    [client],
  );

  const refreshGatewayDevices = useCallback(
    async (isMounted: () => boolean = () => true) => {
      try {
        const res = await client.listGatewayDevices();
        if (!isMounted()) return;
        setGatewayDevices(Array.isArray(res.devices) ? res.devices : []);
      } catch {
        if (!isMounted()) return;
        setGatewayDevices([]);
      }
    },
    [client],
  );

  useEffect(() => {
    let mounted = true;
    let unlisten: (() => void) | null = null;
    const isMounted = () => mounted;

    void refreshGatewaySettings(isMounted);
    void refreshGatewayDevices(isMounted);

    void client
      .onBaoEvent((evt) => {
        if (evt.type === "auth.paired") {
          setPairingModalOpen(false);
          void refreshGatewayDevices(isMounted);
          return;
        }

        if (evt.type === "settings.update") {
          const payload = toPayloadObject(evt.payload);
          const key = typeof payload.key === "string" ? payload.key : "";
          const value = payload.value;
          if (key === "gateway.allowLan" && typeof value === "boolean") {
            setGatewayAllowLan(value);
            return;
          }
          if (key === "gateway.running" && typeof value === "boolean") {
            setGatewayRunning(value);
            if (!value) {
              setPairingModalOpen(false);
            }
            return;
          }
        }

        if (GATEWAY_DEVICE_EVENT_TYPES.has(evt.type)) {
          void refreshGatewayDevices(isMounted);
        }
      })
      .then((fn) => {
        unlisten = fn;
      })
      .catch(() => {
        // Ignore event stream errors in topbar.
      });

    return () => {
      mounted = false;
      unlisten?.();
    };
  }, [client, refreshGatewayDevices, refreshGatewaySettings]);

  const gatewayLabel = useMemo(() => {
    if (gatewayRunning === null || gatewayAllowLan === null) {
      return t("topbar.gateway.unknown");
    }
    if (gatewayRunning) {
      return gatewayAllowLan ? t("topbar.gateway.online_lan") : t("topbar.gateway.online_local");
    }
    return gatewayAllowLan ? t("topbar.gateway.offline_lan") : t("topbar.gateway.offline_local");
  }, [gatewayAllowLan, gatewayRunning, t]);

  const handleGatewayToggle = () => {
    if (gatewayBusy || gatewayRunning === null) return;
    setGatewayBusy(true);
    if (gatewayRunning) {
      void client
        .gatewayStop()
        .then(() => {
          setGatewayRunning(false);
          setPairingModalOpen(false);
        })
        .catch(() => setGatewayRunning(null))
        .finally(() => setGatewayBusy(false));
      return;
    }
    void client
      .gatewayStart()
      .then(() => setGatewayRunning(true))
      .catch(() => setGatewayRunning(null))
      .finally(() => setGatewayBusy(false));
  };

  const applyAllowLan = (allow: boolean) => {
    if (gatewayAllowLan === allow) return;
    setGatewayAllowLan(allow);
    void Promise.all([client.updateSettings("gateway.allowLan", allow), client.gatewaySetAllowLan(allow)])
      .then(() => {
        void refreshGatewaySettings();
      })
      .catch((err) => {
        void refreshGatewaySettings();
        push({
          variant: "error",
          title: t("topbar.gateway.access_update_failed"),
          description: toErrorMessage(err, t("common.unknown_error")),
        });
      });
  };

  const openPairingModal = async () => {
    if (gatewayAllowLan !== true) return;
    try {
      const qr = await client.pairingQr();
      const image = await QRCode.toDataURL(qr.qrText, {
        margin: 1,
        width: 260,
      });
      setPairingQrImage(image);
      setPairingModalOpen(true);
    } catch (err) {
      push({
        variant: "error",
        title: t("topbar.gateway.pairing_open_failed"),
        description: toErrorMessage(err, t("common.unknown_error")),
      });
    }
  };

  const revokeDevice = async (deviceId: string) => {
    try {
      await client.revokeGatewayDevice(deviceId);
      await refreshGatewayDevices();
    } catch (err) {
      push({
        variant: "error",
        title: t("topbar.gateway.device_revoke_failed"),
        description: toErrorMessage(err, t("common.unknown_error")),
      });
    }
  };

  const connectedDevices = useMemo(
    () => gatewayDevices.filter((device) => device.connected),
    [gatewayDevices],
  );

  const connectedDevicesLabel = useMemo(() => {
    if (gatewayDevices.length === 0) {
      return t("topbar.gateway.devices_none");
    }
    return `${t("topbar.gateway.devices_online_prefix")}${connectedDevices.length}/${gatewayDevices.length}`;
  }, [connectedDevices.length, gatewayDevices.length, t]);

  const createSessionFromTopbar = useCallback(async () => {
    if (sessionCreating) return;
    setSessionCreating(true);
    const sessionId = `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    try {
      await client.createSession(sessionId);
      navigate("/");
    } catch (err) {
      push({
        variant: "error",
        title: t("topbar.action.new_session"),
        description: toErrorMessage(err, t("common.unknown_error")),
      });
    } finally {
      setSessionCreating(false);
    }
  }, [client, navigate, push, sessionCreating, t]);

  return (
    <div className="sticky top-0 z-20">
      <MagicCard className="rounded-2xl border border-border/50 bg-background/60 backdrop-blur-xl">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="min-w-0 flex flex-col gap-0.5">
            <div className="truncate text-base font-semibold tracking-tight" data-testid="topbar-title">
              {title}
            </div>
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground/80">
              <div className="flex items-center gap-1.5">
                <div
                  className={`h-1.5 w-1.5 rounded-full ${
                    gatewayRunning ? "bg-green-500" : "bg-muted-foreground/30"
                  }`}
                />
                <span data-testid="topbar-gateway">{gatewayLabel}</span>
              </div>
              <span className="text-muted-foreground/40">·</span>
              <span className="truncate" data-testid="topbar-gateway-devices">
                {connectedDevicesLabel}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <TopbarIconButton
              label={t("topbar.action.new_session")}
              testId="topbar-new"
              onClick={() => {
                void createSessionFromTopbar();
              }}
              disabled={sessionCreating}
            >
              <Plus className="h-4 w-4" />
            </TopbarIconButton>

            <ShinyButton
              type="button"
              aria-label={t("topbar.gateway.manage")}
              title={t("topbar.gateway.manage")}
              className={`h-8 w-8 rounded-lg p-0 transition-all ${
                gatewayPanelOpen
                  ? "bg-primary/10 text-primary ring-1 ring-primary/30"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted"
              }`}
              onClick={() => setGatewayPanelOpen((prev) => !prev)}
              data-testid="topbar-gateway-manage"
            >
              <Wifi className="h-4 w-4" />
            </ShinyButton>

            <div className="flex items-center gap-1 rounded-xl bg-muted/50 p-1">
              <TopbarIconButton
                label={
                  gatewayRunning
                    ? t("topbar.action.stop_gateway")
                    : t("topbar.action.start_gateway")
                }
                testId="topbar-gateway-toggle"
                onClick={handleGatewayToggle}
                disabled={gatewayBusy || gatewayRunning === null}
              >
                {gatewayRunning ? (
                  <Square className="h-4 w-4 fill-current" />
                ) : (
                  <Play className="h-4 w-4 fill-current" />
                )}
              </TopbarIconButton>
            </div>

            <div className="pl-1">
              <TopbarIconButton
                label={t("topbar.action.kill_all")}
                testId="topbar-kill"
                className="h-9 w-9 bg-red-600 text-white ring-1 ring-red-400/40 shadow-lg shadow-red-700/30 hover:bg-red-700"
                onClick={() => {
                  void client.killSwitchStopAll();
                  setGatewayRunning(false);
                  setPairingModalOpen(false);
                }}
              >
                <AlertTriangle className="h-4 w-4" />
              </TopbarIconButton>
            </div>
          </div>
        </div>
      </MagicCard>

      {gatewayPanelOpen ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-30 cursor-pointer"
            onClick={() => setGatewayPanelOpen(false)}
            aria-label={t("topbar.gateway.close_panel")}
          />
          <div className="absolute right-0 top-[calc(100%+10px)] z-40 w-[390px]" data-testid="topbar-gateway-panel">
            <MagicCard className="rounded-2xl border border-border/60 bg-background/90 backdrop-blur-xl">
              <div className="space-y-3 p-4">
                <div className="rounded-xl bg-muted/30 p-3 ring-1 ring-border/50">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-medium">{t("topbar.gateway.access_mode")}</span>
                    <span className="text-xs text-muted-foreground">
                      {gatewayAllowLan ? t("topbar.gateway.access_lan") : t("topbar.gateway.access_local")}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => applyAllowLan(false)}
                      className={`rounded-lg px-3 py-2 text-xs font-medium transition-all ${
                        gatewayAllowLan === false
                          ? "bg-background text-foreground ring-1 ring-border shadow-sm"
                          : "text-muted-foreground hover:bg-muted/60"
                      }`}
                    >
                      {t("topbar.gateway.local_only")}
                    </button>
                    <button
                      type="button"
                      onClick={() => applyAllowLan(true)}
                      className={`rounded-lg px-3 py-2 text-xs font-medium transition-all ${
                        gatewayAllowLan === true
                          ? "bg-background text-foreground ring-1 ring-border shadow-sm"
                          : "text-muted-foreground hover:bg-muted/60"
                      }`}
                    >
                      {t("topbar.gateway.lan_tailscale")}
                    </button>
                  </div>
                </div>

                <div className="rounded-xl bg-muted/30 p-3 ring-1 ring-border/50">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{t("topbar.gateway.pairing_qr")}</span>
                    <ShinyButton
                      type="button"
                      aria-label={t("topbar.gateway.pairing_qr")}
                      title={t("topbar.gateway.pairing_qr")}
                      className="h-8 w-8 rounded-lg p-0"
                      onClick={() => {
                        void openPairingModal();
                      }}
                      disabled={gatewayAllowLan !== true}
                      data-testid="topbar-gateway-open-qr"
                    >
                      <QrCode className="h-3.5 w-3.5" />
                    </ShinyButton>
                  </div>
                  <div className="text-[11px] text-muted-foreground">{t("topbar.gateway.qr_hint")}</div>
                </div>

                <div className="rounded-xl bg-muted/30 p-3 ring-1 ring-border/50">
                  <div className="mb-2 text-sm font-medium">{t("topbar.gateway.connected_devices")}</div>
                  <div className="max-h-[180px] space-y-2 overflow-y-auto pr-1">
                    {gatewayDevices.length === 0 ? (
                      <div className="text-xs text-muted-foreground">{t("topbar.gateway.no_devices")}</div>
                    ) : (
                      gatewayDevices.map((item) => (
                        <div
                          key={item.deviceId}
                          className="flex items-center justify-between gap-2 rounded-lg bg-background/70 px-2 py-2 ring-1 ring-border/50"
                        >
                          <div className="min-w-0">
                            <div className="truncate text-xs font-medium">{item.deviceId}</div>
                            <div className="truncate text-[10px] text-muted-foreground">
                              {item.connected
                                ? t("topbar.gateway.device_connected")
                                : t("topbar.gateway.device_offline")}
                            </div>
                          </div>
                          <button
                            type="button"
                            className="h-7 w-7 shrink-0 rounded-md text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                            onClick={() => {
                              void revokeDevice(item.deviceId);
                            }}
                            data-testid={`topbar-gateway-device-delete-${item.deviceId}`}
                          >
                            <Trash2 className="mx-auto h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </MagicCard>
          </div>
        </>
      ) : null}

      {pairingModalOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-50 flex cursor-pointer items-center justify-center bg-black/45 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setPairingModalOpen(false);
            }
          }}
          data-testid="topbar-pairing-modal"
        >
          <div className="w-full max-w-sm cursor-default rounded-2xl bg-background p-4 ring-1 ring-border/60">
            <div className="text-sm font-semibold">{t("topbar.gateway.scan_qr")}</div>
            <div className="mt-3 flex justify-center rounded-xl bg-white p-3">
              {pairingQrImage ? (
                <img src={pairingQrImage} alt="pairing-qr" className="h-[220px] w-[220px]" />
              ) : null}
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground">{t("topbar.gateway.qr_hint")}</div>
          </div>
        </button>
      ) : null}
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

function TopbarIconButton({
  children,
  label,
  testId,
  onClick,
  className,
  disabled,
}: {
  children: React.ReactNode;
  label: string;
  testId: string;
  onClick: () => void;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <ShinyButton
      type="button"
      aria-label={label}
      data-testid={testId}
      whileTap={{ scale: 0.94 }}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-lg p-0 transition-all hover:bg-background/80 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-40 ${className ?? ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </ShinyButton>
  );
}
