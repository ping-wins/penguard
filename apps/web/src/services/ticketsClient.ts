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
  origin?: Record<string, any>
  attributes?: Record<string, any>
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

export type TriageEvidenceItem = {
  id: string
  type: string
  label: string
  value: string | number | string[] | Record<string, any>
  threshold?: string | number | Record<string, any> | null
  severity: string
  source: string
}

export type TriageMitreMapping = {
  tacticId: string
  tacticName: string
  techniqueId: string
  techniqueName: string
  subtechniqueId?: string | null
  subtechniqueName?: string | null
  confidence: 'low' | 'medium' | 'high'
  reason: string
  evidenceIds: string[]
}

export type TriageResponseCandidate = {
  id: string
  type: string
  label: string
  description: string
  riskLevel: 'low' | 'medium' | 'high'
  requiresApproval: boolean
  availableNow: boolean
  providerRequired?: string | null
  reason: string
  parameters: Record<string, any>
  mappedMitreTechniqueIds: string[]
  playbookTemplateIds: string[]
}

export type TriagePlaybookTemplate = {
  templateId: string
  label: string
  reason: string
  confidence: 'low' | 'medium' | 'high'
  requiredCandidateIds: string[]
  parameters: Record<string, any>
  requiresApproval: boolean
}

export type TriageContext = {
  incidentId: string
  ruleId: string | null
  alertFamily: string
  attackType: string
  severity: string
  confidence: 'low' | 'medium' | 'high'
  recommendedTriageLevel: TriageLevel
  recommendedTicketStatus: TicketStatus
  summary: string
  evidence: TriageEvidenceItem[]
  entities: Array<Record<string, any>>
  impactedAssets: Array<Record<string, any>>
  mitreMappings: TriageMitreMapping[]
  responseCandidates: TriageResponseCandidate[]
  playbookTemplates: TriagePlaybookTemplate[]
  missingData: Array<{ id: string; label: string; reason: string }>
  generatedAt: string
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

export async function resetIncidentStore(): Promise<{ eventsDeleted: number, incidentsDeleted: number }> {
  const response = await fetch('/api/soc/incidents/reset', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(await csrfHeaders()),
      ...localeHeaders(),
    },
  })
  return parseOrThrow<{ eventsDeleted: number, incidentsDeleted: number }>(
    response,
    'Failed to reset incidents',
  )
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  const response = await fetch(`/api/soc/tickets/${encodeURIComponent(ticketId)}`, {
    credentials: 'include',
  })
  return parseOrThrow<Ticket>(response, 'Failed to load ticket')
}

export async function getIncidentTriageContext(incidentId: string): Promise<TriageContext> {
  const response = await fetch(`/api/soc/incidents/${encodeURIComponent(incidentId)}/triage-context`, {
    credentials: 'include',
  })
  return parseOrThrow<TriageContext>(response, 'Failed to load triage context')
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
  provider?: string
  providerMode?: string
  rawOutput?: string
  raw_output?: string
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
  provider?: string
  providerMode?: string
  rawOutput?: string
  raw_output?: string
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
    policyReviewRequired?: boolean
  }
  ticket: Ticket | null
  ticketStatus: 'contained' | 'investigating'
}

export type ApprovePlaybookRunResponse = {
  id: string
  incidentId?: string
  playbookId?: string
  dryRun?: boolean
  status: string
  steps?: Array<{ nodeId: string; nodeType: string; status: string; sensitive: boolean }>
  policyReviewRequired?: boolean
  ticketUpdate?: {
    status: 'contained' | 'failed'
    incidentId: string
    ticket?: Ticket
    error?: string
  }
}

export type FortiGatePolicyScope = 'source_only' | 'source_destination' | 'source_destination_service'

export type FortiGatePolicyChange = {
  operation: 'create' | 'reuse'
  object_type: 'firewall.address' | 'firewall.policy'
  name: string
  payload: Record<string, unknown>
}

export type PlaybookRunPolicyReviewRequest = {
  integrationId: string
  scope: FortiGatePolicyScope
  sourceIp: string
  destinationIp?: string
  service?: string
  sourceInterface: string
  destinationInterface: string
  durationMinutes: number
}

export type PlaybookRunPolicyReviewResponse = {
  request_id: string
  status: 'pending_review'
  intent: 'temporary_block'
  scope: FortiGatePolicyScope
  integration_id: string
  existing_policy_count: number
  owned_policy_count: number
  proposed_policy_name: string
  placement: string
  warnings: string[]
  changes: FortiGatePolicyChange[]
  review_hash: string
  expires_at?: string | null
  runId: string
  incidentId: string
}

export type PlaybookRunPolicyApplyResponse = {
  runId: string
  incidentId: string
  policy: {
    request_id: string
    status: 'applied'
    applied_changes: Array<Record<string, unknown>>
  }
  ticketUpdate?: {
    status: 'contained' | 'failed'
    incidentId: string
    ticket?: Ticket
    error?: string
  } | null
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

export async function instantiateRecommendedPlaybook(
  incidentId: string,
  templateId: string,
): Promise<PlaybookDraftResponse> {
  const headers = { ...(await csrfHeaders()), ...localeHeaders() }
  const response = await fetch(
    `/api/soc/incidents/${encodeURIComponent(incidentId)}/playbook-recommendations/${encodeURIComponent(templateId)}/instantiate`,
    {
      method: 'POST',
      credentials: 'include',
      headers,
    },
  )
  return parseOrThrow<PlaybookDraftResponse>(response, 'Failed to instantiate recommended playbook')
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

export async function approvePlaybookRun(runId: string): Promise<ApprovePlaybookRunResponse> {
  const headers = await csrfHeaders()
  const response = await fetch(`/api/soc/playbook-runs/${encodeURIComponent(runId)}/approve`, {
    method: 'POST',
    credentials: 'include',
    headers,
  })
  return parseOrThrow<ApprovePlaybookRunResponse>(response, 'Failed to approve playbook run')
}

export async function createPlaybookRunPolicyReview(
  runId: string,
  payload: PlaybookRunPolicyReviewRequest,
): Promise<PlaybookRunPolicyReviewResponse> {
  const headers = await csrfHeaders()
  const response = await fetch(`/api/soc/playbook-runs/${encodeURIComponent(runId)}/policy-review`, {
    method: 'POST',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseOrThrow<PlaybookRunPolicyReviewResponse>(response, 'Failed to create FortiGate policy review')
}

export async function applyPlaybookRunPolicy(
  runId: string,
  payload: { integrationId: string, requestId: string, reviewHash: string },
): Promise<PlaybookRunPolicyApplyResponse> {
  const headers = await csrfHeaders()
  const response = await fetch(`/api/soc/playbook-runs/${encodeURIComponent(runId)}/policy-apply`, {
    method: 'POST',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseOrThrow<PlaybookRunPolicyApplyResponse>(response, 'Failed to apply FortiGate policy')
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
