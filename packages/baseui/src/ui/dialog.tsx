import React, { useEffect } from "react";
import { cn } from "../lib/cn";

export function Dialog({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    if (!open) return;
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 cursor-pointer bg-foreground/10"
        onClick={() => onOpenChange(false)}
      />
      <div className="relative mx-auto mt-24 w-[min(560px,calc(100vw-2rem))] rounded-2xl bg-background p-4 shadow-lg">
        <div className="text-sm font-semibold">{title}</div>
        <div className={cn("mt-3")}>{children}</div>
      </div>
    </div>
  );
}
