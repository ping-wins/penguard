import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getEndpointTimeline, listEndpoints } from '../../src/services/endpointsClient'
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

describe('endpoints client and store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads endpoint inventory and timeline with browser credentials', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [endpoint] }))
      .mockResolvedValueOnce(jsonResponse({ endpointId: 'win-server-01', items: [timelineItem] }))

    await expect(listEndpoints(fetcher)).resolves.toEqual([endpoint])
    await expect(getEndpointTimeline('win-server-01', fetcher)).resolves.toEqual([timelineItem])

    expect(fetcher).toHaveBeenNthCalledWith(1, '/api/weapons/endpoints', {
      credentials: 'include',
    })
    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/weapons/endpoints/win-server-01/timeline', {
      credentials: 'include',
    })
  })

  it('keeps selected endpoint detail and timeline in the store', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/weapons/endpoints') return Promise.resolve(jsonResponse({ items: [endpoint] }))
      if (url === '/api/weapons/endpoints/win-server-01/timeline') {
        return Promise.resolve(jsonResponse({ endpointId: 'win-server-01', items: [timelineItem] }))
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
    expect(store.latestConnectionCount).toBe(1)
  })
})
