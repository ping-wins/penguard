import { useAuthStore } from '../stores/useAuthStore'

export type AgentBackend = {
  name: string
  ready: boolean
  default: boolean
}

export type AgentTool = {
  name: string
  description: string
  inputSchema: Record<string, unknown>
  category: string
  requiresApproval: boolean
  timeoutSeconds: number
}

export type AgentSessionResponse = {
  sessionId: string
  backend: string
  model: string
  locale: string
  createdAt: number
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
      status: 'ok' | 'error'
      result: unknown
      error: string | null
      latency_ms: number
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
  const message = typeof (data as any)?.detail === 'string' ? (data as any).detail : fallback
  throw new Error(message)
}

export async function listBackends(): Promise<AgentBackend[]> {
  const response = await fetch('/api/ai/agent/backends', { credentials: 'include' })
  const payload = await parseOrThrow<{ items: AgentBackend[] }>(response, 'Falha ao listar backends')
  return payload.items
}

export async function listAgentTools(): Promise<AgentTool[]> {
  const response = await fetch('/api/ai/agent/tools', { credentials: 'include' })
  const payload = await parseOrThrow<{ items: AgentTool[] }>(response, 'Falha ao listar tools')
  return payload.items
}

export async function createAgentSession(
  options: { backend?: string; locale?: string; model?: string } = {},
): Promise<AgentSessionResponse> {
  const headers = await csrfHeaders()
  const response = await fetch('/api/ai/agent/sessions', {
    method: 'POST',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      backend: options.backend ?? 'scripted',
      locale: options.locale ?? 'pt-BR',
      model: options.model ?? '',
    }),
  })
  return parseOrThrow<AgentSessionResponse>(response, 'Falha ao criar sessão de agente')
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
  signal?: AbortSignal,
): AsyncGenerator<AgentStreamEvent, void, void> {
  const headers = await csrfHeaders()
  const response = await fetch(
    `/api/ai/agent/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
      signal,
    },
  )

  if (!response.ok || response.body === null) {
    const data = await response.json().catch(() => ({}))
    const message =
      typeof (data as any)?.detail === 'string'
        ? (data as any).detail
        : `Falha no agente (HTTP ${response.status})`
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
