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
      .mockResolvedValueOnce(jsonResponse({ items: [
        {
          id: 'incident-triage',
          label: 'Incident triage',
          description: 'Analyze incidents',
          tier: 'balanced',
          localeDefault: 'pt-BR',
          tokenBudget: 150000,
          maxSteps: 20,
          allowedToolCategories: ['read', 'draft'],
        },
      ] }))
      .mockResolvedValueOnce(jsonResponse({ items: [{ name: 'scripted', ready: true, default: true }] }))
      .mockResolvedValueOnce(jsonResponse({ items: [{ name: 'list_incidents', description: 'x', inputSchema: { type: 'object' }, category: 'read', requiresApproval: false, timeoutSeconds: 5 }] }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAiAgentStore()
    await store.ensureCatalog()

    expect(store.roles).toHaveLength(1)
    expect(store.roles[0].id).toBe('incident-triage')
    expect(store.backends).toHaveLength(1)
    expect(store.backends[0].name).toBe('scripted')
    expect(store.tools).toHaveLength(1)
    expect(store.tools[0].name).toBe('list_incidents')
  })

  it('records tool_call + tool_result events in the trace', async () => {
    const csrf = jsonResponse({ csrfToken: 'csrf_42' })
    const sessionPayload = jsonResponse(
      { sessionId: 'sess_1', backend: 'scripted', model: 'scripted-cockpit-agent', role: 'incident-triage', locale: 'pt-BR', createdAt: 1, tokensIn: 0, tokensOut: 0 },
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
    await store.startSession({ role: 'incident-triage', backend: 'scripted' })
    await store.sendMessage('liste incidentes')

    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      '/api/ai/agent/sessions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ locale: 'pt-BR' }),
      }),
    )
    const toolCalls = store.trace.filter((entry) => entry.kind === 'tool_call')
    expect(toolCalls).toHaveLength(1)
    const call = toolCalls[0] as { toolName: string; status?: string; result?: unknown }
    expect(call.toolName).toBe('list_incidents')
    expect(call.status).toBe('ok')
    expect(call.result).toEqual({ items: [], count: 0 })
    expect(store.lastReply).toBe('pronto')
    expect(store.tokensIn).toBe(0)
    expect(store.tokensOut).toBe(0)
  })

  it('captures error events when the agent emits one', async () => {
    const csrf = jsonResponse({ csrfToken: 'csrf_42' })
    const sessionPayload = jsonResponse(
      { sessionId: 'sess_1', backend: 'scripted', model: '', role: 'chat', locale: 'pt-BR', createdAt: 1, tokensIn: 0, tokensOut: 0 },
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
    await store.startSession({ role: 'chat', backend: 'scripted' })
    await store.sendMessage('faz algo errado')

    const errors = store.trace.filter((entry) => entry.kind === 'error')
    expect(errors).toHaveLength(1)
    const errEntry = errors[0] as { code: string; message: string }
    expect(errEntry.code).toBe('unknown_tool')
  })

  it('tracks awaiting approvals and posts an approval decision', async () => {
    const csrf = jsonResponse({ csrfToken: 'csrf_42' })
    const sessionPayload = jsonResponse(
      { sessionId: 'sess_1', backend: 'scripted', model: '', role: 'soc-investigation', locale: 'pt-BR', createdAt: 1, tokensIn: 0, tokensOut: 0 },
      { status: 201 },
    )
    const stream = sseResponse([
      sseEvent({ type: 'step', kind: 'awaiting_approval', step: 1, call_id: 'c1', tool_name: 'write_policy', args: { policyId: 'p1' }, reason: 'write tool requires approval' }),
      sseEvent({ type: 'step', kind: 'tool_result', step: 1, call_id: 'c1', tool_name: 'write_policy', status: 'ok', result: { applied: true }, error: null, latency_ms: 4 }),
      sseEvent({ type: 'step', kind: 'done', step: 2, reply: 'applied', used_tools: ['write_policy'], tokens_in: 12, tokens_out: 5 }),
    ])

    const fetcher = vi.fn()
      .mockResolvedValueOnce(csrf)
      .mockResolvedValueOnce(sessionPayload)
      .mockResolvedValueOnce(stream)
      .mockResolvedValueOnce(jsonResponse({ sessionId: 'sess_1', callId: 'c1', granted: true }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAiAgentStore()
    await store.startSession({ role: 'soc-investigation', backend: 'scripted' })
    await store.sendMessage('apply')

    expect(store.pendingApproval?.callId).toBe('c1')
    await store.approve('c1', true, 'ok')

    expect(fetcher).toHaveBeenLastCalledWith(
      '/api/ai/agent/sessions/sess_1/approvals/c1',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ granted: true, reason: 'ok' }),
      }),
    )
    expect(store.pendingApproval).toBeNull()
    expect(store.tokensIn).toBe(12)
    expect(store.tokensOut).toBe(5)
  })
})
