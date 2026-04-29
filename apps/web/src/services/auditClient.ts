export type AuditActor = {
  id: string | null
  email: string | null
}

export type AuditEvent = {
  id: string
  actor: AuditActor
  action: string
  outcome: string
  ipAddress: string | null
  userAgent: string | null
  details: Record<string, unknown>
  createdAt: string | null
}

export type AuditEventsResponse = {
  items: AuditEvent[]
}

type Fetcher = typeof fetch

export class AuditApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'AuditApiError'
    this.status = status
  }
}

async function parseJson(response: Response) {
  return response.json().catch(() => ({}))
}

async function errorFromResponse(response: Response) {
  const body = await parseJson(response)
  if (typeof body.detail === 'string') {
    return new AuditApiError(body.detail, response.status)
  }
  return new AuditApiError('Unable to load audit trail', response.status)
}

function auditEventsUrl(limit: number) {
  const boundedLimit = Math.min(100, Math.max(1, Math.trunc(limit)))
  return `/api/audit/events?limit=${boundedLimit}`
}

export async function fetchAuditEvents({
  limit = 50,
  fetcher = globalThis.fetch.bind(globalThis),
}: {
  limit?: number
  fetcher?: Fetcher
} = {}): Promise<AuditEventsResponse> {
  const response = await fetcher(auditEventsUrl(limit), { credentials: 'include' })
  if (!response.ok) {
    throw await errorFromResponse(response)
  }

  const payload = await parseJson(response)
  return {
    items: Array.isArray(payload.items) ? payload.items : [],
  }
}
