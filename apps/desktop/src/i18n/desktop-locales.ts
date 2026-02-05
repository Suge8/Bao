import type { BaoLocale } from "@bao/i18n";

export const DESKTOP_LOCALES: Record<BaoLocale, Record<string, string>> = {
  zh: {
    "nav.chat": "对话",
    "nav.tasks": "任务",
    "nav.dimsums": "点心",
    "nav.memory": "记忆",
    "nav.settings": "设置",

    "page.chat.title": "对话",
    "page.tasks.title": "任务",
    "page.dimsums.title": "点心",
    "page.memory.title": "记忆",
    "page.settings.title": "设置",

    "settings.language": "语言",
    "common.on": "开",
    "common.off": "关",
  },
  en: {
    "nav.chat": "Chat",
    "nav.tasks": "Tasks",
    "nav.dimsums": "Dimsums",
    "nav.memory": "Memory",
    "nav.settings": "Settings",

    "page.chat.title": "Chat",
    "page.tasks.title": "Tasks",
    "page.dimsums.title": "Dimsums",
    "page.memory.title": "Memory",
    "page.settings.title": "Settings",

    "settings.language": "Language",
    "common.on": "On",
    "common.off": "Off",
  },
};
