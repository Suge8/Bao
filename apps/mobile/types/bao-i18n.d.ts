declare module '@bao/i18n' {
  export type BaoLocale = 'en' | 'zh';

  export const BAO_LOCALES: {
    en: Record<string, string>;
    zh: Record<string, string>;
  };
}
