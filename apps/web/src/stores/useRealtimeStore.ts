import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Ticket } from '../services/ticketsClient'
import { queryClient } from '../services/queryClient'
import { applyRealtimeQueryEvent, resyncRealtimeQueries } from '../services/realtimeQueryBridge'

type RealtimeHandler = (event: RealtimeEvent) => void

export interface RealtimeWidgetSnapshot {
  widgetId: string
  integrationId?: string
  refreshedAt?: string
  status?: 'ready' | 'error'
  data?: Record<string, unknown>
  meta?: {
    source?: string
    cacheTtlSeconds?: number
    refreshIntervalSeconds?: number
    error?: {
      message?: string
    }
  }
}

export interface RealtimeEvent {
  type: string
  ownerUserId?: string
  integrationId?: string
  eventId?: string | null
  receivedAt?: string
  refresh?: string[]
  event?: Record<string, any>
  ticket?: Ticket
  widgets?: RealtimeWidgetSnapshot[]
}

const WIDGET_HEARTBEAT_INTERVAL_MS = 5000

export const useRealtimeStore = defineStore('realtime', () => {
  let source: EventSource | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  const handlers = new Set<RealtimeHandler>()
  const connectionState = ref<'idle' | 'connecting' | 'connected' | 'error'>('idle')
  const lastEvent = ref<RealtimeEvent | null>(null)
  const lastErrorAt = ref<string | null>(null)
  const eventCount = ref(0)
  let resyncPending = false

  function _dispatchWidgetHeartbeat() {
    const heartbeat: RealtimeEvent = {
      type: 'widget.heartbeat',
      refresh: ['widgets'],
      receivedAt: new Date().toISOString(),
    }
    applyRealtimeQueryEvent(queryClient, heartbeat)
    for (const handler of handlers) handler(heartbeat)
  }

  function connect() {
    if (source || typeof window === 'undefined' || typeof EventSource === 'undefined') return
    connectionState.value = 'connecting'
    source = new EventSource('/api/events/stream', { withCredentials: true })
    source.onmessage = handleMessage
    source.addEventListener('connected', handleMessage)
    source.addEventListener('fortigate.syslog.event', handleMessage)
    source.addEventListener('soc.event.created', handleMessage)
    source.addEventListener('soc.incident.created', handleMessage)
    source.addEventListener('fortigate.ingestion.events', handleMessage)
    source.addEventListener('audit.siem.event', handleMessage)
    source.addEventListener('soc.incidents.reset', handleMessage)
    source.onerror = () => {
      connectionState.value = 'error'
      lastErrorAt.value = new Date().toISOString()
      resyncPending = true
    }
    if (!heartbeatTimer) {
      heartbeatTimer = setInterval(_dispatchWidgetHeartbeat, WIDGET_HEARTBEAT_INTERVAL_MS)
    }
  }

  function handleMessage(message: MessageEvent) {
    if (!message.data) return
    try {
      const event = JSON.parse(message.data) as RealtimeEvent
      connectionState.value = 'connected'
      lastEvent.value = event
      eventCount.value += 1
      applyRealtimeQueryEvent(queryClient, event)
      if (resyncPending && event.type !== 'connected') {
        resyncPending = false
        resyncRealtimeQueries(queryClient)
      }
      for (const handler of handlers) handler(event)
    } catch {
      // Ignore malformed keep-alive/proxy noise.
    }
  }

  function subscribe(handler: RealtimeHandler) {
    handlers.add(handler)
    connect()
    return () => {
      handlers.delete(handler)
    }
  }

  function disconnect() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    source?.close()
    source = null
    connectionState.value = 'idle'
    handlers.clear()
  }

  return {
    connectionState,
    lastEvent,
    lastErrorAt,
    eventCount,
    connect,
    subscribe,
    disconnect,
  }
})
