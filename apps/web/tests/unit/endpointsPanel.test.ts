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
    vi.unstubAllGlobals()
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
      if (url === '/api/weapons/endpoints/win-server-01/related-incidents') {
        return Promise.resolve(jsonResponse({
          endpointId: 'win-server-01',
          items: [
            {
              id: 'inc_endpoint',
              title: 'Suspicious endpoint connection',
              severity: 'high',
              triageLevel: 'T1',
              ticketStatus: 'investigating',
              source: 'kowalski',
              origin: { kind: 'demo.replay' },
              attributes: { demoRunId: 'demo_endpoint_01' },
              entities: { endpointId: 'win-server-01' },
            },
          ],
          total: 1,
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
    expect(wrapper.text()).toContain('Related incidents')
    expect(wrapper.text()).toContain('Suspicious endpoint connection')
    expect(wrapper.text()).toContain('high')
    expect(wrapper.text()).toContain('T1')
    expect(wrapper.text()).toContain('investigating')
    expect(wrapper.text()).toContain('Seeded demo')
    expect(wrapper.text()).toContain('Connection Snapshot')
    expect(wrapper.text()).toContain('1 connection')
    expect(wrapper.text()).toContain('1 process')
    expect(wrapper.text()).toContain('pid 2972')
  })

  it('creates a Windows agent enrollment and shows it as pending before first heartbeat', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/weapons/endpoints') {
        return Promise.resolve(jsonResponse({ items: [] }))
      }
      if (url === '/api/auth/csrf') {
        return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      }
      if (url === '/api/weapons/enrollments') {
        return Promise.resolve(jsonResponse({
          id: 'enr_01',
          displayName: 'Windows Server Lab',
          hostnameHint: 'WIN-LAB-01',
          createdAt: '2026-05-13T18:00:00.000Z',
          token: 'enrollment-token',
        }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('fetch', fetcher)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const wrapper = mount(EndpointsPanel, {
      global: {
        plugins: [i18n],
      },
    })
    await flushPromises()

    await wrapper.find('[data-test="add-windows-agent"]').trigger('click')
    await wrapper.find('input[name="displayName"]').setValue('Windows Server Lab')
    await wrapper.find('input[name="hostnameHint"]').setValue('WIN-LAB-01')
    await wrapper.find('form[data-test="agent-enrollment-form"]').trigger('submit.prevent')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith('/api/auth/csrf', { credentials: 'include' })
    expect(fetcher).toHaveBeenCalledWith('/api/weapons/enrollments', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf_01' }),
    }))
    expect(wrapper.find('[data-test="agent-enrollment-command"]').text()).toContain(
      '$env:AGENT_PRIVATE_ENROLLMENT_TOKEN="enrollment-token"',
    )
    expect(wrapper.find('[data-test="agent-enrollment-command"]').text()).toContain(
      'cd apps\\agent_private',
    )
    expect(wrapper.find('[data-test="copy-agent-command"]').exists()).toBe(true)
    await wrapper.find('[data-test="copy-agent-command"]').trigger('click')
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('enrollment-token'))
    expect(wrapper.find('[data-test="pending-endpoint"]').text()).toContain('Windows Server Lab')
    expect(wrapper.find('[data-test="pending-endpoint"]').text()).toContain('Waiting for first heartbeat')
  })
})
