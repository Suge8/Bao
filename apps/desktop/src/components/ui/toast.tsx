import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "info";

type ToastInput = {
  variant?: ToastVariant;
  title: string;
  description?: string;
  durationMs?: number;
};

type ToastItem = ToastInput & {
  id: string;
};

type ToastContextValue = {
  push: (input: ToastInput) => void;
};

const noopToastContext: ToastContextValue = {
  push: () => {
    // no-op fallback for pages rendered outside provider
  },
};

const ToastContext = createContext<ToastContextValue>(noopToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const push = useCallback(
    (input: ToastInput) => {
      const id = `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const item: ToastItem = {
        id,
        variant: input.variant ?? "info",
        title: input.title,
        description: input.description,
        durationMs: input.durationMs ?? 3200,
      };
      setItems((prev) => [item, ...prev].slice(0, 4));
      window.setTimeout(() => remove(id), item.durationMs);
    },
    [remove],
  );

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[200] flex w-[320px] max-w-[90vw] flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={cn(
              "pointer-events-auto rounded-xl border px-3 py-2 shadow-lg backdrop-blur",
              item.variant === "success" && "border-emerald-400/40 bg-emerald-500/10 text-emerald-100",
              item.variant === "error" && "border-red-400/40 bg-red-500/10 text-red-100",
              item.variant === "info" && "border-slate-300/40 bg-slate-900/90 text-slate-100",
            )}
          >
            <div className="text-sm font-semibold">{item.title}</div>
            {item.description ? <div className="mt-1 text-xs opacity-90">{item.description}</div> : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}
