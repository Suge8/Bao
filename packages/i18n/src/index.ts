import en from "./locales/en.json";
import zh from "./locales/zh.json";

export type BaoLocale = "en" | "zh";

export const BAO_LOCALES = {
  en,
  zh,
} as const;
