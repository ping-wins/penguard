import { useAuthStore } from '../stores/useAuthStore'

export type AiPreferenceMode = 'api' | 'cli'

export type AiPreferenceResponse = {
  mode: AiPreferenceMode
  provider: string
  model: string
  apiKeySet: boolean
  cliBinary: string
  updatedAt: string | null
}

export type AiPreferenceUpdate = {
  mode?: AiPreferenceMode
  provider?: string
  model?: string
  apiKey?: string
  cliBinary?: string
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

export async function getAiPreferences(): Promise<AiPreferenceResponse> {
  const response = await fetch('/api/ai/preferences', { credentials: 'include' })
  return parseOrThrow<AiPreferenceResponse>(response, 'Falha ao carregar preferências de IA')
}

export async function updateAiPreferences(
  update: AiPreferenceUpdate,
): Promise<AiPreferenceResponse> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/preferences', {
    method: 'PUT',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  })
  return parseOrThrow<AiPreferenceResponse>(response, 'Falha ao salvar preferências de IA')
}
