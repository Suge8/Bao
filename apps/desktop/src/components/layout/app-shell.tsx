import { NavLink, Outlet } from "react-router-dom";
import { motion } from "motion/react";
import { Brain, Cog, LayoutGrid, ListChecks, MessageSquare, PanelLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n/i18n";
import { Topbar } from "@/components/layout/topbar";
import { DotPattern } from "@/components/ui/dot-pattern";
import { MagicCard } from "@/components/ui/magic-card";
import { ShinyButton } from "@/components/ui/shiny-button";
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
    <div className="relative h-full overflow-hidden bg-background text-foreground selection:bg-primary/20">
      <DotPattern
        className="pointer-events-none text-foreground/[0.03]"
        width={32}
        height={32}
        cr={1}
        cx={1}
        cy={1}
        aria-hidden
      />
      <div className="relative z-10 flex h-full min-h-0">
        <motion.aside
          animate={{ width: compact ? 88 : 280 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="h-full min-h-0 shrink-0 p-4"
        >
          <MagicCard className="h-full rounded-3xl border border-border/50 bg-background/60 backdrop-blur-xl">
            <div className="flex h-full flex-col p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary">
                    <Brain className="h-5 w-5" />
                  </div>
                  {compact ? null : (
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="truncate text-base font-bold tracking-tight">Bao</div>
                      <div className="truncate text-xs text-muted-foreground font-medium">Stage 2</div>
                    </div>
                  )}
                </div>

                <ShinyButton
                  type="button"
                  aria-label="Toggle Sidebar"
                  data-testid="sidebar-toggle"
                  className="group h-8 w-8 rounded-lg p-0 hover:bg-muted/50"
                  onClick={() => setCompact((v) => !v)}
                >
                  <PanelLeft className="h-4 w-4 text-muted-foreground transition-colors group-hover:text-foreground" />
                </ShinyButton>
              </div>

              <nav className="mt-8 flex flex-col gap-1.5">
                {nav.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    aria-label={item.label}
                    data-testid={`nav-${item.to === "/" ? "chat" : item.to.slice(1)}`}
                    className={(s: NavState) =>
                      cn(
                        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                        s.isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                      )
                    }
                  >
                    {(s: NavState) => (
                      <>
                        {s.isActive ? (
                          <motion.div
                            layoutId="bao-sidebar-active"
                            className="absolute inset-0 rounded-xl bg-muted"
                            transition={{ type: "spring", stiffness: 300, damping: 30 }}
                          />
                        ) : null}
                        <item.icon className={cn("relative h-4 w-4 transition-transform group-hover:scale-110", s.isActive && "text-primary")} />
                        {compact ? null : <span className="relative truncate">{item.label}</span>}
                      </>
                    )}
                  </NavLink>
                ))}
              </nav>
            </div>
          </MagicCard>
        </motion.aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden px-6 py-4">
          <Topbar title={t("app.title")} />
          <div className="mt-6 min-h-0 min-w-0 flex-1 overflow-hidden">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
