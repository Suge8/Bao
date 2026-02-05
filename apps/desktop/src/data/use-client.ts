import React, { createContext, useContext, useMemo } from "react";
import type { DesktopClient } from "./client";
import { createTauriClient } from "./tauri-client";

const ClientContext = createContext<DesktopClient | null>(null);

export function ClientProvider({ children }: { children: React.ReactNode }) {
  const value = useMemo<DesktopClient>(() => {
    return createTauriClient();
  }, []);

  return React.createElement(ClientContext.Provider, { value }, children);
}

export function useClient(): DesktopClient {
  const ctx = useContext(ClientContext);
  if (!ctx) throw new Error("useClient must be used within ClientProvider");
  return ctx;
}
