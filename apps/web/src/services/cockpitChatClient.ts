import { useAuthStore } from '../stores/useAuthStore'

export type ChatTurn = { role: 'user' | 'assistant'; content: string }

export type WidgetFieldBinding = {
  fieldId: string
  label: string
  type: string
  unit?: string | null
  source?: string | null
  provider: string
  integrationId?: string | null
}

export type WidgetDraft = {
  provider: string
  integrationId?: string | null
  visualType: string
  title: string
  fieldBindings: WidgetFieldBinding[]
  layout: { w: number; h: number }
  settings: Record<string, unknown>
}

export type WidgetDraftResponse = {
  toolName: string
  status: string
  requiresConfirmation: boolean
  draft: WidgetDraft
  preview: { source: string; values: Record<string, unknown> }
  validation: { valid: boolean; warnings: string[]; errors: string[] }
}

export type ChatResponse = {
  reply: string
  provider: string
  model: string
  runtime: string
  widgetDrafts: WidgetDraftResponse[]
}

export async function sendCockpitChat(
  messages: ChatTurn[],
  locale = 'pt-BR',
): Promise<ChatResponse> {
  const auth = useAuthStore()
  if (!auth.csrfToken) await auth.fetchCsrf()
  const response = await fetch('/api/ai/chat', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': auth.csrfToken,
      'X-Penguard-Locale': locale,
    },
    body: JSON.stringify({ messages }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error((data as any)?.detail ?? 'Falha no chat')
  }
  return response.json()
}
