import React, { createContext, useContext, useMemo, useState } from 'react';
import { BAO_LOCALES, type BaoLocale } from '@bao/i18n';

type I18nContextValue = {
  locale: BaoLocale;
  setLocale: (locale: BaoLocale) => void;
  t: (key: string) => string;
};

type LocaleDict = Record<string, string>;

const I18nContext = createContext<I18nContextValue | null>(null);
const EMPTY_DICT: LocaleDict = {};

const MOBILE_LOCALES: Record<BaoLocale, LocaleDict> = {
  en: {
    'nav.connect': 'Connect',
    'nav.sessions': 'Sessions',
    'nav.chat': 'Chat',
    'nav.settings': 'Settings',

    'connect.title': 'Connect to Desktop',
    'connect.url': 'Gateway URL',
    'connect.token': 'Token',
    'connect.urlPlaceholder': 'ws://desktop.local:3901/ws',
    'connect.tokenPlaceholder': 'Paste pairing token from desktop',
    'connect.connect': 'Connect',
    'connect.connected': 'Connected',
    'connect.lastEvent': 'Last Event ID',
    'connect.events': 'Event Count',
    'connect.replayHint': 'Reconnect with same URL/token to resume event replay',
    'connect.replayState': 'Replay',
    'connect.replayOn': 'Resuming from lastEventId',
    'connect.replayOff': 'Fresh stream (no replay)',
    'connect.eventsByType': 'Events by Type',
    'events.message': 'Message',
    'events.task': 'Task',
    'events.memory': 'Memory',
    'events.audit': 'Audit',
    'events.other': 'Other',

    'sessions.title': 'Sessions',
    'sessions.fetchTasks': 'Fetch Tasks',
    'sessions.fetchDimsums': 'Fetch Dimsums',
    'sessions.fetchMemories': 'Fetch Memories',

    'actions.title': 'Quick Actions',
    'actions.fetchAll': 'Fetch All',
    'actions.fetchSessions': 'Fetch Sessions',
    'actions.fetchTasks': 'Fetch Tasks',
    'actions.fetchDimsums': 'Fetch Dimsums',
    'actions.fetchMemories': 'Fetch Memories',
    'actions.fetchSettings': 'Fetch Settings',

    'chat.title': 'Chat',
    'chat.sessionId': 'Session ID',
    'chat.message': 'Message',
    'chat.sessionIdPlaceholder': 'default-chat',
    'chat.messagePlaceholder': 'Type a message',
    'chat.send': 'Send',
    'chat.eventsFilter': 'Event Filter',

    'settings.title': 'Settings',
    'settings.language': 'Language',
    'settings.actions': 'Remote Actions',
    'settings.errorSummary': 'Error Summary',
    'settings.errorType': 'Type',
    'settings.errorCode': 'Code',
    'settings.errorStage': 'Stage',
    'settings.errorCount': 'Count',
    'settings.errorLatest': 'Latest Event ID',
    'settings.errorEmpty': 'No error events',
    'settings.errorAlerts': 'Error Alerts',
    'settings.errorEvents': 'Recent Error Events',
    'settings.errorDimension': 'Dimension',
    'settings.dimensionGlobal': 'Global',
    'settings.dimensionProvider': 'Provider',
    'settings.dimensionSession': 'Session',
    'settings.filterProvider': 'Provider Filter',
    'settings.filterSession': 'Session Filter',
    'settings.clearFilter': 'Clear Filter',
    'settings.warnThreshold': 'Warn Threshold',
    'settings.criticalThreshold': 'Critical Threshold',
    'settings.alertWarn': 'Warn',
    'settings.alertCritical': 'Critical',
    'settings.none': 'None',

    'common.refresh': 'Refresh',
    'common.disconnect': 'Disconnect',
    'common.empty': 'Empty',
    'common.on': 'On',
    'common.off': 'Off',
    'common.fetch': 'Fetch',
  },
  zh: {
    'nav.connect': '连接',
    'nav.sessions': '会话',
    'nav.chat': '聊天',
    'nav.settings': '设置',

    'connect.title': '连接桌面端',
    'connect.url': 'Gateway 地址',
    'connect.token': '令牌',
    'connect.urlPlaceholder': 'ws://desktop.local:3901/ws',
    'connect.tokenPlaceholder': '粘贴桌面端配对令牌',
    'connect.connect': '连接',
    'connect.connected': '连接状态',
    'connect.lastEvent': '最近事件 ID',
    'connect.events': '事件数量',
    'connect.replayHint': '使用相同地址与令牌重连，可继续按 lastEventId 回放',
    'connect.replayState': '回放状态',
    'connect.replayOn': '按 lastEventId 续播中',
    'connect.replayOff': '全新连接（无回放）',
    'connect.eventsByType': '事件分类统计',
    'events.message': '消息',
    'events.task': '任务',
    'events.memory': '记忆',
    'events.audit': '审计',
    'events.other': '其他',

    'sessions.title': '会话',
    'sessions.fetchTasks': '拉取任务',
    'sessions.fetchDimsums': '拉取点心',
    'sessions.fetchMemories': '拉取记忆',

    'actions.title': '快捷动作',
    'actions.fetchAll': '全部拉取',
    'actions.fetchSessions': '拉取会话',
    'actions.fetchTasks': '拉取任务',
    'actions.fetchDimsums': '拉取点心',
    'actions.fetchMemories': '拉取记忆',
    'actions.fetchSettings': '拉取设置',

    'chat.title': '聊天',
    'chat.sessionId': '会话 ID',
    'chat.message': '消息',
    'chat.sessionIdPlaceholder': 'default-chat',
    'chat.messagePlaceholder': '输入消息',
    'chat.send': '发送',
    'chat.eventsFilter': '事件筛选',

    'settings.title': '设置',
    'settings.language': '语言',
    'settings.actions': '远程动作',
    'settings.errorSummary': '错误聚合',
    'settings.errorType': '类型',
    'settings.errorCode': '错误码',
    'settings.errorStage': '阶段',
    'settings.errorCount': '次数',
    'settings.errorLatest': '最近事件 ID',
    'settings.errorEmpty': '暂无错误事件',
    'settings.errorAlerts': '错误告警',
    'settings.errorEvents': '最近错误事件',
    'settings.errorDimension': '聚合维度',
    'settings.dimensionGlobal': '全局',
    'settings.dimensionProvider': '按 Provider',
    'settings.dimensionSession': '按 Session',
    'settings.filterProvider': 'Provider 过滤',
    'settings.filterSession': 'Session 过滤',
    'settings.clearFilter': '清空过滤',
    'settings.warnThreshold': '预警阈值',
    'settings.criticalThreshold': '严重阈值',
    'settings.alertWarn': '预警',
    'settings.alertCritical': '严重',
    'settings.none': '无',

    'common.refresh': '刷新',
    'common.disconnect': '断开',
    'common.empty': '暂无数据',
    'common.on': '开',
    'common.off': '关',
    'common.fetch': '拉取',
  },
};

function getBaseLocale(locale: BaoLocale): LocaleDict {
  return (BAO_LOCALES[locale] as LocaleDict | undefined) ?? EMPTY_DICT;
}

function getMobileLocale(locale: BaoLocale): LocaleDict {
  return MOBILE_LOCALES[locale] ?? EMPTY_DICT;
}

function getString(locale: BaoLocale, key: string): string {
  // Merge strategy: packages/i18n -> mobile overrides.
  // If not found, fallback to key itself (deterministic).
  const base = getBaseLocale(locale);
  const local = getMobileLocale(locale);
  return local[key] ?? base[key] ?? key;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<BaoLocale>('zh');
  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key: string) => getString(locale, key),
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
