export type MobileEventCategory = 'message' | 'task' | 'memory' | 'audit' | 'other';

export type MobileErrorAggregateDimension = 'global' | 'provider' | 'session';

export type MobileEventErrorAggregate = {
  key: string;
  dimension: MobileErrorAggregateDimension;
  dimensionValue: string | null;
  eventType: string;
  code: string | null;
  stage: string | null;
  message: string;
  count: number;
  latestEventId: number | null;
  sessionId: string | null;
  provider: string | null;
};

export type MobileEventErrorAlertLevel = 'warn' | 'critical';

export type MobileEventErrorAlert = {
  key: string;
  level: MobileEventErrorAlertLevel;
  aggregateKey: string;
  dimension: MobileErrorAggregateDimension;
  dimensionValue: string | null;
  eventType: string;
  code: string | null;
  count: number;
  latestEventId: number | null;
};

export type MobileEventErrorItem = {
  key: string;
  eventId: number | null;
  eventType: string;
  code: string | null;
  stage: string | null;
  message: string;
  sessionId: string | null;
  provider: string | null;
};

type ParsedErrorEvent = {
  eventId: number | null;
  eventType: string;
  code: string | null;
  stage: string | null;
  message: string;
  sessionId: string | null;
  provider: string | null;
};

const CATEGORY_PREFIXES = {
  message: ['message.', 'sessions.', 'provider.', 'corrector.'],
  task: ['tasks.'],
  memory: ['memory.', 'memories.'],
  audit: ['auth.', 'dimsums.', 'settings.', 'gateway.'],
} as const;

const SPECIAL_MESSAGE_TYPE = 'engine.turn';
const ERROR_SUFFIX = '.error';

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function startsWithAny(value: string, prefixes: readonly string[]): boolean {
  return prefixes.some((prefix) => value.startsWith(prefix));
}

function getPayload(event: unknown): Record<string, unknown> | null {
  if (!isObject(event)) return null;
  const payload = event.payload;
  return isObject(payload) ? payload : null;
}

function getStringField(obj: Record<string, unknown> | null, key: string): string | null {
  if (!obj) return null;
  const raw = obj[key];
  return typeof raw === 'string' && raw.trim() ? raw : null;
}

function normalizeDimensionValue(value: string | null): string {
  return value && value.trim() ? value : 'unknown';
}

export function getEventId(event: unknown): number | null {
  if (!isObject(event)) return null;
  const raw = event.eventId;
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  return null;
}

export function getEventType(event: unknown): string | null {
  if (!isObject(event)) return null;
  const raw = event.type;
  return typeof raw === 'string' ? raw : null;
}

export function classifyEventCategory(eventType: string | null): MobileEventCategory {
  if (!eventType) return 'other';
  if (eventType === SPECIAL_MESSAGE_TYPE || startsWithAny(eventType, CATEGORY_PREFIXES.message)) {
    return 'message';
  }
  if (startsWithAny(eventType, CATEGORY_PREFIXES.task)) return 'task';
  if (startsWithAny(eventType, CATEGORY_PREFIXES.memory)) return 'memory';
  if (startsWithAny(eventType, CATEGORY_PREFIXES.audit)) {
    return 'audit';
  }
  return 'other';
}

export function countEventsByCategory(events: unknown[]): Record<MobileEventCategory, number> {
  const counts: Record<MobileEventCategory, number> = {
    message: 0,
    task: 0,
    memory: 0,
    audit: 0,
    other: 0,
  };

  for (const event of events) {
    const category = classifyEventCategory(getEventType(event));
    counts[category] += 1;
  }

  return counts;
}

function parseErrorEvent(event: unknown): ParsedErrorEvent | null {
  const eventType = getEventType(event);
  if (!eventType || !eventType.endsWith(ERROR_SUFFIX)) return null;

  const payload = getPayload(event);
  return {
    eventId: getEventId(event),
    eventType,
    code: getStringField(payload, 'code'),
    stage: getStringField(payload, 'stage'),
    message: getStringField(payload, 'error') ?? 'unknown error',
    sessionId: getStringField(payload, 'sessionId'),
    provider: getStringField(payload, 'provider'),
  };
}

function getAggregateDimensionValue(
  parsed: ParsedErrorEvent,
  dimension: MobileErrorAggregateDimension,
): string | null {
  if (dimension === 'provider') return normalizeDimensionValue(parsed.provider);
  if (dimension === 'session') return normalizeDimensionValue(parsed.sessionId);
  return null;
}

