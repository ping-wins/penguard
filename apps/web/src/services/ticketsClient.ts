import { useAuthStore } from '../stores/useAuthStore'

export type TriageLevel = 'T1' | 'T2' | 'T3'
export type TicketStatus = 'new' | 'investigating' | 'contained' | 'closed'

export type TicketTimelineItem = {
  id: string
  type: string
  status?: string | null
  message: string
  occurredAt: string
}

export type Ticket = {
  id: string
  ruleId: string | null
  title: string
  severity: string
  status: string
  source: 'kowalski'
  entities: Record<string, any>
  summary: string
  createdAt: string
  timeline: TicketTimelineItem[]
  eventIds: string[]
  triageLevel: TriageLevel
  ticketStatus: TicketStatus
  assigneeUserId: string | null
  aiAnalysisId: string | null
}

type TicketsResponse = { items: Ticket[] }

async function csrfHeaders(): Promise<Record<string, string>> {
  const auth = useAuthStore()
  if (!auth.csrfToken) await auth.fetchCsrf()
  return { 'X-CSRF-Token': auth.csrfToken }
}

async function parseOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  const data = await response.json().catch(() => ({}))
  const message = typeof (data as any)?.detail === 'string' ? (data as any).detail : fallback
  throw new Error(message)
}

export async function listTickets(filters: {
  triage?: TriageLevel
  status?: TicketStatus
  severity?: string
} = {}): Promise<Ticket[]> {
  const params = new URLSearchParams()
  if (filters.triage) params.set('triage', filters.triage)
  if (filters.status) params.set('status', filters.status)
  if (filters.severity) params.set('severity', filters.severity)
  const qs = params.toString()
  const url = `/api/soc/tickets${qs ? `?${qs}` : ''}`
  const data = await parseOrThrow<TicketsResponse>(
    await fetch(url, { credentials: 'include' }),
    'Failed to load tickets',
  )
  return data.items ?? []
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  const response = await fetch(`/api/soc/tickets/${encodeURIComponent(ticketId)}`, {
    credentials: 'include',
  })
  return parseOrThrow<Ticket>(response, 'Failed to load ticket')
}

export type IncidentAnalysis = {
  id: string
  incidentId: string
  headline: string
  summary: string
  riskScore: number
  suggestedTriage: TriageLevel
  suggestedTicketStatus: TicketStatus
  indicatorsOfCompromise: string[]
  nextSteps: string[]
  references: string[]
}

export type ContainmentStep = {
  title: string
  description: string
  playbookNodeType: string
  severity: 'low' | 'medium' | 'high'
  requiresApproval: boolean
}

export type ContainmentSuggestion = {
  incidentId: string
  summary: string
  steps: ContainmentStep[]
  playbookDraftId: string | null
}

export async function analyzeIncident(incidentId: string): Promise<IncidentAnalysis> {
  const headers = await csrfHeaders()
  const response = await fetch(`/api/soc/incidents/${encodeURIComponent(incidentId)}/analyze`, {
    method: 'POST',
    credentials: 'include',
    headers,
  })
  return parseOrThrow<IncidentAnalysis>(response, 'Failed to analyze incident')
}

export async function suggestContainment(incidentId: string): Promise<ContainmentSuggestion> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/soc/incidents/${encodeURIComponent(incidentId)}/containment-suggestions`,
    {
      method: 'POST',
      credentials: 'include',
      headers,
    },
  )
  return parseOrThrow<ContainmentSuggestion>(response, 'Failed to fetch containment suggestions')
}

export async function updateTicket(
  ticketId: string,
  patch: {
    triageLevel?: TriageLevel
    ticketStatus?: TicketStatus
    assigneeUserId?: string
    aiAnalysisId?: string
    note?: string
  },
): Promise<Ticket> {
  const headers = await csrfHeaders()
  const response = await fetch(`/api/soc/tickets/${encodeURIComponent(ticketId)}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return parseOrThrow<Ticket>(response, 'Failed to update ticket')
}
