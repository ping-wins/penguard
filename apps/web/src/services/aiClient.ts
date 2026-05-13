import { useAuthStore } from '../stores/useAuthStore'
import { getLocale } from '../i18n'

export type ChatRole = 'user' | 'assistant' | 'system'

export type ChatTurn = {
  role: ChatRole
  content: string
}

export type ChatReply = {
  reply: string
  provider: string
  model: string
  runtime: string
}

export type AIStatus = {
  provider: string
  model: string
  ready: boolean
  runtime: string
}

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

export async function aiChat(messages: ChatTurn[]): Promise<ChatReply> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/chat', {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...headers,
      ...localeHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ messages }),
  })
  return parseOrThrow<ChatReply>(response, 'Falha ao falar com o assistente IA')
}

export async function aiStatus(): Promise<AIStatus> {
  const response = await fetch('/api/ai/status', {
    credentials: 'include',
  })
  return parseOrThrow<AIStatus>(response, 'Falha ao consultar status do provider IA')
}
