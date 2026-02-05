import React, { createContext, useContext, useMemo, useState } from 'react';
import { BAO_LOCALES, type BaoLocale } from '@bao/i18n';

type I18nContextValue = {
  locale: BaoLocale;
  setLocale: (locale: BaoLocale) => void;
  t: (key: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

const MOBILE_LOCALES: Record<BaoLocale, Record<string, string>> = {
  en: {
    'nav.connect': 'Connect',
    'nav.sessions': 'Sessions',
    'nav.chat': 'Chat',
    'nav.settings': 'Settings',

    'connect.title': 'Connect to Desktop',
    'connect.url': 'Gateway URL',
    'connect.token': 'Token',
    'connect.connect': 'Connect',

    'sessions.title': 'Sessions',

    'chat.title': 'Chat',
    'chat.sessionId': 'Session ID',
    'chat.message': 'Message',
    'chat.send': 'Send',

    'settings.title': 'Settings',
    'settings.language': 'Language',

    'common.refresh': 'Refresh',
    'common.disconnect': 'Disconnect',
    'common.empty': 'Empty',
    'common.on': 'On',
    'common.off': 'Off',
  },
  zh: {
    'nav.connect': '连接',
    'nav.sessions': '会话',
    'nav.chat': '聊天',
    'nav.settings': '设置',

    'connect.title': '连接桌面端',
    'connect.url': 'Gateway 地址',
    'connect.token': '令牌',
    'connect.connect': '连接',

    'sessions.title': '会话',

    'chat.title': '聊天',
    'chat.sessionId': '会话 ID',
    'chat.message': '消息',
    'chat.send': '发送',

    'settings.title': '设置',
    'settings.language': '语言',

    'common.refresh': '刷新',
    'common.disconnect': '断开',
    'common.empty': '暂无数据',
    'common.on': '开',
    'common.off': '关',
  },
};

function getString(locale: BaoLocale, key: string): string {
  // Merge strategy: packages/i18n -> mobile overrides.
  // If not found, fallback to key itself (deterministic).
  const base = (BAO_LOCALES[locale] as Record<string, string> | undefined) ?? {};
  const local = MOBILE_LOCALES[locale] ?? {};
  return local[key] ?? base[key] ?? key;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<BaoLocale>('zh');
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
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
