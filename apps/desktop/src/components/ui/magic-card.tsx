import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type MagicCardProps = HTMLAttributes<HTMLDivElement> & {
  gradientSize?: number;
  gradientColor?: string;
  gradientOpacity?: number;
  gradientFrom?: string;
  gradientTo?: string;
};

export function MagicCard({
  children,
  className,
  gradientSize: _gradientSize = 180,
  gradientColor: _gradientColor = "#0f172a",
  gradientOpacity: _gradientOpacity = 0.45,
  gradientFrom: _gradientFrom = "#14b8a6",
  gradientTo: _gradientTo = "#22d3ee",
  ...props
}: MagicCardProps) {
  return (
    <div className={cn("relative rounded-[inherit] border border-border/45 shadow-[0_1px_2px_rgba(2,6,23,0.05)]", className)} {...props}>
      <div className="pointer-events-none absolute inset-0 rounded-[inherit] bg-gradient-to-b from-white/35 to-transparent dark:from-white/[0.03]" />
      <div className="relative">{children}</div>
    </div>
  );
}
