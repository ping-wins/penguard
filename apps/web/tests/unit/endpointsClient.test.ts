import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildAgentRunCommand,
  createEndpointEnrollment,
  deleteEndpoint,
  getEndpointRelatedIncidents,
  getEndpointTimeline,
  listEndpoints,
} from '../../src/services/endpointsClient'
import { useEndpointsStore } from '../../src/stores/useEndpointsStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const endpoint = {
  id: 'win-server-01',
  hostname: 'WIN-T2D53C8JOKL',
  ipAddresses: ['192.168.56.10'],
  currentUser: 'FORTIDASHBOARD\\Administrator',
  lastSeenAt: '2026-05-12T22:32:18.675000Z',
  health: 'unknown',
  attributes: { os: 'Windows' },
}

const timelineItem = {
  id: 'tl_01',
  endpointId: 'win-server-01',
  eventType: 'connection.snapshot',
  occurredAt: '2026-05-12T22:32:18.675000Z',
  title: 'Connection Snapshot',
  hostname: 'WIN-T2D53C8JOKL',
  ipAddresses: ['192.168.56.10'],
  currentUser: null,
  health: null,
  attributes: {
    connections: [{ localAddress: { ip: '0.0.0.0', port: 51708 }, remoteAddress: null, status: 'NONE', pid: 2972 }],
  },
}

const relatedIncident = {
  id: 'inc_endpoint',
  title: 'Suspicious endpoint connection',
  severity: 'high',
  triageLevel: 'T1',
  ticketStatus: 'new',
  source: 'xdr_rico',
  entities: { endpointId: 'win-server-01' },
}

