import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AuditFeed from '../../src/components/audit/AuditFeed.vue'
import { formatAuditEvent } from '../../src/components/audit/auditFormat'
import { i18n, setLocale } from '../../src/i18n'
import { fetchAuditEvents } from '../../src/services/auditClient'
import { useAuditStore } from '../../src/stores/useAuditStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const loginEvent = {
  id: 'audit_01',
  actor: { id: 'usr_01', email: 'analyst@example.com' },
  action: 'login',
  outcome: 'success',
  ipAddress: '192.0.2.10',
  userAgent: 'Mozilla/5.0',
  details: {},
  createdAt: '2026-04-26T21:10:00.000Z',
}

describe('audit feed', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    })
    setLocale('en-US')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('fetches audit events with browser credentials and a bounded limit', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ items: [loginEvent] }))

    await expect(fetchAuditEvents({ limit: 25, fetcher })).resolves.toEqual({
      items: [loginEvent],
    })

    expect(fetcher).toHaveBeenCalledWith('/api/audit/events?limit=25', {
      credentials: 'include',
    })
  })

  it('fetches admin audit events from the admin endpoint when scoped globally', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ items: [loginEvent] }))

    await fetchAuditEvents({ limit: 500, scope: 'admin', fetcher })

    expect(fetcher).toHaveBeenCalledWith('/api/admin/audit/events?limit=100', {
      credentials: 'include',
    })
  })

  it('maps known and unknown audit actions into readable SOC labels', () => {
    expect(formatAuditEvent({ ...loginEvent, action: 'login', outcome: 'success' }).title)
      .toBe('Login succeeded')
    expect(formatAuditEvent({ ...loginEvent, action: 'login', outcome: 'provider_error' }).title)
      .toBe('Login failed')
    expect(formatAuditEvent({ ...loginEvent, action: 'integration.fortigate.created' }).title)
      .toBe('FortiGate integration created')
    expect(formatAuditEvent({ ...loginEvent, action: 'integration.fortigate.deleted' }).title)
      .toBe('FortiGate integration removed')
    expect(formatAuditEvent({ ...loginEvent, action: 'workspace.updated' }).title)
      .toBe('Workspace updated')
    expect(formatAuditEvent({ ...loginEvent, action: 'soc.demo.replay' }).title)
      .toBe('Demo incident replayed')
    expect(formatAuditEvent({ ...loginEvent, action: 'soc.incident.analyzed' }).title)
      .toBe('Incident analyzed by AI')
    expect(formatAuditEvent({ ...loginEvent, action: 'soc.ticket.playbook_drafted' }).title)
      .toBe('Containment playbook drafted')
    expect(formatAuditEvent({ ...loginEvent, action: 'soc.ticket.contained' }).title)
      .toBe('Ticket contained')
    expect(formatAuditEvent({ ...loginEvent, action: 'workspace.imported' }).title)
      .toBe('Workspace imported')
    expect(formatAuditEvent({ ...loginEvent, action: 'workspace.exported' }).title)
      .toBe('Workspace exported')
    expect(formatAuditEvent({ ...loginEvent, action: 'workspace.presentation.updated' }).title)
      .toBe('Presentation updated')
    expect(formatAuditEvent({ ...loginEvent, action: 'workspace.widget.rebound' }).title)
      .toBe('Widget integration rebound')
    expect(formatAuditEvent({ ...loginEvent, action: 'audit.events.viewed' }).title)
      .toBe('Audit trail viewed')
    expect(formatAuditEvent({ ...loginEvent, action: 'tenant.unknown.action' }).title)
      .toBe('tenant.unknown.action')
  })

  it('redacts sensitive detail fields before formatting them for render', () => {
    const formatted = formatAuditEvent({
      ...loginEvent,
      action: 'integration.fortigate.created',
      details: {
        integrationId: 'int_fgt_01',
        apiKey: 'plain-secret-key',
        nested: { refresh_token: 'refresh-secret', status: '[REDACTED]' },
      },
    })

    expect(formatted.detailRows).toEqual([
      ['integrationId', 'int_fgt_01'],
      ['apiKey', '[REDACTED]'],
      ['nested.refresh_token', '[REDACTED]'],
      ['nested.status', '[REDACTED]'],
    ])
    expect(JSON.stringify(formatted)).not.toContain('plain-secret-key')
    expect(JSON.stringify(formatted)).not.toContain('refresh-secret')
  })

  it('loads events through the store and exposes loading, empty, and error states', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Audit unavailable' }, { status: 503 }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAuditStore()
    await store.fetchEvents()
    expect(store.events).toEqual([])
    expect(store.isEmpty).toBe(true)
    expect(store.error).toBeNull()

    await store.fetchEvents()
    expect(store.error).toBe('Audit unavailable')
    expect(store.isLoading).toBe(false)
  })

  it('loads admin scoped events through the store', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(jsonResponse({ items: [loginEvent] }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAuditStore()
    await store.fetchEvents({ scope: 'admin', limit: 20 })

    expect(fetcher).toHaveBeenCalledWith('/api/admin/audit/events?limit=20', {
      credentials: 'include',
    })
    expect(store.events).toEqual([loginEvent])
    expect(store.scope).toBe('admin')
  })

  it('polls audit events until polling is stopped', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ items: [loginEvent] }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAuditStore()
    store.startPolling({ scope: 'admin', limit: 10, intervalMs: 2000 })
    await vi.advanceTimersByTimeAsync(0)

    expect(fetcher).toHaveBeenCalledWith('/api/admin/audit/events?limit=10', {
      credentials: 'include',
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2000)
    expect(fetcher).toHaveBeenCalledTimes(2)

    store.stopPolling()
    await vi.advanceTimersByTimeAsync(4000)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('renders loading, empty, error, and event rows without exposing secrets', () => {
    expect(mountAuditFeed({ isLoading: true, events: [] }).text())
      .toContain('Loading audit trail')
    expect(mountAuditFeed({
      title: 'Admin audit trail',
      subtitle: 'Global SOC activity',
      events: [],
    }).text())
      .toContain('Global SOC activity')
    expect(mountAuditFeed({ events: [] }).text())
      .toContain('No sensitive activity recorded')
    expect(mountAuditFeed({ events: [], error: 'Audit unavailable' }).text())
      .toContain('Audit unavailable')

    const wrapper = mountAuditFeed({
      events: [
        {
          ...loginEvent,
          action: 'integration.fortigate.created',
          details: {
            integrationId: 'int_fgt_01',
            apiKey: 'plain-secret-key',
          },
        },
      ],
    })

    expect(wrapper.text()).toContain('FortiGate integration created')
    expect(wrapper.text()).toContain('analyst@example.com')
    expect(wrapper.text()).toContain('int_fgt_01')
    expect(wrapper.text()).toContain('[REDACTED]')
    expect(wrapper.text()).not.toContain('plain-secret-key')
  })
})

function mountAuditFeed(props: Record<string, unknown>) {
  return mount(AuditFeed, {
    props,
    global: {
      plugins: [i18n],
    },
  })
}
