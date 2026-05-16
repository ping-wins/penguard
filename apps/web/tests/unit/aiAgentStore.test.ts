import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAiAgentStore } from '../../src/stores/useAiAgentStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function sseResponse(chunks: string[]): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder()
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function sseEvent(data: object): string {
  return `event: step\ndata: ${JSON.stringify(data)}\n\n`
}

describe('useAiAgentStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads backends and tools via ensureCatalog', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [{ name: 'scripted', ready: true, default: true }] }))
      .mockResolvedValueOnce(jsonResponse({ items: [{ name: 'list_incidents', description: 'x', inputSchema: { type: 'object' }, category: 'read', requiresApproval: false, timeoutSeconds: 5 }] }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAiAgentStore()
    await store.ensureCatalog()

    expect(store.backends).toHaveLength(1)
    expect(store.backends[0].name).toBe('scripted')
    expect(store.tools).toHaveLength(1)
    expect(store.tools[0].name).toBe('list_incidents')
  })

  it('records tool_call + tool_result events in the trace', async () => {
    const csrf = jsonResponse({ csrfToken: 'csrf_42' })
    const sessionPayload = jsonResponse(
      { sessionId: 'sess_1', backend: 'scripted', model: '', locale: 'pt-BR', createdAt: 1 },
      { status: 201 },
    )
    const stream = sseResponse([
      sseEvent({ type: 'step', kind: 'tool_call', step: 1, call_id: 'c1', tool_name: 'list_incidents', args: { limit: 10 } }),
      sseEvent({ type: 'step', kind: 'tool_result', step: 1, call_id: 'c1', tool_name: 'list_incidents', status: 'ok', result: { items: [], count: 0 }, error: null, latency_ms: 3 }),
      sseEvent({ type: 'step', kind: 'done', step: 2, reply: 'pronto', used_tools: ['list_incidents'], tokens_in: 0, tokens_out: 0 }),
    ])

    const fetcher = vi.fn()
      .mockResolvedValueOnce(csrf)
      .mockResolvedValueOnce(sessionPayload)
      .mockResolvedValueOnce(stream)
    vi.stubGlobal('fetch', fetcher)

    const store = useAiAgentStore()
    await store.startSession('scripted')
    await store.sendMessage('liste incidentes')

    const toolCalls = store.trace.filter((entry) => entry.kind === 'tool_call')
    expect(toolCalls).toHaveLength(1)
    const call = toolCalls[0] as { toolName: string; status?: string; result?: unknown }
    expect(call.toolName).toBe('list_incidents')
    expect(call.status).toBe('ok')
    expect(call.result).toEqual({ items: [], count: 0 })
    expect(store.lastReply).toBe('pronto')
  })

  it('captures error events when the agent emits one', async () => {
    const csrf = jsonResponse({ csrfToken: 'csrf_42' })
    const sessionPayload = jsonResponse(
      { sessionId: 'sess_1', backend: 'scripted', model: '', locale: 'pt-BR', createdAt: 1 },
      { status: 201 },
    )
    const stream = sseResponse([
      sseEvent({ type: 'step', kind: 'error', step: 1, message: 'unknown tool', code: 'unknown_tool' }),
    ])
    const fetcher = vi.fn()
      .mockResolvedValueOnce(csrf)
      .mockResolvedValueOnce(sessionPayload)
      .mockResolvedValueOnce(stream)
    vi.stubGlobal('fetch', fetcher)

    const store = useAiAgentStore()
    await store.startSession('scripted')
    await store.sendMessage('faz algo errado')

    const errors = store.trace.filter((entry) => entry.kind === 'error')
    expect(errors).toHaveLength(1)
    const errEntry = errors[0] as { code: string; message: string }
    expect(errEntry.code).toBe('unknown_tool')
  })
})
