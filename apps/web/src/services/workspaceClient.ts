import { useAuthStore } from '../stores/useAuthStore'

export type ManifestWidgetLayout = {
  x: number
  y: number
  w: number
  h: number
  z: number
}

export type ManifestFieldBinding = {
  fieldId: string
  label: string
  type: string
  unit?: string | null
  source: string
  provider?: string | null
  groupId?: string | null
  groupName?: string | null
}

export type ManifestWidget = {
  instanceId: string
  catalogId: string
  providerType: string
  layout: ManifestWidgetLayout
  fieldBindings: ManifestFieldBinding[]
  titleOverride?: string | null
  notes?: string | null
}

export type PresentationSlide = {
  widgetInstanceId: string
  title: string
  narration?: string | null
  highlightFieldIds: string[]
}

export type PresentationMetadata = {
  title: string
  incidentSummary?: string | null
  presenterName?: string | null
  audience?: string | null
  severity?: string | null
  slides: PresentationSlide[]
}

export type WorkspaceManifest = {
  schemaVersion: number
  workspaceId: string
  name: string
  widgets: ManifestWidget[]
  providerTypes: string[]
  presentation: PresentationMetadata | null
  metadata: {
    description?: string | null
    tags: string[]
    incidentId?: string | null
    exportedAt: string
    exportedByEmail?: string | null
  }
}

export type TemplateCategory =
  | 'executive'
  | 'analyst'
  | 'engineer'
  | 'incident_response'
  | 'community'

export type CommunityTemplate = {
  id: string
  slug: string
  title: string
  description: string | null
  tags: string[]
  publishedByEmail: string | null
  publishedByUserId: string
  installCount: number
  category: TemplateCategory
  isCurated: boolean
  icon: string | null
  createdAt: string
  updatedAt: string
  manifest?: WorkspaceManifest
}

export type WorkspaceOrigin = {
  type: 'local' | 'imported' | 'template'
  templateId?: string
  templateSlug?: string
  templateTitle?: string
  templateDescription?: string | null
  tags?: string[]
  publishedByEmail?: string | null
  publishedByUserId?: string
  installCount?: number
  installedAt?: string
  exportedByEmail?: string | null
  exportedAt?: string
  description?: string | null
  incidentId?: string | null
  sourceWorkspaceId?: string
  importedAt?: string
  missingProviderTypes?: string[]
}

export type WorkspacePayload = {
  id: string
  name: string
  widgets: any[]
  presentation: PresentationMetadata | null
  origin: WorkspaceOrigin | null
  version: number
  updatedAt?: string
}

export type WorkspaceSummary = {
  id: string
  name: string
  widgetCount: number
  version: number
  origin: WorkspaceOrigin | null
  hasPresentation: boolean
  createdAt: string
  updatedAt: string
}

async function csrfHeaders(): Promise<Record<string, string>> {
  const authStore = useAuthStore()
  if (!authStore.csrfToken) {
    await authStore.fetchCsrf()
  }
  return { 'X-CSRF-Token': authStore.csrfToken }
}

async function parseOrThrow(response: Response, fallback: string) {
  if (response.ok) {
    return response.json()
  }
  const data = await response.json().catch(() => ({}))
  const message = typeof data?.detail === 'string' ? data.detail : fallback
  throw new Error(message)
}

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
  const response = await fetch('/api/workspaces', { credentials: 'include' })
  const data = await parseOrThrow(response, 'Failed to list workspaces')
  return data.items ?? []
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  const headers = await csrfHeaders()
  const response = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE',
    credentials: 'include',
    headers,
  })
  await parseOrThrow(response, 'Failed to delete workspace')
}

export async function rebindWidgetIntegration(
  workspaceId: string,
  instanceId: string,
  integrationId: string,
): Promise<WorkspacePayload> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/widgets/${encodeURIComponent(instanceId)}/integration`,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ integrationId }),
    },
  )
  return parseOrThrow(response, 'Failed to rebind widget integration')
}

export async function exportWorkspace(workspaceId: string): Promise<WorkspaceManifest> {
  const response = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/export`, {
    credentials: 'include',
  })
  return parseOrThrow(response, 'Failed to export workspace')
}

export async function importWorkspace(
  manifest: WorkspaceManifest,
  workspaceId?: string,
): Promise<WorkspacePayload> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/workspaces/import', {
    method: 'POST',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ manifest, workspaceId }),
  })
  return parseOrThrow(response, 'Failed to import workspace')
}

export async function updatePresentation(
  workspaceId: string,
  presentation: PresentationMetadata | null,
): Promise<WorkspacePayload> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/presentation`,
    {
      method: 'PUT',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ presentation }),
    },
  )
  return parseOrThrow(response, 'Failed to save presentation')
}

export async function publishWorkspaceTemplate(payload: {
  workspaceId: string
  slug: string
  title: string
  description?: string
  tags?: string[]
  presentation?: PresentationMetadata | null
  incidentId?: string
}): Promise<CommunityTemplate> {
  const headers = await csrfHeaders()
  const body = {
    slug: payload.slug,
    title: payload.title,
    description: payload.description ?? null,
    tags: payload.tags ?? [],
    presentation: payload.presentation ?? null,
    incidentId: payload.incidentId ?? null,
  }
  const response = await fetch(
    `/api/workspaces/${encodeURIComponent(payload.workspaceId)}/publish`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
  return parseOrThrow(response, 'Failed to publish workspace template')
}

export async function listCommunityTemplates(): Promise<CommunityTemplate[]> {
  const response = await fetch('/api/workspaces/community', { credentials: 'include' })
  const data = await parseOrThrow(response, 'Failed to load community library')
  return data.items ?? []
}

export async function listWorkspaceTemplates(options: {
  category?: TemplateCategory | 'all'
  search?: string
} = {}): Promise<CommunityTemplate[]> {
  const params = new URLSearchParams()
  if (options.category && options.category !== 'all') {
    params.set('category', options.category)
  }
  if (options.search) params.set('search', options.search)
  const query = params.toString()
  const url = query
    ? `/api/workspaces/templates?${query}`
    : '/api/workspaces/templates'
  const response = await fetch(url, { credentials: 'include' })
  const data = await parseOrThrow(response, 'Failed to load workspace templates')
  return data.items ?? []
}

export async function installCommunityTemplate(
  templateId: string,
  workspaceId?: string,
): Promise<{ workspace: WorkspacePayload; templateId: string }> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/workspaces/community/${encodeURIComponent(templateId)}/install`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspaceId }),
    },
  )
  return parseOrThrow(response, 'Failed to install template')
}

export async function deleteCommunityTemplate(templateId: string): Promise<void> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/workspaces/community/${encodeURIComponent(templateId)}`,
    {
      method: 'DELETE',
      credentials: 'include',
      headers,
    },
  )
  await parseOrThrow(response, 'Failed to delete template')
}

export function manifestToDownloadBlob(manifest: WorkspaceManifest): Blob {
  return new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' })
}

export function downloadManifest(manifest: WorkspaceManifest, filename?: string) {
  const blob = manifestToDownloadBlob(manifest)
  const url = URL.createObjectURL(blob)
  const safeName = (filename || manifest.name || 'workspace').replace(/[^a-z0-9-_]+/gi, '-').toLowerCase()
  const link = document.createElement('a')
  link.href = url
  link.download = `${safeName}-manifest.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function readManifestFile(file: File): Promise<WorkspaceManifest> {
  const text = await file.text()
  const parsed = JSON.parse(text)
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('Manifest file must be a JSON object')
  }
  return parsed as WorkspaceManifest
}
