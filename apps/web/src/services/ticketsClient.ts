import { useAuthStore } from '../stores/useAuthStore'
import { getLocale } from '../i18n'

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

function localeHeaders(): Record<string, string> {
  return { 'X-FortiDashboard-Locale': getLocale() }
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

export type MitreTechnique = {
  id: string
  name: string
  url: string
}

export type CvssAnalysis = {
  score: number | null
  severity: '' | 'None' | 'Low' | 'Medium' | 'High' | 'Critical'
  vector: string
  justification: string
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
  cvss?: CvssAnalysis
  mitreTechniques?: MitreTechnique[]
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
  const headers = { ...(await csrfHeaders()), ...localeHeaders() }
  const response = await fetch(`/api/soc/incidents/${encodeURIComponent(incidentId)}/analyze`, {
    method: 'POST',
    credentials: 'include',
    headers,
  })
  return parseOrThrow<IncidentAnalysis>(response, 'Failed to analyze incident')
}

export type PlaybookSimulationStep = {
  nodeId: string
  nodeType: string
  status: string
  sensitive: boolean
}

export type PlaybookSimulation = {
  dryRun: boolean
  valid: boolean
  steps: PlaybookSimulationStep[]
  error?: string
}

export type PlaybookDraft = {
  id: string
  name: string
  enabled: boolean
  nodes: Array<{ id: string; type: string; config?: Record<string, any> }>
  edges: Array<{ from: string; to: string }>
}

export type PlaybookDraftResponse = {
  ticketId: string
  playbook: PlaybookDraft
  simulation: PlaybookSimulation
  suggestion: ContainmentSuggestion
}

export type ApplyContainmentResponse = {
  ticketId: string
  playbookId: string
  run: {
    id: string
    incidentId: string
    playbookId: string
    dryRun: boolean
    status: string
    steps: Array<{ nodeId: string; nodeType: string; status: string; sensitive: boolean }>
    createdAt: string
  }
  ticket: Ticket | null
  ticketStatus: 'contained' | 'investigating'
}

export async function draftContainmentPlaybook(ticketId: string): Promise<PlaybookDraftResponse> {
  const headers = { ...(await csrfHeaders()), ...localeHeaders() }
  const response = await fetch(
    `/api/soc/tickets/${encodeURIComponent(ticketId)}/draft-playbook`,
    {
      method: 'POST',
      credentials: 'include',
      headers,
    },
  )
  return parseOrThrow<PlaybookDraftResponse>(response, 'Failed to draft containment playbook')
}

export async function applyContainmentPlaybook(
  ticketId: string,
  playbookId: string,
): Promise<ApplyContainmentResponse> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/soc/tickets/${encodeURIComponent(ticketId)}/apply-containment`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ playbookId }),
    },
  )
  return parseOrThrow<ApplyContainmentResponse>(response, 'Failed to apply containment playbook')
}

export async function suggestContainment(incidentId: string): Promise<ContainmentSuggestion> {
  const headers = { ...(await csrfHeaders()), ...localeHeaders() }
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
