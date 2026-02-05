import { useEffect, useMemo, useState } from "react";
import { Pause, Square, Plus } from "lucide-react";
import { motion } from "motion/react";
import { useClient } from "@/data/use-client";

export function Topbar({ title }: { title: string }) {
  const client = useClient();
  const [gatewayAllowLan, setGatewayAllowLan] = useState<boolean | null>(null);
  const [providerModel, setProviderModel] = useState<string>("Unknown");

  useEffect(() => {
    let mounted = true;
    client
      .getSettings()
      .then((res) => {
        if (!mounted) return;
        const entries = new Map(
          res.settings.map((s) => [s.key, s.value] as const),
        );
        const allowLan = entries.get("gateway.allowLan");
        if (typeof allowLan === "boolean") {
          setGatewayAllowLan(allowLan);
        }
        const provider = entries.get("provider.active");
        const model = entries.get("provider.model");
        if (typeof provider === "string" && typeof model === "string") {
          setProviderModel(`${provider}/${model}`);
        } else if (typeof provider === "string") {
          setProviderModel(provider);
        }
      })
      .catch(() => {
        if (mounted) {
          setGatewayAllowLan(null);
          setProviderModel("Unavailable");
        }
      });
    return () => {
      mounted = false;
    };
  }, [client]);

  const gatewayLabel = useMemo(() => {
    if (gatewayAllowLan === null) return "Gateway: Unknown";
    return gatewayAllowLan ? "Gateway: LAN" : "Gateway: Local";
  }, [gatewayAllowLan]);

  return (
    <div className="sticky top-0 z-20">
      <div className="flex h-14 items-center justify-between rounded-2xl bg-background/80 px-4 backdrop-blur-sm">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" data-testid="topbar-title">
            {title}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
            <span data-testid="topbar-gateway">{gatewayLabel}</span>
            <span aria-hidden>•</span>
            <span data-testid="topbar-model">Model: {providerModel}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <TopbarIconButton label="New" testId="topbar-new">
            <Plus className="h-4 w-4" />
          </TopbarIconButton>
          <TopbarIconButton label="Pause" testId="topbar-pause">
            <Pause className="h-4 w-4" />
          </TopbarIconButton>
          <TopbarIconButton label="Kill" testId="topbar-kill">
            <Square className="h-4 w-4" />
          </TopbarIconButton>
        </div>
      </div>
    </div>
  );
}

function TopbarIconButton({
  children,
  label,
  testId,
}: {
  children: React.ReactNode;
  label: string;
  testId: string;
}) {
  return (
    <motion.button
      type="button"
      aria-label={label}
      data-testid={testId}
      whileTap={{ scale: 0.96 }}
      className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-foreground/5 text-foreground transition hover:bg-foreground/10"
    >
      {children}
    </motion.button>
  );
}
