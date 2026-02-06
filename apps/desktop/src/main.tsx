import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./globals.css";
import { I18nProvider } from "./i18n/i18n";
import { ClientProvider } from "./data/use-client";
import { subscribeBaoEvents } from "@/lib/bao-events";

// Runtime event log hook.
subscribeBaoEvents((evt) => {
  // eslint-disable-next-line no-console
  console.log("[bao:event]", evt.type, evt);
}).catch(() => {
  // ignore in non-tauri contexts
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <I18nProvider>
      <ClientProvider>
        <App />
      </ClientProvider>
    </I18nProvider>
  </React.StrictMode>,
);
