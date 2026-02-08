import { NavLink, Outlet } from "react-router-dom";
import { motion } from "motion/react";
import { Brain, Cog, LayoutGrid, ListChecks, MessageSquare, PanelLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n/i18n";
import { Topbar } from "@/components/layout/topbar";
import { DotPattern } from "@/components/ui/dot-pattern";
import { MagicCard } from "@/components/ui/magic-card";
import { useMemo, useState } from "react";

type NavState = {
  isActive: boolean;
  isPending: boolean;
};

const SIDEBAR_TRANSITION = { duration: 0.3, ease: [0.22, 1, 0.36, 1] as const };

const NAV = [
  { to: "/", labelKey: "nav.chat", icon: MessageSquare },
  { to: "/tasks", labelKey: "nav.tasks", icon: ListChecks },
  { to: "/dimsums", labelKey: "nav.dimsums", icon: LayoutGrid },
  { to: "/memory", labelKey: "nav.memory", icon: Brain },
  { to: "/settings", labelKey: "nav.settings", icon: Cog },
] as const;

function getSidebarPaddingClass(compact: boolean): string {
  return compact ? "p-2" : "p-4";
}

function getHeaderLayoutClass(compact: boolean): string {
  return compact ? "justify-center" : "justify-between gap-2";
}

function getNavLayoutClass(compact: boolean): string {
  return compact ? "mt-6 items-center gap-2" : "mt-8 gap-1.5";
}

function getNavItemLayoutClass(compact: boolean): string {
  return compact ? "h-10 w-10 justify-center" : "gap-3 px-3 py-2.5";
}

function toNavTestId(path: string): string {
  return `nav-${path === "/" ? "chat" : path.slice(1)}`;
}

export function AppShell() {
  const { t } = useI18n();
  const [compact, setCompact] = useState(false);
  const sidebarPaddingClass = getSidebarPaddingClass(compact);
  const headerLayoutClass = getHeaderLayoutClass(compact);
  const navLayoutClass = getNavLayoutClass(compact);
  const navItemLayoutClass = getNavItemLayoutClass(compact);

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
          animate={{ width: compact ? 72 : 236 }}
          transition={SIDEBAR_TRANSITION}
          className={cn("h-full min-h-0 shrink-0", sidebarPaddingClass)}
        >
          <MagicCard className="h-full rounded-3xl border border-border/50 bg-background/60 backdrop-blur-xl">
            <div className={cn("flex h-full flex-col", sidebarPaddingClass)}>
              <div className={cn("flex items-center", headerLayoutClass)}>
                {compact ? null : (
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary">
                      <Brain className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="truncate text-base font-bold tracking-tight">{t("app.title")}</div>
                      <div className="truncate text-xs text-muted-foreground font-medium">{t("app.shell.stage")}</div>
                    </div>
                  </div>
                )}

                <button
                  type="button"
                  aria-label={t("app.shell.toggle_sidebar")}
                  data-testid="sidebar-toggle"
                  className={cn(
                    "group flex shrink-0 items-center justify-center transition-all",
                    compact
                      ? "h-8 w-8 rounded-lg text-foreground/75 hover:bg-muted/55 hover:text-foreground"
                      : "h-9 w-9 rounded-xl border border-border/60 bg-background/70 text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                  onClick={() => setCompact((v) => !v)}
                >
                  <PanelLeft className={cn("h-4 w-4 transition-transform", compact && "rotate-180")} />
                </button>
              </div>

              <nav className={cn("flex flex-col", navLayoutClass)}>
                {nav.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    aria-label={item.label}
                    data-testid={toNavTestId(item.to)}
                    className={(s: NavState) =>
                      cn(
                        "group relative flex items-center rounded-xl text-sm font-medium transition-all duration-200",
                        navItemLayoutClass,
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
                        <item.icon
                          className={cn(
                            "relative shrink-0 transition-transform group-hover:scale-110",
                            compact ? "h-5 w-5" : "h-4 w-4",
                            s.isActive ? "text-primary" : compact && "text-foreground/85 group-hover:text-foreground",
                          )}
                        />
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
