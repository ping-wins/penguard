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

type EndpointsResponse = { items: Endpoint[] }
type EndpointTimelineResponse = { endpointId: string; items: EndpointTimelineItem[] }
type Fetcher = typeof fetch

async function parseOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  const data = await response.json().catch(() => ({}))
  const message = typeof (data as any)?.detail === 'string' ? (data as any).detail : fallback
  throw new Error(message)
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
