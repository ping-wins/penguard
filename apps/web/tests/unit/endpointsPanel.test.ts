import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EndpointsPanel from '../../src/components/endpoints/EndpointsPanel.vue'
import { i18n, setLocale } from '../../src/i18n'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const endpoint = {
  id: 'win-server-01',
  hostname: 'WIN-T2D53C8JOKL',
  ipAddresses: ['10.0.2.15', '192.168.56.10'],
  currentUser: 'FORTIDASHBOARD\\Administrator',
  lastSeenAt: '2026-05-12T22:32:18.675000Z',
  health: 'unknown',
  attributes: { os: 'Windows', observedSourceIp: '192.168.56.10' },
}

describe('EndpointsPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('en-US')
  })

  it('renders endpoint inventory, timeline, and connection snapshot counts', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/weapons/endpoints') {
        return Promise.resolve(jsonResponse({ items: [endpoint] }))
      }
      if (url === '/api/weapons/endpoints/win-server-01/timeline') {
        return Promise.resolve(jsonResponse({
          endpointId: 'win-server-01',
          items: [
            {
              id: 'tl_conn',
              endpointId: 'win-server-01',
              eventType: 'connection.snapshot',
              occurredAt: '2026-05-12T22:32:18.675000Z',
              title: 'Connection Snapshot',
              hostname: 'WIN-T2D53C8JOKL',
              ipAddresses: ['192.168.56.10'],
              currentUser: null,
              health: null,
              attributes: {
                connections: [
                  {
                    localAddress: { ip: '0.0.0.0', port: 51708 },
                    remoteAddress: null,
                    status: 'NONE',
                    pid: 2972,
                  },
                ],
              },
            },
            {
              id: 'tl_proc',
              endpointId: 'win-server-01',
              eventType: 'process.snapshot',
              occurredAt: '2026-05-12T22:21:41.651000Z',
              title: 'Process Snapshot',
              hostname: 'WIN-T2D53C8JOKL',
              ipAddresses: ['192.168.56.10'],
              currentUser: null,
              health: null,
              attributes: {
                processes: [{ pid: 424, name: 'csrss.exe' }],
              },
            },
          ],
        }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(EndpointsPanel, {
      global: {
        plugins: [i18n],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Endpoints')
    expect(wrapper.text()).toContain('WIN-T2D53C8JOKL')
    expect(wrapper.text()).toContain('192.168.56.10')
    expect(wrapper.text()).toContain('Observed via API')
    expect(wrapper.text()).toContain('Connection Snapshot')
    expect(wrapper.text()).toContain('1 connection')
    expect(wrapper.text()).toContain('1 process')
    expect(wrapper.text()).toContain('pid 2972')
  })
})
