import { Page } from "./page";
import { useI18n } from "@/i18n/i18n";
import { cn } from "@/lib/utils";
import { useEffect, useMemo, useState } from "react";
import { useClient } from "@/data/use-client";

export default function SettingsPage() {
  const { t, locale, setLocale } = useI18n();
  const client = useClient();
  const [allowLan, setAllowLan] = useState(false);
  const [pairingToken, setPairingToken] = useState<string | null>(null);
  const [gatewayRunning, setGatewayRunning] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    client
      .getSettings()
      .then((res) => {
        if (!mounted) return;
        const entries = new Map(
          res.settings.map((s) => [s.key, s.value] as const),
        );
        const allowLanValue = entries.get("gateway.allowLan");
        if (typeof allowLanValue === "boolean") {
          setAllowLan(allowLanValue);
        }
      })
      .catch(() => {
        // ignore errors in non-tauri contexts
      });
    return () => {
      mounted = false;
    };
  }, [client]);

  useEffect(() => {
    let mounted = true;
    if (!mounted) return () => {
      mounted = false;
    };
    void client.updateSettings("gateway.allowLan", allowLan).catch(() => {
      // ignore in non-tauri contexts
    });
    return () => {
      mounted = false;
    };
  }, [allowLan, client]);

  const gatewayStatusLabel = useMemo(() => {
    if (gatewayRunning === null) return "Unknown";
    return gatewayRunning ? "Running" : "Stopped";
  }, [gatewayRunning]);

  const allowLanLabel = useMemo(() => {
    return allowLan ? "LAN" : "Local";
  }, [allowLan]);
  return (
    <div className="space-y-6" data-testid="page-settings">
      <Page title={t("page.settings.title")} description="设置页面骨架（权限/审计/网络等占位）。" />

      <div className="mx-auto w-full max-w-5xl">
        <div className="mb-4 rounded-2xl bg-foreground/5 p-4">
          <div className="text-sm font-medium">网络与远程访问</div>
          <div className="mt-2 text-sm text-foreground/70">
            默认仅本机（127.0.0.1）。如需远程访问，请使用 Tailscale 或受控 tunnel；不要将服务裸露到公网。
          </div>
          <div className="mt-2 text-xs text-foreground/60">
            Gateway: {gatewayStatusLabel} · Mode: {allowLanLabel}
          </div>
          <div className="mt-3 flex items-center gap-3 text-sm">
            <button
              type="button"
              className={cn(
                "rounded-xl px-3 py-2 transition hover:bg-foreground/10",
                allowLan && "bg-foreground/10",
              )}
              onClick={() => setAllowLan(true)}
            >
              允许局域网
            </button>
            <button
              type="button"
              className={cn(
                "rounded-xl px-3 py-2 transition hover:bg-foreground/10",
                !allowLan && "bg-foreground/10",
              )}
              onClick={() => setAllowLan(false)}
            >
              仅本机
            </button>
            <div className="text-xs text-foreground/60">
              切换后下次启动生效（绑定 0.0.0.0 或 127.0.0.1）
            </div>
          </div>
          <div className="mt-3 flex items-center gap-3 text-sm">
            <button
              type="button"
              className={cn(
                "rounded-xl px-3 py-2 transition hover:bg-foreground/10",
                gatewayRunning === true && "bg-foreground/10",
              )}
              onClick={() => {
                setGatewayRunning(true);
                void client.gatewayStart().catch(() => {
                  setGatewayRunning(null);
                });
              }}
            >
              启动 Gateway
            </button>
            <button
              type="button"
              className={cn(
                "rounded-xl px-3 py-2 transition hover:bg-foreground/10",
                gatewayRunning === false && "bg-foreground/10",
              )}
              onClick={() => {
                setGatewayRunning(false);
                void client.gatewayStop().catch(() => {
                  setGatewayRunning(null);
                });
              }}
            >
              停止 Gateway
            </button>
          </div>
          <div className="mt-3 flex items-center gap-3 text-sm">
            <button
              type="button"
              className="rounded-xl px-3 py-2 transition hover:bg-foreground/10"
              onClick={() => {
                void client
                  .generatePairingToken()
                  .then((res) => setPairingToken(res.token))
                  .catch(() => setPairingToken(null));
              }}
            >
              生成配对 Token
            </button>
            <div className="text-xs text-foreground/60">
              {pairingToken ? pairingToken : "未生成"}
            </div>
          </div>
        </div>

        <div className="rounded-2xl bg-foreground/5 p-4">
          <div className="text-sm font-medium">{t("settings.language")}</div>
          <div className="mt-3 flex gap-3 text-sm">
            <button
              type="button"
              className={cn(
                "rounded-xl px-3 py-2 transition hover:bg-foreground/10",
                locale === "zh" && "bg-foreground/10",
              )}
              onClick={() => setLocale("zh")}
            >
              zh {locale === "zh" ? `(${t("common.on")})` : ""}
            </button>
            <button
              type="button"
              className={cn(
                "rounded-xl px-3 py-2 transition hover:bg-foreground/10",
                locale === "en" && "bg-foreground/10",
              )}
              onClick={() => setLocale("en")}
            >
              en {locale === "en" ? `(${t("common.on")})` : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
