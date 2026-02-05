import { NavLink, Outlet } from "react-router-dom";
import { motion } from "motion/react";
import { Brain, Cog, LayoutGrid, ListChecks, MessageSquare, PanelLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n/i18n";
import { Topbar } from "@/components/layout/topbar";
import { useMemo, useState } from "react";

type NavState = {
  isActive: boolean;
  isPending: boolean;
};

const NAV = [
  { to: "/", labelKey: "nav.chat", icon: MessageSquare },
  { to: "/tasks", labelKey: "nav.tasks", icon: ListChecks },
  { to: "/dimsums", labelKey: "nav.dimsums", icon: LayoutGrid },
  { to: "/memory", labelKey: "nav.memory", icon: Brain },
  { to: "/settings", labelKey: "nav.settings", icon: Cog },
] as const;

export function AppShell() {
  const { t } = useI18n();
  const [compact, setCompact] = useState(false);

  const nav = useMemo(() => NAV.map((n) => ({ ...n, label: t(n.labelKey) })), [t]);
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">
        <motion.aside
          animate={{ width: compact ? 88 : 280 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="shrink-0 px-4 py-5"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-xl bg-foreground/10" />
              {compact ? null : (
                <div className="leading-tight">
                  <div className="text-sm font-semibold">Bao</div>
                  <div className="text-xs text-muted-foreground">Stage 1</div>
                </div>
              )}
            </div>

            <button
              type="button"
              aria-label="Toggle Sidebar"
              data-testid="sidebar-toggle"
              className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-foreground/5 text-foreground transition hover:bg-foreground/10"
              onClick={() => setCompact((v) => !v)}
            >
              <PanelLeft className="h-4 w-4" />
            </button>
          </div>

          <nav className="mt-6 flex flex-col gap-1">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                aria-label={item.label}
                data-testid={`nav-${item.to === "/" ? "chat" : item.to.slice(1)}`}
                className={(s: NavState) =>
                  cn(
                    "relative flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-muted-foreground transition",
                    "hover:text-foreground",
                    s.isActive && "text-foreground",
                  )
                }
              >
                {(s: NavState) => (
                  <>
                    {s.isActive ? (
                      <motion.div
                        layoutId="bao-sidebar-active"
                        className="absolute inset-0 rounded-xl bg-foreground/8"
                        transition={{ type: "spring", stiffness: 380, damping: 32 }}
                      />
                    ) : null}
                    <item.icon className="relative h-4 w-4" />
                    {compact ? null : <span className="relative">{item.label}</span>}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </motion.aside>

        <main className="flex min-h-0 flex-1 flex-col px-6 py-6">
          <Topbar title={t("app.title")} />
          <div className="mt-4 min-h-0 flex-1">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
