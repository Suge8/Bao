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

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function toSafeString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function toSafeCategory(value: unknown): MobileEventCategory | null {
  return typeof value === 'string' && CATEGORY_SET.has(value as MobileEventCategory)
    ? (value as MobileEventCategory)
    : null;
}

function toSafeDimension(value: unknown): MobileErrorAggregateDimension | null {
  return typeof value === 'string' && DIMENSION_SET.has(value as MobileErrorAggregateDimension)
    ? (value as MobileErrorAggregateDimension)
    : null;
}

function toPositiveInt(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const n = Math.floor(value);
  return n > 0 ? n : null;
}

function getPrefsFile(): File {
  return new File(Paths.document, PREFS_DIR_NAME, PREFS_FILE_NAME);
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

    const url = toSafeString(json.url);
    const token = typeof json.token === 'string' ? json.token : null;
    const selectedCategory = toSafeCategory(json.selectedCategory);
    const errorDimension = toSafeDimension(json.errorDimension);
    const errorWarnThreshold = toPositiveInt(json.errorWarnThreshold);
    const errorCriticalThreshold = toPositiveInt(json.errorCriticalThreshold);

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
      selectedErrorProvider: toSafeString(json.selectedErrorProvider),
      selectedErrorSessionId: toSafeString(json.selectedErrorSessionId),
      errorWarnThreshold,
      errorCriticalThreshold,
    };
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
