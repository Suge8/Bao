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

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
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
  if (
    eventType.startsWith('message.') ||
    eventType.startsWith('sessions.') ||
    eventType === 'engine.turn' ||
    eventType.startsWith('provider.') ||
    eventType.startsWith('corrector.')
  ) {
    return 'message';
  }
  if (eventType.startsWith('tasks.')) return 'task';
  if (eventType.startsWith('memory.') || eventType.startsWith('memories.')) return 'memory';
  if (
    eventType.startsWith('auth.') ||
    eventType.startsWith('dimsums.') ||
    eventType.startsWith('settings.') ||
    eventType.startsWith('gateway.')
  ) {
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
  if (!eventType || !eventType.endsWith('.error')) return null;

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

export function aggregateErrorEvents(
  events: unknown[],
  dimension: MobileErrorAggregateDimension = 'global',
): MobileEventErrorAggregate[] {
  const grouped = new Map<string, MobileEventErrorAggregate>();

  for (const event of events) {
    const parsed = parseErrorEvent(event);
    if (!parsed) continue;

    const dimensionValue =
      dimension === 'provider'
        ? normalizeDimensionValue(parsed.provider)
        : dimension === 'session'
          ? normalizeDimensionValue(parsed.sessionId)
          : null;

    const key = `${dimension}|${dimensionValue ?? ''}|${parsed.eventType}|${parsed.code ?? ''}|${parsed.stage ?? ''}`;

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

  return [...grouped.values()].sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return (b.latestEventId ?? 0) - (a.latestEventId ?? 0);
  });
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
    if (b.count !== a.count) return b.count - a.count;
    return (b.latestEventId ?? 0) - (a.latestEventId ?? 0);
  });
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

    if (filterProvider && normalizeDimensionValue(parsed.provider) !== filterProvider) continue;
    if (filterSessionId && normalizeDimensionValue(parsed.sessionId) !== filterSessionId) continue;

    items.push({
      key: `${parsed.eventId ?? 'na'}|${parsed.eventType}|${parsed.code ?? ''}|${parsed.stage ?? ''}`,
      eventId: parsed.eventId,
      eventType: parsed.eventType,
      code: parsed.code,
      stage: parsed.stage,
      message: parsed.message,
      sessionId: parsed.sessionId,
      provider: parsed.provider,
    });

    if (items.length >= limit) break;
  }

  return items;
}
