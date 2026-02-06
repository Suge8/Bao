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

  const [providerActive, setProviderActive] = useState("openai");
  const [providerModel, setProviderModel] = useState("gpt-4.1-mini");
  const [providerBaseUrl, setProviderBaseUrl] = useState("https://api.openai.com/v1");
  const [providerApiKey, setProviderApiKey] = useState("");
  const [providerSaving, setProviderSaving] = useState(false);

  useEffect(() => {
    let mounted = true;
    client
      .getSettings()
      .then((res) => {
        if (!mounted) return;
        const entries = new Map(res.settings.map((s) => [s.key, s.value] as const));

        const allowLanValue = entries.get("gateway.allowLan");
        if (typeof allowLanValue === "boolean") {
          setAllowLan(allowLanValue);
        }

        const runningValue = entries.get("gateway.running");
        if (typeof runningValue === "boolean") {
          setGatewayRunning(runningValue);
        }

        const active = entries.get("provider.active");
        if (typeof active === "string" && active.trim()) {
          setProviderActive(active.trim());
        }

        const model = entries.get("provider.model");
        if (typeof model === "string" && model.trim()) {
          setProviderModel(model.trim());
        }

        const baseUrl = entries.get("provider.baseUrl");
        if (typeof baseUrl === "string" && baseUrl.trim()) {
          setProviderBaseUrl(baseUrl.trim());
        }

        const apiKey = entries.get("provider.apiKey");
        if (typeof apiKey === "string") {
          setProviderApiKey(apiKey);
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
    void client.updateSettings("gateway.allowLan", allowLan).catch(() => {
      // ignore in non-tauri contexts
    });
    void client.gatewaySetAllowLan(allowLan).catch(() => {
      // ignore in non-tauri contexts
    });
  }, [allowLan, client]);

  const gatewayStatusLabel = useMemo(() => {
    if (gatewayRunning === null) return "Unknown";
    return gatewayRunning ? "Running" : "Stopped";
  }, [gatewayRunning]);

  const allowLanLabel = useMemo(() => {
    return allowLan ? "LAN" : "Local";
  }, [allowLan]);

  const providerHint = useMemo(() => {
    return `${providerActive}/${providerModel}`;
  }, [providerActive, providerModel]);

  const saveProviderSettings = async () => {
    const active = providerActive.trim();
    const model = providerModel.trim();
    const baseUrl = providerBaseUrl.trim();

    if (!active || !model || !baseUrl) {
      return;
    }

    setProviderSaving(true);
    try {
      await Promise.all([
        client.updateSettings("provider.active", active),
        client.updateSettings("provider.model", model),
        client.updateSettings("provider.baseUrl", baseUrl),
        client.updateSettings("provider.apiKey", providerApiKey.trim()),
      ]);
    } finally {
      setProviderSaving(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="page-settings">
      <Page title={t("page.settings.title")} description="网关、配对、语言与运行状态设置。" />

      <div className="mx-auto w-full max-w-5xl space-y-4">
        <div className="rounded-2xl bg-foreground/5 p-4">
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
            <div className="text-xs text-foreground/60">可即时切换 Gateway 绑定模式</div>
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
            <div className="text-xs text-foreground/60">{pairingToken ? pairingToken : "未生成"}</div>
          </div>
        </div>

        <div className="rounded-2xl bg-foreground/5 p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">Provider 配置</div>
            <div className="text-xs text-muted-foreground">当前：{providerHint}</div>
          </div>

          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <InputField label="provider.active" value={providerActive} onChange={setProviderActive} />
            <InputField label="provider.model" value={providerModel} onChange={setProviderModel} />
            <InputField label="provider.baseUrl" value={providerBaseUrl} onChange={setProviderBaseUrl} />
            <InputField
              label="provider.apiKey"
              value={providerApiKey}
              onChange={setProviderApiKey}
              type="password"
            />
          </div>

          <div className="mt-3">
            <button
              type="button"
              onClick={() => {
                void saveProviderSettings();
              }}
              disabled={providerSaving}
              className={cn(
                "rounded-xl px-3 py-2 text-sm transition",
                providerSaving
                  ? "cursor-not-allowed bg-foreground/10 text-muted-foreground"
                  : "bg-foreground text-background hover:opacity-90",
              )}
              data-testid="settings-provider-save"
            >
              {providerSaving ? "保存中" : "保存 Provider"}
            </button>
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

function InputField({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="rounded-xl bg-background p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 h-10 w-full rounded-xl bg-foreground/5 px-3 text-sm outline-none"
      />
    </label>
  );
}
