export type EndpointHealth = 'unknown' | 'healthy' | 'warning' | 'critical' | 'offline'

export type Endpoint = {
  id: string
  hostname: string | null
  ipAddresses: string[]
  currentUser: string | null
  lastSeenAt: string | null
  health: EndpointHealth
  attributes: Record<string, any>
}

export type EndpointTimelineItem = {
  id: string
  endpointId: string
  eventType: string
  occurredAt: string
  title: string
  hostname: string | null
  ipAddresses: string[]
  currentUser: string | null
  health: EndpointHealth | null
  attributes: Record<string, any>
}

export type EndpointRelatedIncident = {
  id: string
  title: string
  severity: string
  triageLevel?: string | null
  ticketStatus?: string | null
  source?: string | null
  origin?: Record<string, any>
  entities?: Record<string, any>
  attributes?: Record<string, any>
}

export type EndpointRelatedIncidentsResponse = {
  endpointId: string
  items: EndpointRelatedIncident[]
  total: number
  matchedFields?: Record<string, string[]>
}

export type EndpointEnrollmentRequest = {
  displayName?: string
  hostnameHint?: string
}

export type EndpointEnrollment = {
  id: string
  displayName: string | null
  hostnameHint: string | null
  createdAt: string
  token: string
}

type EndpointsResponse = { items: Endpoint[] }
type EndpointTimelineResponse = { endpointId: string; items: EndpointTimelineItem[] }
type Fetcher = typeof fetch

async function parseOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  const data = await response.json().catch(() => ({}))
  const message = typeof (data as any)?.detail === 'string' ? (data as any).detail : fallback
  throw new Error(message)
}

async function getCsrfToken(fetcher: Fetcher): Promise<string> {
  const data = await parseOrThrow<{ csrfToken?: string }>(
    await fetcher('/api/auth/csrf', { credentials: 'include' }),
    'Failed to load CSRF token',
  )
  if (!data.csrfToken) throw new Error('Failed to load CSRF token')
  return data.csrfToken
}

function quotePowerShellValue(value: string): string {
  return `"${value.replace(/`/g, '``').replace(/"/g, '`"')}"`
}

export async function listEndpoints(fetcher: Fetcher = fetch): Promise<Endpoint[]> {
  const data = await parseOrThrow<EndpointsResponse>(
    await fetcher('/api/weapons/endpoints', { credentials: 'include' }),
    'Failed to load endpoints',
  )
  return data.items ?? []
}

export async function getEndpoint(endpointId: string, fetcher: Fetcher = fetch): Promise<Endpoint> {
  return parseOrThrow<Endpoint>(
    await fetcher(`/api/weapons/endpoints/${encodeURIComponent(endpointId)}`, {
      credentials: 'include',
    }),
    'Failed to load endpoint',
  )
}

export async function getEndpointTimeline(
  endpointId: string,
  fetcher: Fetcher = fetch,
): Promise<EndpointTimelineItem[]> {
  const data = await parseOrThrow<EndpointTimelineResponse>(
    await fetcher(`/api/weapons/endpoints/${encodeURIComponent(endpointId)}/timeline`, {
      credentials: 'include',
    }),
    'Failed to load endpoint timeline',
  )
  return data.items ?? []
}

export async function getEndpointRelatedIncidents(
  endpointId: string,
  fetcher: Fetcher = fetch,
): Promise<EndpointRelatedIncidentsResponse> {
  const data = await parseOrThrow<EndpointRelatedIncidentsResponse>(
    await fetcher(`/api/weapons/endpoints/${encodeURIComponent(endpointId)}/related-incidents`, {
      credentials: 'include',
    }),
    'Failed to load related incidents',
  )
  return {
    endpointId: data.endpointId,
    items: data.items ?? [],
    total: data.total ?? 0,
    matchedFields: data.matchedFields,
  }
}

export async function createEndpointEnrollment(
  payload: EndpointEnrollmentRequest,
  fetcher: Fetcher = fetch,
): Promise<EndpointEnrollment> {
  const csrfToken = await getCsrfToken(fetcher)
  return parseOrThrow<EndpointEnrollment>(
    await fetcher('/api/weapons/enrollments', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
      },
      body: JSON.stringify(payload),
    }),
    'Failed to create endpoint enrollment',
  )
}

export function buildAgentRunCommand(enrollment: EndpointEnrollment, apiUrl?: string): string {
  const resolvedApiUrl = apiUrl ?? (typeof window !== 'undefined' ? window.location.origin : '')
  return [
    'cd apps\\agent_private',
    `$env:AGENT_PRIVATE_API_URL=${quotePowerShellValue(resolvedApiUrl)}`,
    `$env:AGENT_PRIVATE_ENDPOINT_ID=${quotePowerShellValue(enrollment.id)}`,
    `$env:AGENT_PRIVATE_ENROLLMENT_TOKEN=${quotePowerShellValue(enrollment.token)}`,
    'uv run agent-private run',
  ].join('; ')
}
