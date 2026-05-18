import { useAuthStore } from '../stores/useAuthStore'

export type SocAssistantSettings = {
  provider: string
  model: string
  apiKeySet: boolean
  configured: boolean
  lastTestedAt: string | null
  lastTestStatus: string | null
  lastTestError: string | null
  updatedBy: string | null
  updatedAt: string | null
}

export type SocAssistantSettingsUpdate = {
  provider?: string
  model?: string
  apiKey?: string
}

export type SocAssistantSettingsTestResult = {
  ok: boolean
  status: string
  error: string | null
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

export async function getSocAssistantSettings(): Promise<SocAssistantSettings> {
  const response = await fetch('/api/ai/agent/settings', { credentials: 'include' })
  return parseOrThrow<SocAssistantSettings>(
    response,
    'Failed to load SOC Assistant settings',
  )
}

export async function saveSocAssistantSettings(
  update: SocAssistantSettingsUpdate,
): Promise<SocAssistantSettings> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/agent/settings', {
    method: 'PUT',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  })
  return parseOrThrow<SocAssistantSettings>(
    response,
    'Failed to save SOC Assistant settings',
  )
}

export async function testSocAssistantSettings(): Promise<SocAssistantSettingsTestResult> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/agent/settings/test', {
    method: 'POST',
    credentials: 'include',
    headers,
  })
  return parseOrThrow<SocAssistantSettingsTestResult>(
    response,
    'Failed to test SOC Assistant settings',
  )
}
