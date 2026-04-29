import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AuditFeed from '../../src/components/audit/AuditFeed.vue'
import { formatAuditEvent } from '../../src/components/audit/auditFormat'
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

  it('renders loading, empty, error, and event rows without exposing secrets', () => {
    expect(mount(AuditFeed, { props: { isLoading: true, events: [] } }).text())
      .toContain('Loading audit trail')
    expect(mount(AuditFeed, { props: { events: [] } }).text())
      .toContain('No sensitive activity recorded')
    expect(mount(AuditFeed, { props: { events: [], error: 'Audit unavailable' } }).text())
      .toContain('Audit unavailable')

    const wrapper = mount(AuditFeed, {
      props: {
        events: [{
          ...loginEvent,
          action: 'integration.fortigate.created',
          details: {
            integrationId: 'int_fgt_01',
            apiKey: 'plain-secret-key',
          },
        }],
      },
    })

    expect(wrapper.text()).toContain('FortiGate integration created')
    expect(wrapper.text()).toContain('analyst@example.com')
    expect(wrapper.text()).toContain('int_fgt_01')
    expect(wrapper.text()).toContain('[REDACTED]')
    expect(wrapper.text()).not.toContain('plain-secret-key')
  })
})
