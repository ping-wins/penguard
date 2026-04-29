export type ProviderDataField = {
  id: string
  label: string
  type: string
  unit?: string
  source: string
  recommendedVisuals?: string[]
}

export type ProviderDataGroup = {
  id: string
  name: string
  fields: ProviderDataField[]
}

export type ProviderDataFieldsResponse = {
  provider: string
  groups: ProviderDataGroup[]
}

type Fetcher = typeof fetch

export class ProviderDataApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ProviderDataApiError'
    this.status = status
  }
}

async function parseJson(response: Response) {
  return response.json().catch(() => ({}))
}

async function errorFromResponse(response: Response) {
  const body = await parseJson(response)
  if (typeof body.detail === 'string') {
    return new ProviderDataApiError(body.detail, response.status)
  }
  return new ProviderDataApiError('Unable to load provider data fields', response.status)
}

function normalizeGroups(groups: unknown): ProviderDataGroup[] {
  if (!Array.isArray(groups)) return []
  return groups
    .filter((group): group is Record<string, unknown> => Boolean(group) && typeof group === 'object')
    .map((group) => ({
      id: String(group.id ?? ''),
      name: String(group.name ?? group.id ?? 'Data group'),
      fields: normalizeFields(group.fields),
    }))
    .filter(group => group.id.length > 0)
}

function normalizeFields(fields: unknown): ProviderDataField[] {
  if (!Array.isArray(fields)) return []
  return fields
    .filter((field): field is Record<string, unknown> => Boolean(field) && typeof field === 'object')
    .map((field) => ({
      id: String(field.id ?? ''),
      label: String(field.label ?? field.id ?? 'Field'),
      type: String(field.type ?? 'unknown'),
      unit: typeof field.unit === 'string' ? field.unit : undefined,
      source: String(field.source ?? ''),
      recommendedVisuals: Array.isArray(field.recommendedVisuals)
        ? field.recommendedVisuals.filter((item): item is string => typeof item === 'string')
        : [],
    }))
    .filter(field => field.id.length > 0)
}

export async function fetchFortigateDataFields({
  fetcher = globalThis.fetch.bind(globalThis),
}: {
  fetcher?: Fetcher
} = {}): Promise<ProviderDataFieldsResponse> {
  const response = await fetcher('/api/providers/fortigate/data-fields', {
    credentials: 'include',
  })
  if (!response.ok) {
    throw await errorFromResponse(response)
  }

  const payload = await parseJson(response)
  return {
    provider: String(payload.provider ?? 'fortigate'),
    groups: normalizeGroups(payload.groups),
  }
}
