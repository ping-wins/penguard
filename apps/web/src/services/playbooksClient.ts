import { useAuthStore } from '../stores/useAuthStore'

export type PlaybookNode = {
  id: string
  type: string
  config?: Record<string, any>
  sensitive?: boolean
}

export type PlaybookNodeType = {
  id: string
  label: string
  category: 'trigger' | 'condition' | 'enrichment' | 'action' | 'control' | string
  sensitive: boolean
  dryRunOnly: boolean
  executionMode: 'dry_run' | 'live' | string
  liveAvailable: boolean
  boundary: string
  configSchema: Record<string, any>
}

export type PlaybookEdge = {
  from: string
  to: string
}

export type Playbook = {
  id: string
  name: string
  description?: string | null
  enabled: boolean
  nodes: PlaybookNode[]
  edges: PlaybookEdge[]
}

export type PlaybookDraft = Pick<Playbook, 'id' | 'name' | 'enabled' | 'nodes' | 'edges'>

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
  error?: string | null
}

export type PlaybookRun = {
  id: string
  incidentId?: string
  playbookId?: string
  dryRun?: boolean
  status: string
  steps: PlaybookSimulationStep[]
  ticketUpdate?: {
    status?: string
    incidentId?: string
    [key: string]: any
  }
}

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

type PlaybookListResponse = Playbook[] | { items?: Playbook[] }
type PlaybookNodeTypesResponse = { items?: PlaybookNodeType[] }

export async function listPlaybookNodeTypes(): Promise<PlaybookNodeType[]> {
  const data = await parseOrThrow<PlaybookNodeTypesResponse>(
    await fetch('/api/soc/playbook-node-types', { credentials: 'include' }),
    'Failed to load playbook node types',
  )
  return Array.isArray(data.items) ? data.items : []
}

export async function listPlaybooks(): Promise<Playbook[]> {
  const data = await parseOrThrow<PlaybookListResponse>(
    await fetch('/api/soc/playbooks', { credentials: 'include' }),
    'Failed to load playbooks',
  )
  if (Array.isArray(data)) return data
  if (Array.isArray(data.items)) return data.items
  return []
}

export async function createPlaybook(payload: PlaybookDraft): Promise<Playbook> {
  return parseOrThrow<Playbook>(
    await fetch('/api/soc/playbooks', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(await csrfHeaders()),
      },
      body: JSON.stringify(payload),
    }),
    'Failed to create playbook',
  )
}

export async function simulatePlaybook(playbookId: string): Promise<PlaybookSimulation> {
  return parseOrThrow<PlaybookSimulation>(
    await fetch(`/api/soc/playbooks/${encodeURIComponent(playbookId)}/simulate`, {
      method: 'POST',
      credentials: 'include',
      headers: await csrfHeaders(),
    }),
    'Failed to simulate playbook',
  )
}

export async function runPlaybook(incidentId: string, playbookId: string): Promise<PlaybookRun> {
  return parseOrThrow<PlaybookRun>(
    await fetch(`/api/soc/incidents/${encodeURIComponent(incidentId)}/playbooks/${encodeURIComponent(playbookId)}/run`, {
      method: 'POST',
      credentials: 'include',
      headers: await csrfHeaders(),
    }),
    'Failed to run playbook',
  )
}

export async function getPlaybookRun(runId: string): Promise<PlaybookRun> {
  return parseOrThrow<PlaybookRun>(
    await fetch(`/api/soc/playbook-runs/${encodeURIComponent(runId)}`, { credentials: 'include' }),
    'Failed to load playbook run',
  )
}

export async function approvePlaybookRun(runId: string): Promise<PlaybookRun> {
  return parseOrThrow<PlaybookRun>(
    await fetch(`/api/soc/playbook-runs/${encodeURIComponent(runId)}/approve`, {
      method: 'POST',
      credentials: 'include',
      headers: await csrfHeaders(),
    }),
    'Failed to approve playbook run',
  )
}
