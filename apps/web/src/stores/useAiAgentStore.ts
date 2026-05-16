import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  type AgentBackend,
  type AgentSessionResponse,
  type AgentStreamEvent,
  type AgentTool,
  createAgentSession,
  deleteAgentSession,
  listAgentTools,
  listBackends,
  streamAgentMessage,
} from '../services/aiAgentClient'

export type AgentTraceEntry =
  | { kind: 'user'; step: number; content: string }
  | { kind: 'text'; step: number; text: string }
  | {
      kind: 'tool_call'
      step: number
      callId: string
      toolName: string
      args: Record<string, unknown>
      result?: unknown
      status?: 'ok' | 'error'
      error?: string | null
      latencyMs?: number
    }
  | { kind: 'error'; step: number; message: string; code: string }

export const useAiAgentStore = defineStore('aiAgent', () => {
  const backends = ref<AgentBackend[]>([])
  const tools = ref<AgentTool[]>([])
  const session = ref<AgentSessionResponse | null>(null)
  const trace = ref<AgentTraceEntry[]>([])
  const isLoading = ref(false)
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  const lastReply = ref<string>('')

  async function ensureCatalog() {
    if (backends.value.length > 0 && tools.value.length > 0) return
    isLoading.value = true
    try {
      const [b, t] = await Promise.all([listBackends(), listAgentTools()])
      backends.value = b
      tools.value = t
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      isLoading.value = false
    }
  }

  async function startSession(backend = 'scripted', locale = 'pt-BR') {
    error.value = null
    isLoading.value = true
    try {
      session.value = await createAgentSession({ backend, locale })
      trace.value = []
      lastReply.value = ''
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      isLoading.value = false
    }
  }

  async function endSession() {
    if (!session.value) return
    const id = session.value.sessionId
    session.value = null
    trace.value = []
    try {
      await deleteAgentSession(id)
    } catch {
      // best-effort
    }
  }

  async function sendMessage(content: string) {
    if (!session.value) {
      await startSession()
      if (!session.value) return
    }
    error.value = null
    isStreaming.value = true
    trace.value.push({ kind: 'user', step: 0, content })

    try {
      for await (const event of streamAgentMessage(session.value.sessionId, content)) {
        consumeEvent(event)
      }
    } catch (e) {
      error.value = (e as Error).message
      trace.value.push({
        kind: 'error',
        step: -1,
        message: error.value || 'stream error',
        code: 'stream_error',
      })
    } finally {
      isStreaming.value = false
    }
  }

  function consumeEvent(event: AgentStreamEvent) {
    if (event.type === 'connected') return
    if (event.kind === 'text_delta') {
      trace.value.push({ kind: 'text', step: event.step, text: event.text })
      return
    }
    if (event.kind === 'tool_call') {
      trace.value.push({
        kind: 'tool_call',
        step: event.step,
        callId: event.call_id,
        toolName: event.tool_name,
        args: event.args,
      })
      return
    }
    if (event.kind === 'tool_result') {
      const target = trace.value.find(
        (entry) => entry.kind === 'tool_call' && entry.callId === event.call_id,
      )
      if (target && target.kind === 'tool_call') {
        target.result = event.result
        target.status = event.status
        target.error = event.error
        target.latencyMs = event.latency_ms
      }
      return
    }
    if (event.kind === 'done') {
      lastReply.value = event.reply
      return
    }
    if (event.kind === 'error') {
      trace.value.push({
        kind: 'error',
        step: event.step,
        message: event.message,
        code: event.code,
      })
    }
  }

  function reset() {
    backends.value = []
    tools.value = []
    session.value = null
    trace.value = []
    error.value = null
    isLoading.value = false
    isStreaming.value = false
    lastReply.value = ''
  }

  return {
    backends,
    tools,
    session,
    trace,
    isLoading,
    isStreaming,
    error,
    lastReply,
    ensureCatalog,
    startSession,
    endSession,
    sendMessage,
    reset,
  }
})
