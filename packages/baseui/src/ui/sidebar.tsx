import React from "react";
import { cn } from "../lib/cn";

export function Sidebar({
  compact,
  children,
  className,
}: {
  compact: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <aside
      className={cn(
        "shrink-0 px-4 py-5",
        compact ? "w-[88px]" : "w-[280px]",
        className,
      )}
    >
      {children}
    </aside>
  );
}
