type QueryPrimitive = string | number | boolean | null
type QueryParams = Record<string, QueryPrimitive | undefined>

function normalizeValue(value: QueryParams[string]): QueryPrimitive {
  if (value === undefined || value === '') return null
  return value
}

export function normalizeQueryParams<T extends QueryParams>(params: T = {} as T): Record<string, QueryPrimitive> {
  return Object.fromEntries(
    Object.entries(params)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, value]) => [key, normalizeValue(value)]),
  )
}

export type WidgetDataQueryParams = {
  integrationId?: string | null
  source?: string | null
  window?: string | null
  limit?: string | number | null
  dataEndpoint?: string | null
}

export type SocTicketsQueryFilters = {
  triage?: string | null
  status?: string | null
  severity?: string | null
}

export type SocIncidentsQueryFilters = {
  status?: string | null
  severity?: string | null
}

export type SocEventsQueryFilters = {
  eventType?: string | null
  limit?: string | number | null
}

export const widgetDataKey = (widgetId: string, params: WidgetDataQueryParams = {}) => [
  'widgets',
  'data',
  widgetId,
  normalizeQueryParams(params),
] as const

export const socTicketsKey = (filters: SocTicketsQueryFilters = {}) => [
  'soc',
  'tickets',
  normalizeQueryParams(filters),
] as const

export const socIncidentsKey = (filters: SocIncidentsQueryFilters = {}) => [
  'soc',
  'incidents',
  normalizeQueryParams(filters),
] as const

export const socEventsKey = (filters: SocEventsQueryFilters = {}) => [
  'soc',
  'events',
  normalizeQueryParams(filters),
] as const
