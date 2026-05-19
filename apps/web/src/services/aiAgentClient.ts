import { useAuthStore } from '../stores/useAuthStore'
import { i18n } from '../i18n'

export type AgentTool = {
  name: string
  description: string
  inputSchema: Record<string, unknown>
  category: string
  requiresApproval: boolean
  requiredPermissions: string[]
  timeoutSeconds: number
}

export type AgentSessionResponse = {
  sessionId: string
  backend: string
  model: string
  role: string
  locale: string
  createdAt: number
  tokensIn: number
  tokensOut: number
}

export type AgentStreamEvent =
  | { type: 'connected'; sessionId: string }
  | {
      type: 'step'
      kind: 'text_delta'
      step: number
      text: string
    }
  | {
      type: 'step'
      kind: 'tool_call'
      step: number
      call_id: string
      tool_name: string
      args: Record<string, unknown>
    }
  | {
      type: 'step'
      kind: 'tool_result'
      step: number
      call_id: string
      tool_name: string
      status: 'ok' | 'error' | 'denied'
      result: unknown
      error: string | null
      latency_ms: number
    }
  | {
      type: 'step'
      kind: 'awaiting_approval'
      step: number
      call_id: string
      tool_name: string
      args: Record<string, unknown>
      reason: string
    }
  | {
      type: 'step'
      kind: 'done'
      step: number
      reply: string
      used_tools: string[]
      tokens_in: number
      tokens_out: number
    }
  | {
      type: 'step'
      kind: 'error'
      step: number
      message: string
      code: string
    }

async function csrfHeaders(): Promise<Record<string, string>> {
  const auth = useAuthStore()
  if (!auth.csrfToken) await auth.fetchCsrf()
  return { 'X-CSRF-Token': auth.csrfToken }
}

async function parseOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  const data = await response.json().catch(() => ({}))
  const detail = (data as any)?.detail
  const message =
    typeof detail === 'string'
      ? localizeAgentError(detail)
      : fallback
  throw new Error(message)
}

function localizeAgentError(message: string): string {
  if (message === 'SOC Assistant provider is not configured') {
    return i18n.global.t('aiAgent.errorNotConfigured')
  }
  return message
}

export async function listAgentTools(): Promise<AgentTool[]> {
  const response = await fetch('/api/ai/agent/tools', { credentials: 'include' })
  const payload = await parseOrThrow<{ items: AgentTool[] }>(
    response,
    i18n.global.t('aiAgent.errorListTools'),
  )
  return payload.items
}

export async function createAgentSession(
  options: { locale?: string } = {},
): Promise<AgentSessionResponse> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/agent/sessions', {
    method: 'POST',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      locale: options.locale ?? 'pt-BR',
    }),
  })
  return parseOrThrow<AgentSessionResponse>(
    response,
    i18n.global.t('aiAgent.errorCreateSession'),
  )
}

export async function approveAgentToolCall(
  sessionId: string,
  callId: string,
  granted: boolean,
  reason = '',
): Promise<void> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/ai/agent/sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(callId)}`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ granted, reason }),
    },
  )
  await parseOrThrow(response, i18n.global.t('aiAgent.errorApprove'))
}

export async function deleteAgentSession(sessionId: string): Promise<void> {
  const headers = await csrfHeaders()
  await fetch(`/api/ai/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    credentials: 'include',
    headers,
  })
}

export async function* streamAgentMessage(
  sessionId: string,
  content: string,
  options: { workspaceId?: string } = {},
  signal?: AbortSignal,
): AsyncGenerator<AgentStreamEvent, void, void> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/ai/agent/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content,
        ...(options.workspaceId ? { workspaceId: options.workspaceId } : {}),
      }),
      signal,
    },
  )

  if (!response.ok || response.body === null) {
    const data = await response.json().catch(() => ({}))
    const message =
      typeof (data as any)?.detail === 'string'
        ? localizeAgentError((data as any).detail)
        : i18n.global.t('aiAgent.errorStream', { status: response.status })
    throw new Error(message)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      while (true) {
        const idx = buffer.indexOf('\n\n')
        if (idx === -1) break
        const chunk = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const dataLine = chunk
          .split('\n')
          .find((line) => line.startsWith('data: '))
        if (!dataLine) continue
        try {
          yield JSON.parse(dataLine.slice('data: '.length)) as AgentStreamEvent
        } catch {
          // ignore malformed payloads
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