describe('endpoints client and store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads endpoint inventory and timeline with browser credentials', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [endpoint] }))
      .mockResolvedValueOnce(jsonResponse({ endpointId: 'win-server-01', items: [timelineItem] }))
      .mockResolvedValueOnce(jsonResponse({ endpointId: 'win-server-01', items: [relatedIncident], total: 1 }))

    await expect(listEndpoints(fetcher)).resolves.toEqual([endpoint])
    await expect(getEndpointTimeline('win-server-01', fetcher)).resolves.toEqual([timelineItem])
    await expect(getEndpointRelatedIncidents('win-server-01', fetcher)).resolves.toEqual({
      endpointId: 'win-server-01',
      items: [relatedIncident],
      total: 1,
    })

    expect(fetcher).toHaveBeenNthCalledWith(1, '/api/weapons/endpoints', {
      credentials: 'include',
    })
    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/weapons/endpoints/win-server-01/timeline', {
      credentials: 'include',
    })
    expect(fetcher).toHaveBeenNthCalledWith(3, '/api/weapons/endpoints/win-server-01/related-incidents', {
      credentials: 'include',
    })
  })

  it('creates endpoint enrollment through the BFF with CSRF', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_01' }))
      .mockResolvedValueOnce(jsonResponse({
        id: 'enr_01',
        displayName: 'Windows Server Lab',
        hostnameHint: 'WIN-LAB-01',
        createdAt: '2026-05-13T18:00:00.000Z',
        token: 'enrollment-token',
      }))

    await expect(createEndpointEnrollment({
      displayName: 'Windows Server Lab',
      hostnameHint: 'WIN-LAB-01',
    }, fetcher)).resolves.toMatchObject({ id: 'enr_01', token: 'enrollment-token' })

    expect(fetcher).toHaveBeenNthCalledWith(1, '/api/auth/csrf', { credentials: 'include' })
    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/weapons/enrollments', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      }),
      body: JSON.stringify({
        displayName: 'Windows Server Lab',
        hostnameHint: 'WIN-LAB-01',
      }),
    }))
  })

  it('deletes endpoint through the BFF with CSRF', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_01' }))
      .mockResolvedValueOnce(jsonResponse({ deleted: true, endpointId: 'win-server-01' }))

    await expect(deleteEndpoint('win-server-01', fetcher)).resolves.toBeUndefined()

    expect(fetcher).toHaveBeenNthCalledWith(1, '/api/auth/csrf', { credentials: 'include' })
    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/weapons/endpoints/win-server-01', {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'X-CSRF-Token': 'csrf_01',
      },
    })
  })

  it('builds a PowerShell-friendly agent run command', () => {
    const command = buildAgentRunCommand({
      id: 'enr_01',
      displayName: 'Windows Server Lab',
      hostnameHint: 'WIN-LAB-01',
      createdAt: '2026-05-13T18:00:00.000Z',
      token: 'enrollment-token',
    }, 'http://localhost:8000')

    expect(command).toBe(
      'cd apps\\agent_private; '
      + '$env:AGENT_PRIVATE_API_URL="http://localhost:8000"; '
      + '$env:AGENT_PRIVATE_ENDPOINT_ID="enr_01"; '
      + '$env:AGENT_PRIVATE_ENROLLMENT_TOKEN="enrollment-token"; '
      + 'uv run agent-private run',
    )
  })

  it('keeps selected endpoint detail and timeline in the store', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/weapons/endpoints') return Promise.resolve(jsonResponse({ items: [endpoint] }))
      if (url === '/api/weapons/endpoints/win-server-01/timeline') {
        return Promise.resolve(jsonResponse({ endpointId: 'win-server-01', items: [timelineItem] }))
      }
      if (url === '/api/weapons/endpoints/win-server-01/related-incidents') {
        return Promise.resolve(jsonResponse({
          endpointId: 'win-server-01',
          items: [relatedIncident],
          total: 1,
        }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = useEndpointsStore()
    await store.refresh()
    await store.selectEndpoint('win-server-01')

    expect(store.endpoints).toEqual([endpoint])
    expect(store.selectedEndpoint?.hostname).toBe('WIN-T2D53C8JOKL')
    expect(store.timeline).toEqual([timelineItem])
    expect(store.relatedIncidents).toEqual([relatedIncident])
    expect(store.latestConnectionCount).toBe(1)
  })

  it('tracks pending enrollments and resolves them when the endpoint id comes online', async () => {
    const onlineEndpoint = {
      ...endpoint,
      id: 'enr_01',
      hostname: 'WIN-LAB-01',
    }
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/auth/csrf') return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url === '/api/weapons/enrollments') {
        return Promise.resolve(jsonResponse({
          id: 'enr_01',
          displayName: 'Windows Server Lab',
          hostnameHint: 'WIN-LAB-01',
          createdAt: '2026-05-13T18:00:00.000Z',
          token: 'enrollment-token',
        }))
      }
      if (url === '/api/weapons/endpoints') return Promise.resolve(jsonResponse({ items: [onlineEndpoint] }))
      if (url === '/api/weapons/endpoints/enr_01/timeline') {
        return Promise.resolve(jsonResponse({ endpointId: 'enr_01', items: [] }))
      }
      if (url === '/api/weapons/endpoints/enr_01/related-incidents') {
        return Promise.resolve(jsonResponse({ endpointId: 'enr_01', items: [], total: 0 }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = useEndpointsStore()
    await expect(store.createEnrollment({
      displayName: 'Windows Server Lab',
      hostnameHint: 'WIN-LAB-01',
    })).resolves.toMatchObject({ id: 'enr_01' })

    expect(store.pendingEnrollments).toHaveLength(1)
    expect(store.pendingEnrollments[0]).toMatchObject({
      enrollmentId: 'enr_01',
      hostnameHint: 'WIN-LAB-01',
      status: 'pending',
    })
    expect(store.pendingEnrollments[0].command).toContain(
      '$env:AGENT_PRIVATE_ENROLLMENT_TOKEN="enrollment-token"',
    )

    await store.refresh()

    expect(store.endpoints).toEqual([onlineEndpoint])
    expect(store.pendingEnrollments).toEqual([])
  })

  it('resolves pending enrollment when a fresh heartbeat arrives from the hinted hostname', async () => {
    const onlineEndpoint = {
      ...endpoint,
      id: 'manually-configured-id',
      hostname: 'WIN-LAB-01',
      lastSeenAt: '2026-05-13T18:01:00.000Z',
    }
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/auth/csrf') return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url === '/api/weapons/enrollments') {
        return Promise.resolve(jsonResponse({
          id: 'enr_01',
          displayName: 'Windows Server Lab',
          hostnameHint: 'WIN-LAB-01',
          createdAt: '2026-05-13T18:00:00.000Z',
          token: 'enrollment-token',
        }))
      }
      if (url === '/api/weapons/endpoints') return Promise.resolve(jsonResponse({ items: [onlineEndpoint] }))
      if (url === '/api/weapons/endpoints/manually-configured-id/timeline') {
        return Promise.resolve(jsonResponse({ endpointId: 'manually-configured-id', items: [] }))
      }
      if (url === '/api/weapons/endpoints/manually-configured-id/related-incidents') {
        return Promise.resolve(jsonResponse({ endpointId: 'manually-configured-id', items: [], total: 0 }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = useEndpointsStore()
    await store.createEnrollment({
      displayName: 'Windows Server Lab',
      hostnameHint: 'WIN-LAB-01',
    })
    await store.refresh()

    expect(store.pendingEnrollments).toEqual([])
    expect(store.endpoints[0].id).toBe('manually-configured-id')
  })

  it('does not resolve pending enrollment only because a stale hostname matches', async () => {
    const staleEndpoint = {
      ...endpoint,
      id: 'old-endpoint-id',
      hostname: 'WIN-LAB-01',
    }
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/auth/csrf') return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url === '/api/weapons/enrollments') {
        return Promise.resolve(jsonResponse({
          id: 'enr_01',
          displayName: 'Windows Server Lab',
          hostnameHint: 'WIN-LAB-01',
          createdAt: '2026-05-13T18:00:00.000Z',
          token: 'enrollment-token',
        }))
      }
      if (url === '/api/weapons/endpoints') return Promise.resolve(jsonResponse({ items: [staleEndpoint] }))
      return Promise.resolve(jsonResponse({ endpointId: 'old-endpoint-id', items: [], total: 0 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = useEndpointsStore()
    await store.createEnrollment({
      displayName: 'Windows Server Lab',
      hostnameHint: 'WIN-LAB-01',
    })
    await store.refresh()

    expect(store.pendingEnrollments).toHaveLength(1)
    expect(store.pendingEnrollments[0].enrollmentId).toBe('enr_01')
  })

  it('removes pending cards locally and deletes real endpoints through the store', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/auth/csrf') return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url === '/api/weapons/enrollments') {
        return Promise.resolve(jsonResponse({
          id: 'enr_01',
          displayName: 'Windows Server Lab',
          hostnameHint: 'WIN-LAB-01',
          createdAt: '2026-05-13T18:00:00.000Z',
          token: 'enrollment-token',
        }))
      }
      if (url === '/api/weapons/endpoints/win-server-01' && init?.method === 'DELETE') {
        return Promise.resolve(jsonResponse({ deleted: true }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = useEndpointsStore()
    await store.createEnrollment({
      displayName: 'Windows Server Lab',
      hostnameHint: 'WIN-LAB-01',
    })
    store.dismissPendingEnrollment('enr_01')
    expect(store.pendingEnrollments).toEqual([])

    store.endpoints = [endpoint]
    store.selectedEndpointId = 'win-server-01'
    await store.removeEndpoint('win-server-01')

    expect(store.endpoints).toEqual([])
    expect(store.selectedEndpointId).toBeNull()
  })
})
