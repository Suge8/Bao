import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

export type Toast = { id: string; title: string; description?: string };

type ToastContextValue = {
  toasts: Toast[];
  push: (input: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((input: Omit<Toast, "id">) => {
    const id = `toast-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const toast: Toast = { id, ...input };
    setToasts((prev) => [toast, ...prev].slice(0, 6));
    return id;
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      toasts,
      push,
      dismiss,
    }),
    [dismiss, push, toasts],
  );

  return React.createElement(ToastContext.Provider, { value }, children);
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
