type BaoSetting = {
  key: string;
  value: unknown;
};

export type ProviderProfile = {
  id: string;
  name: string;
  provider: string;
  modelIds: string[];
  baseUrl: string;
  apiKey: string;
};

export type ProviderModelProfile = ProviderProfile & {
  model: string;
  modelKey: string;
};

type ProviderState = {
  profiles: ProviderProfile[];
  selectedProfileId: string;
};

export function toSettingsMap(settings: BaoSetting[]): Map<string, unknown> {
  return new Map(settings.map((item) => [item.key, item.value] as const));
}

export function createProfileDraft(): ProviderProfile {
  return {
    id: createId(),
    name: "",
    provider: "",
    modelIds: [],
    baseUrl: "",
    apiKey: "",
  };
}

export function expandProfilesToModelProfiles(profiles: ProviderProfile[]): ProviderModelProfile[] {
  const out: ProviderModelProfile[] = [];
  for (const item of profiles) {
    for (const model of item.modelIds) {
      const modelId = model.trim();
      if (!modelId) continue;
      out.push({
        ...item,
        model: modelId,
        modelKey: `${item.id}:${modelId}`,
      });
    }
  }
  return out;
}

export function parseProviderState(entries: Map<string, unknown>): ProviderState {
  const fromProfiles = parseProfiles(entries.get("provider.profiles"));
  const profiles = fromProfiles.length > 0 ? fromProfiles : deriveLegacyProfiles(entries);

  if (profiles.length === 0) {
    const draft = createProfileDraft();
    return { profiles: [draft], selectedProfileId: draft.id };
  }

  const preferred = asString(entries.get("provider.selectedProfileId"));
  const selectedProfileId =
    preferred && profiles.some((item) => item.id === preferred) ? preferred : profiles[0].id;

  return { profiles, selectedProfileId };
}

function parseProfiles(raw: unknown): ProviderProfile[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => normalizeProfile(item))
    .filter((item): item is ProviderProfile => item !== null);
}

function deriveLegacyProfiles(entries: Map<string, unknown>): ProviderProfile[] {
  const provider = asString(entries.get("provider.active")) ?? "";
  const model = asString(entries.get("provider.model")) ?? "";
  const baseUrl = asString(entries.get("provider.baseUrl")) ?? "";
  const apiKey = asString(entries.get("provider.apiKey")) ?? "";

  if (!provider && !model && !baseUrl && !apiKey) return [];

  return [
    {
      id: createId(),
      name: "",
      provider,
      modelIds: model ? [model] : [],
      baseUrl,
      apiKey,
    },
  ];
}

function normalizeProfile(raw: unknown): ProviderProfile | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;

  const provider = asString(item.provider) ?? "";
  const model = asString(item.model) ?? "";
  const baseUrl = asString(item.baseUrl) ?? "";
  const apiKey = asString(item.apiKey) ?? "";
  const modelIds = parseModelIds(item.modelIds, model);

  const id = asString(item.id) ?? createId();
  const name = asString(item.name) ?? "";

  return {
    id,
    name,
    provider,
    modelIds,
    baseUrl,
    apiKey,
  };
}

function parseModelIds(raw: unknown, fallbackModel: string): string[] {
  const fromArray = Array.isArray(raw)
    ? raw
        .map((item) => (typeof item === "string" ? item.trim() : ""))
        .filter((item) => item.length > 0)
    : [];
  if (fromArray.length > 0) return uniq(fromArray);
  return fallbackModel ? [fallbackModel] : [];
}

function uniq(values: string[]): string[] {
  return Array.from(new Set(values));
}

function asString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return value.trim();
}

function createId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `provider-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
