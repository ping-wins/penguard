import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useRealtimeStore } from '../../src/stores/useRealtimeStore'
import { useTicketsStore } from '../../src/stores/useTicketsStore'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners: Record<string, Array<(message: MessageEvent) => void>> = {}
  onmessage: ((message: MessageEvent) => void) | null = null
  url: string
  withCredentials: boolean
  closed = false

  constructor(url: string, init?: EventSourceInit) {
    this.url = url
    this.withCredentials = Boolean(init?.withCredentials)
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const callback = typeof listener === 'function'
      ? listener as (message: MessageEvent) => void
      : (message: MessageEvent) => listener.handleEvent(message)
    this.listeners[type] = [...(this.listeners[type] || []), callback]
  }

  emit(type: string, payload: unknown) {
    const message = new MessageEvent(type, { data: JSON.stringify(payload) })
    if (type === 'message') this.onmessage?.(message)
    for (const listener of this.listeners[type] || []) listener(message)
  }

  close() {
    this.closed = true
  }
}

describe('tickets realtime store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  it('applies ticket payloads from the shared SSE stream without dashboard polling', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
    vi.stubGlobal('fetch', fetcher)

    const ticketsStore = useTicketsStore()
    ticketsStore.startRealtime()

    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledTimes(1)
    })
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toBe('/api/events/stream')
    expect(FakeEventSource.instances[0].withCredentials).toBe(true)

    FakeEventSource.instances[0].emit('fortigate.syslog.event', {
      type: 'fortigate.syslog.event',
      integrationId: 'int_fgt_01',
      ticket: {
        id: 'inc_syslog_01',
        title: 'FortiGate denied traffic burst',
        severity: 'high',
        triageLevel: 'T1',
        ticketStatus: 'new',
        createdAt: '2026-05-15T12:00:00.000Z',
      },
    })

    await vi.waitFor(() => {
      expect(ticketsStore.tickets.map((ticket) => ticket.id)).toEqual(['inc_syslog_01'])
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(useRealtimeStore().lastEvent?.type).toBe('fortigate.syslog.event')
  })

  it('applies audit-created ticket payloads without another GET', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
    vi.stubGlobal('fetch', fetcher)

    const ticketsStore = useTicketsStore()
    ticketsStore.startRealtime()

    await vi.waitFor(() => {
      expect(fetcher).toHaveBeenCalledTimes(1)
    })

    FakeEventSource.instances[0].emit('audit.siem.event', {
      type: 'audit.siem.event',
      eventId: 'evt_audit_01',
      ticket: {
        id: 'inc_audit_01',
        title: 'Repeated failed FortiDashboard logins',
        severity: 'medium',
        triageLevel: 'T2',
        ticketStatus: 'new',
        createdAt: '2026-05-15T12:05:00.000Z',
      },
    })

    await vi.waitFor(() => {
      expect(ticketsStore.tickets.map((ticket) => ticket.id)).toEqual(['inc_audit_01'])
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(useRealtimeStore().lastEvent?.type).toBe('audit.siem.event')
  })

  it('refreshes tickets when the incident reset event is received', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        items: [{
          id: 'inc_stale_01',
          title: 'Stale incident',
          severity: 'high',
          triageLevel: 'T1',
          ticketStatus: 'new',
          createdAt: '2026-05-15T12:00:00.000Z',
        }],
      }))
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
    vi.stubGlobal('fetch', fetcher)

    const ticketsStore = useTicketsStore()
    ticketsStore.startRealtime()

    await vi.waitFor(() => {
      expect(ticketsStore.tickets.map((ticket) => ticket.id)).toEqual(['inc_stale_01'])
    })

    FakeEventSource.instances[0].emit('soc.incidents.reset', {
      type: 'soc.incidents.reset',
      refresh: ['tickets', 'widgets'],
      eventsDeleted: 4,
      incidentsDeleted: 1,
    })

    await vi.waitFor(() => {
      expect(ticketsStore.tickets).toEqual([])
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(useRealtimeStore().lastEvent?.type).toBe('soc.incidents.reset')
  })
})
