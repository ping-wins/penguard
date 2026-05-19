import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { i18n } from '../i18n'
import { useDashboardStore } from './useDashboardStore'
import {
  type AgentSessionResponse,
  type AgentStreamEvent,
  type AgentTool,
  approveAgentToolCall,
  createAgentSession,
  deleteAgentSession,
  listAgentTools,
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
      status?: 'ok' | 'error' | 'denied'
      error?: string | null
      latencyMs?: number
    }
  | { kind: 'error'; step: number; message: string; code: string }

export type PendingAgentApproval = {
  callId: string
  toolName: string
  args: Record<string, unknown>
  reason: string
}

function localizedError(message: string, code?: string): string {
  if (code === 'agent_not_configured' || message === 'SOC Assistant provider is not configured') {
    return i18n.global.t('aiAgent.errorNotConfigured')
  }
  return message
}

const STORAGE_KEY = 'penguard.aiAgent.state'

type PersistedState = {
  session: AgentSessionResponse | null
  trace: AgentTraceEntry[]
  tokensIn: number
  tokensOut: number
  lastReply: string
}

function loadPersisted(): PersistedState | null {
  if (typeof window === 'undefined' || !window.localStorage) return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const data = JSON.parse(raw) as PersistedState
    if (!data || typeof data !== 'object') return null
    return data
  } catch {
    return null
  }
}

function savePersisted(state: PersistedState): void {
  if (typeof window === 'undefined' || !window.localStorage) return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // ignore quota / privacy-mode errors
  }
}

function clearPersisted(): void {
  if (typeof window === 'undefined' || !window.localStorage) return
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

export const useAiAgentStore = defineStore('aiAgent', () => {
  const tools = ref<AgentTool[]>([])
  const persisted = loadPersisted()
  const session = ref<AgentSessionResponse | null>(persisted?.session ?? null)
  const trace = ref<AgentTraceEntry[]>(persisted?.trace ?? [])
  const isLoading = ref(false)
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  const lastReply = ref<string>(persisted?.lastReply ?? '')
  const pendingApproval = ref<PendingAgentApproval | null>(null)
  const tokensIn = ref(persisted?.tokensIn ?? 0)
  const tokensOut = ref(persisted?.tokensOut ?? 0)

  watch(
    [session, trace, tokensIn, tokensOut, lastReply],
    () => {
      if (!session.value) {
        clearPersisted()
        return
      }
      savePersisted({
        session: session.value,
        trace: trace.value,
        tokensIn: tokensIn.value,
        tokensOut: tokensOut.value,
        lastReply: lastReply.value,
      })
    },
    { deep: true },
  )

  async function ensureCatalog() {
    if (tools.value.length > 0) return
    isLoading.value = true
    try {
      tools.value = await listAgentTools()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      isLoading.value = false
    }
  }

  async function startSession(options: { locale?: string } = {}) {
    error.value = null
    isLoading.value = true
    try {
      session.value = await createAgentSession({
        locale: options.locale ?? String(i18n.global.locale.value || 'pt-BR'),
      })
      trace.value = []
      lastReply.value = ''
      pendingApproval.value = null
      tokensIn.value = session.value.tokensIn
      tokensOut.value = session.value.tokensOut
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
    pendingApproval.value = null
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

    let attempted_recovery = false
    while (true) {
      try {
        const dashboardStore = useDashboardStore()
        for await (const event of streamAgentMessage(
          session.value.sessionId,
          content,
          { workspaceId: dashboardStore.activeWorkspaceId },
        )) {
          consumeEvent(event)
        }
        break
      } catch (e) {
        const msg = (e as Error).message || ''
        if (!attempted_recovery && /session not found/i.test(msg)) {
          attempted_recovery = true
          try {
            session.value = await createAgentSession({
              locale: String(i18n.global.locale.value || 'pt-BR'),
            })
            tokensIn.value = session.value.tokensIn
            tokensOut.value = session.value.tokensOut
            continue
          } catch (recoveryError) {
            error.value = (recoveryError as Error).message
            trace.value.push({
              kind: 'error',
              step: -1,
              message: error.value || msg,
              code: 'stream_error',
            })
            break
          }
        }
        error.value = msg
        trace.value.push({
          kind: 'error',
          step: -1,
          message: error.value || 'stream error',
          code: 'stream_error',
        })
        break
      }
    }
    isStreaming.value = false
  }

  function consumeEvent(event: AgentStreamEvent) {
    if (event.type === 'connected') return
    if (event.kind === 'text_delta') {
      const lastEntry = trace.value[trace.value.length - 1]
      if (lastEntry?.kind === 'text' && lastEntry.step === event.step) {
        lastEntry.text += event.text
        return
      }
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
    if (event.kind === 'awaiting_approval') {
      pendingApproval.value = {
        callId: event.call_id,
        toolName: event.tool_name,
        args: event.args,
        reason: event.reason,
      }
      trace.value.push({
        kind: 'tool_call',
        step: event.step,
        callId: event.call_id,
        toolName: event.tool_name,
        args: event.args,
      })
      return
    }
    if (event.kind === 'done') {
      lastReply.value = event.reply
      tokensIn.value = event.tokens_in
      tokensOut.value = event.tokens_out
      return
    }
    if (event.kind === 'error') {
      trace.value.push({
        kind: 'error',
        step: event.step,
        message: localizedError(event.message, event.code),
        code: event.code,
      })
    }
  }

  async function approve(callId: string, granted: boolean, reason = '') {
    if (!session.value) return
    await approveAgentToolCall(session.value.sessionId, callId, granted, reason)
    if (pendingApproval.value?.callId === callId) pendingApproval.value = null
  }

  function reset() {
    tools.value = []
    session.value = null
    trace.value = []
    pendingApproval.value = null
    error.value = null
    isLoading.value = false
    isStreaming.value = false
    lastReply.value = ''
    tokensIn.value = 0
    tokensOut.value = 0
  }

  return {
    tools,
    session,
    trace,
    isLoading,
    isStreaming,
    error,
    lastReply,
    pendingApproval,
    tokensIn,
    tokensOut,
    ensureCatalog,
    startSession,
    endSession,
    sendMessage,
    approve,
    reset,
  }
})
