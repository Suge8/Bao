type SessionTitleSource = {
  id: string;
  title?: string | null;
};

const GENERATED_SESSION_ID_RE = /^s-[0-9a-z]+-[0-9a-z]{4}$/i;

export function buildDefaultSessionTitle(baseLabel: string, sessions: SessionTitleSource[]): string {
  const label = normalizeBaseLabel(baseLabel);
  const escaped = escapeRegExp(label);
  const numberedPattern = new RegExp(`^${escaped}\\s+(\\d+)$`);
  const usedNumbers = new Set<number>();

  for (const session of sessions) {
    const rawTitle = normalizeTitle(session.title);
    if (!rawTitle) continue;
    if (rawTitle === label) {
      usedNumbers.add(1);
      continue;
    }
    const matched = numberedPattern.exec(rawTitle);
    if (!matched) continue;
    const nextNumber = Number.parseInt(matched[1], 10);
    if (Number.isFinite(nextNumber) && nextNumber > 0) {
      usedNumbers.add(nextNumber);
    }
  }

  let number = 1;
  while (usedNumbers.has(number)) {
    number += 1;
  }
  return `${label} ${number}`;
}

export function getSessionDisplayTitle(
  baseLabel: string,
  sessionId: string,
  title?: string | null,
): string {
  const label = normalizeBaseLabel(baseLabel);
  const normalizedTitle = normalizeTitle(title);
  if (normalizedTitle && !looksLikeGeneratedSessionId(normalizedTitle)) {
    return normalizedTitle;
  }

  const suffix = parseGeneratedSessionTime(sessionId);
  if (!suffix) {
    return label;
  }
  return `${label} ${suffix}`;
}

function parseGeneratedSessionTime(sessionId: string): string | null {
  const matched = GENERATED_SESSION_ID_RE.exec(sessionId);
  if (!matched) return null;
  const ts = Number.parseInt(matched[1], 36);
  if (!Number.isFinite(ts) || ts <= 0) return null;

  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return null;
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function looksLikeGeneratedSessionId(value: string): boolean {
  return GENERATED_SESSION_ID_RE.test(value);
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