function getAggregateKey(
  parsed: ParsedErrorEvent,
  dimension: MobileErrorAggregateDimension,
  dimensionValue: string | null,
): string {
  return `${dimension}|${dimensionValue ?? ''}|${parsed.eventType}|${parsed.code ?? ''}|${parsed.stage ?? ''}`;
}

function sortByCountThenLatestEventIdDesc(
  a: { count: number; latestEventId: number | null },
  b: { count: number; latestEventId: number | null },
): number {
  if (b.count !== a.count) return b.count - a.count;
  return (b.latestEventId ?? 0) - (a.latestEventId ?? 0);
}

export function aggregateErrorEvents(
  events: unknown[],
  dimension: MobileErrorAggregateDimension = 'global',
): MobileEventErrorAggregate[] {
  const grouped = new Map<string, MobileEventErrorAggregate>();

  for (const event of events) {
    const parsed = parseErrorEvent(event);
    if (!parsed) continue;

    const dimensionValue = getAggregateDimensionValue(parsed, dimension);
    const key = getAggregateKey(parsed, dimension, dimensionValue);

    const prev = grouped.get(key);
    if (!prev) {
      grouped.set(key, {
        key,
        dimension,
        dimensionValue,
        eventType: parsed.eventType,
        code: parsed.code,
        stage: parsed.stage,
        message: parsed.message,
        count: 1,
        latestEventId: parsed.eventId,
        sessionId: parsed.sessionId,
        provider: parsed.provider,
      });
      continue;
    }

    prev.count += 1;
    if (parsed.eventId != null && (prev.latestEventId == null || parsed.eventId > prev.latestEventId)) {
      prev.latestEventId = parsed.eventId;
      prev.message = parsed.message;
      prev.sessionId = parsed.sessionId;
      prev.provider = parsed.provider;
    }
  }

  return [...grouped.values()].sort(sortByCountThenLatestEventIdDesc);
}

export function buildErrorAlerts(
  aggregates: MobileEventErrorAggregate[],
  warnThreshold = 3,
  criticalThreshold = 6,
): MobileEventErrorAlert[] {
  const alerts: MobileEventErrorAlert[] = [];

  for (const aggregate of aggregates) {
    if (aggregate.count < warnThreshold) continue;
    const level: MobileEventErrorAlertLevel = aggregate.count >= criticalThreshold ? 'critical' : 'warn';
    alerts.push({
      key: `${aggregate.key}|${level}`,
      level,
      aggregateKey: aggregate.key,
      dimension: aggregate.dimension,
      dimensionValue: aggregate.dimensionValue,
      eventType: aggregate.eventType,
      code: aggregate.code,
      count: aggregate.count,
      latestEventId: aggregate.latestEventId,
    });
  }

  return alerts.sort((a, b) => {
    if (a.level !== b.level) return a.level === 'critical' ? -1 : 1;
    return sortByCountThenLatestEventIdDesc(a, b);
  });
}

function shouldIncludeErrorEvent(
  parsed: ParsedErrorEvent,
  provider: string | null,
  sessionId: string | null,
): boolean {
  if (provider && normalizeDimensionValue(parsed.provider) !== provider) return false;
  if (sessionId && normalizeDimensionValue(parsed.sessionId) !== sessionId) return false;
  return true;
}

function toErrorItem(parsed: ParsedErrorEvent): MobileEventErrorItem {
  return {
    key: `${parsed.eventId ?? 'na'}|${parsed.eventType}|${parsed.code ?? ''}|${parsed.stage ?? ''}`,
    eventId: parsed.eventId,
    eventType: parsed.eventType,
    code: parsed.code,
    stage: parsed.stage,
    message: parsed.message,
    sessionId: parsed.sessionId,
    provider: parsed.provider,
  };
}

export function listErrorEvents(
  events: unknown[],
  options?: {
    provider?: string | null;
    sessionId?: string | null;
    limit?: number;
  },
): MobileEventErrorItem[] {
  const filterProvider = options?.provider ?? null;
  const filterSessionId = options?.sessionId ?? null;
  const limit = options?.limit ?? 120;
  const items: MobileEventErrorItem[] = [];

  for (const event of [...events].reverse()) {
    const parsed = parseErrorEvent(event);
    if (!parsed) continue;

    if (!shouldIncludeErrorEvent(parsed, filterProvider, filterSessionId)) continue;

    items.push(toErrorItem(parsed));

    if (items.length >= limit) break;
  }

  return items;
}
