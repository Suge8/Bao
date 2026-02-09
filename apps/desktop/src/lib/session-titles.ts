type SessionTitleSource = {
  id: string;
  title?: string | null;
};

const GENERATED_SESSION_ID_RE = /^s-[0-9a-z]+-[0-9a-z]{4}$/i;

export function buildDefaultSessionTitle(baseLabel: string, _sessions: SessionTitleSource[]): string {
  return normalizeBaseLabel(baseLabel);
}

export function getSessionDisplayTitle(
  baseLabel: string,
  sessionId: string,
  title?: string | null,
): string {
  const label = normalizeBaseLabel(baseLabel);
  const normalizedTitle = normalizeTitle(title);
  if (
    normalizedTitle &&
    !looksLikeGeneratedSessionId(normalizedTitle) &&
    !isLegacySystemTitle(normalizedTitle, sessionId) &&
    !looksLikeSystemNumberedTitle(normalizedTitle, label)
  ) {
    return normalizedTitle;
  }
  return label;
}

function looksLikeGeneratedSessionId(value: string): boolean {
  return GENERATED_SESSION_ID_RE.test(value);
}

function isLegacySystemTitle(value: string, sessionId: string): boolean {
  const lowered = value.toLowerCase();
  if (lowered === "default session" || lowered === "default" || lowered === "默认对话") {
    return true;
  }
  return value === sessionId;
}

function looksLikeSystemNumberedTitle(value: string, baseLabel: string): boolean {
  const escaped = escapeRegExp(baseLabel);
  return new RegExp(`^${escaped}\\s+\\d+$`).test(value);
}

function normalizeTitle(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeBaseLabel(value: string): string {
  const title = value.trim();
  return title.length > 0 ? title : "Chat";
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
