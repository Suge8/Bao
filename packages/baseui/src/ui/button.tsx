import React from "react";
import { cn } from "../lib/cn";

export function Button({
  className,
  variant = "default",
  size = "md",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "ghost" | "danger";
  size?: "sm" | "md";
}) {
  return (
    <button
      type={props.type ?? "button"}
      className={cn(
        "inline-flex items-center justify-center rounded-xl font-medium transition",
        "disabled:pointer-events-none disabled:opacity-50",
        size === "sm" ? "h-9 px-3 text-sm" : "h-10 px-4 text-sm",
        variant === "default" && "bg-foreground text-background hover:opacity-90",
        variant === "ghost" && "bg-foreground/5 text-foreground hover:bg-foreground/10",
        variant === "danger" && "bg-destructive text-primary-foreground hover:opacity-90",
        className,
      )}
      {...props}
    />
  );
}
