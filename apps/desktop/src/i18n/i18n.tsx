import React, { createContext, useContext, useMemo, useState } from "react";
import { BAO_LOCALES, type BaoLocale } from "@bao/i18n";
import { DESKTOP_LOCALES } from "./desktop-locales";

type I18nContextValue = {
  locale: BaoLocale;
  setLocale: (locale: BaoLocale) => void;
  t: (key: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

function getString(locale: BaoLocale, key: string): string {
  // Merge strategy: packages/i18n -> desktop overrides.
  // If not found, fallback to key itself (deterministic).
  const base = (BAO_LOCALES[locale] as Record<string, string> | undefined) ?? {};
  const local = DESKTOP_LOCALES[locale] ?? {};
  return local[key] ?? base[key] ?? key;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<BaoLocale>("zh");
  const value = useMemo<I18nContextValue>(() => {
    return {
      locale,
      setLocale,
      t: (key: string) => getString(locale, key),
    };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
