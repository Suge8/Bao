import { NavLink, Outlet } from "react-router-dom";
import { motion } from "motion/react";
import { Brain, Cog, LayoutGrid, ListChecks, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

type NavState = {
  isActive: boolean;
  isPending: boolean;
};

const NAV = [
  { to: "/", label: "对话", icon: MessageSquare },
  { to: "/tasks", label: "任务", icon: ListChecks },
  { to: "/dimsums", label: "点心", icon: LayoutGrid },
  { to: "/memory", label: "记忆", icon: Brain },
  { to: "/settings", label: "设置", icon: Cog },
] as const;

export function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">
        <aside className="w-[280px] shrink-0 px-4 py-5">
          <div className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-xl bg-foreground/10" />
            <div className="leading-tight">
              <div className="text-sm font-semibold">Bao</div>
              <div className="text-xs text-muted-foreground">Stage 0</div>
            </div>
          </div>

          <nav className="mt-6 flex flex-col gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
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
                    <span className="relative">{item.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
