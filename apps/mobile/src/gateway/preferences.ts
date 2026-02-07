import { Directory, File, Paths } from 'expo-file-system';
import { type MobileErrorAggregateDimension, type MobileEventCategory } from './events';

const PREFS_DIR_NAME = 'bao-mobile';
const PREFS_FILE_NAME = 'gateway-preferences.v1.json';

const CATEGORY_SET = new Set<MobileEventCategory>(['message', 'task', 'memory', 'audit', 'other']);
const DIMENSION_SET = new Set<MobileErrorAggregateDimension>(['global', 'provider', 'session']);

export type GatewayPreferences = {
  url: string;
  token: string;
  selectedCategory: MobileEventCategory;
  errorDimension: MobileErrorAggregateDimension;
  selectedErrorProvider: string | null;
  selectedErrorSessionId: string | null;
  errorWarnThreshold: number;
  errorCriticalThreshold: number;
};

type RawGatewayPreferences = {
  url: unknown;
  token: unknown;
  selectedCategory: unknown;
  errorDimension: unknown;
  selectedErrorProvider: unknown;
  selectedErrorSessionId: unknown;
  errorWarnThreshold: unknown;
  errorCriticalThreshold: unknown;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function toSafeString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function toSafeCategory(value: unknown): MobileEventCategory | null {
  if (typeof value !== 'string' || !CATEGORY_SET.has(value as MobileEventCategory)) return null;
  return value as MobileEventCategory;
}

function toSafeDimension(value: unknown): MobileErrorAggregateDimension | null {
  if (typeof value !== 'string' || !DIMENSION_SET.has(value as MobileErrorAggregateDimension)) return null;
  return value as MobileErrorAggregateDimension;
}

function toPositiveInt(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const n = Math.floor(value);
  return n > 0 ? n : null;
}

function getPrefsFile(): File {
  return new File(Paths.document, PREFS_DIR_NAME, PREFS_FILE_NAME);
}

function toRawPreferences(json: Record<string, unknown>): RawGatewayPreferences {
  return {
    url: json.url,
    token: json.token,
    selectedCategory: json.selectedCategory,
    errorDimension: json.errorDimension,
    selectedErrorProvider: json.selectedErrorProvider,
    selectedErrorSessionId: json.selectedErrorSessionId,
    errorWarnThreshold: json.errorWarnThreshold,
    errorCriticalThreshold: json.errorCriticalThreshold,
  };
}

function parseGatewayPreferences(raw: RawGatewayPreferences): GatewayPreferences | null {
  const url = toSafeString(raw.url);
  const token = typeof raw.token === 'string' ? raw.token : null;
  const selectedCategory = toSafeCategory(raw.selectedCategory);
  const errorDimension = toSafeDimension(raw.errorDimension);
  const errorWarnThreshold = toPositiveInt(raw.errorWarnThreshold);
  const errorCriticalThreshold = toPositiveInt(raw.errorCriticalThreshold);

  if (
    !url ||
    token == null ||
    !selectedCategory ||
    !errorDimension ||
    !errorWarnThreshold ||
    !errorCriticalThreshold
  ) {
    return null;
  }

  return {
    url,
    token,
    selectedCategory,
    errorDimension,
    selectedErrorProvider: toSafeString(raw.selectedErrorProvider),
    selectedErrorSessionId: toSafeString(raw.selectedErrorSessionId),
    errorWarnThreshold,
    errorCriticalThreshold,
  };
}

function ensurePrefsDir(): void {
  const dir = new Directory(Paths.document, PREFS_DIR_NAME);
  if (!dir.exists) {
    dir.create({ idempotent: true, intermediates: true, overwrite: false });
  }
}

export async function loadGatewayPreferences(): Promise<GatewayPreferences | null> {
  try {
    const file = getPrefsFile();
    if (!file.exists) return null;

    const raw = await file.text();
    const json: unknown = JSON.parse(raw);
    if (!isObject(json)) return null;
    return parseGatewayPreferences(toRawPreferences(json));
  } catch {
    return null;
  }
}

export function saveGatewayPreferences(prefs: GatewayPreferences): void {
  try {
    ensurePrefsDir();
    const file = getPrefsFile();
    if (!file.exists) {
      file.create({ intermediates: true, overwrite: true });
    }
    file.write(JSON.stringify(prefs));
  } catch {
    // ignore persistence failures to keep gateway stream usable.
  }
}
