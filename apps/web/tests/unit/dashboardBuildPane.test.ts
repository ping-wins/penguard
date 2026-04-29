import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DashboardCanvas from '../../src/components/canvas/DashboardCanvas.vue'
import { useDashboardStore } from '../../src/stores/useDashboardStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('DashboardCanvas build pane', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('separates FortiGate presets from empty visuals and loads live provider fields from the API', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/auth/csrf')) {
        return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      }
      if (url.startsWith('/api/integrations')) {
        return Promise.resolve(jsonResponse({
          items: [
            {
              id: 'int_fgt_01',
              type: 'fortigate',
              name: 'FortiGate Lab',
              host: 'https://192.0.2.118',
              status: 'connected',
            },
          ],
        }))
      }
      if (url.startsWith('/api/widget-catalog')) {
        return Promise.resolve(jsonResponse({
          items: [
            {
              id: 'fortigate-system-status',
              title: 'System Status',
              kind: 'kpi',
              source: 'fortigate',
              requiredCapabilities: ['system'],
              defaultSize: { w: 3, h: 2 },
              dataEndpoint: '/api/widgets/fortigate-system-status/data',
            },
          ],
        }))
      }
      if (url.startsWith('/api/providers/fortigate/data-fields')) {
        return Promise.resolve(jsonResponse({
          provider: 'fortigate',
          groups: [
            {
              id: 'system',
              name: 'System Data',
              fields: [
                {
                  id: 'system.cpu',
                  label: 'CPU Usage',
                  type: 'number',
                  unit: 'percent',
                  source: 'fortigate-system-status',
                  recommendedVisuals: ['kpi'],
                },
              ],
            },
          ],
        }))
      }
      if (url.startsWith('/api/workspaces/ws_default')) {
        return Promise.resolve(jsonResponse({
          id: 'ws_default',
          name: 'SOC Overview',
          widgets: [],
        }))
      }
      return Promise.resolve(jsonResponse({}))
    })
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(DashboardCanvas, {
      global: {
        plugins: [pinia],
        directives: { motion: {} },
        stubs: {
          DraggableWidget: { template: '<div />' },
        },
      },
    })

    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith('/api/providers/fortigate/data-fields', {
      credentials: 'include',
    })
    expect(wrapper.text()).toContain('FortiGate presets')
    expect(wrapper.text()).toContain('System Status')
    expect(wrapper.text()).toContain('Criar dados ao seu visual')
    expect(wrapper.text()).toContain('Card')

    await wrapper.get('[data-test="visual-template-visual-template-card"]').trigger('click')
    const dashboardStore = useDashboardStore()
    expect(dashboardStore.activeWidgets).toEqual([
      expect.objectContaining({
        catalogId: 'visual-template-card',
        integrationId: 'int_fgt_01',
      }),
    ])

    await wrapper.get('[data-test="build-tab-data"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Available Fields')
    expect(wrapper.text()).toContain('System Data')
    expect(wrapper.text()).toContain('CPU Usage')
    expect(wrapper.text()).toContain('number')
    expect(wrapper.text()).toContain('Live')

    const dataTransfer = {
      setData: vi.fn(),
      effectAllowed: '',
    }
    await wrapper.get('[data-test="data-field-system.cpu"]').trigger('dragstart', {
      dataTransfer,
    })

    expect(dataTransfer.setData).toHaveBeenCalledWith(
      'application/x-fortidashboard-provider-field',
      expect.stringContaining('"fieldId":"system.cpu"'),
    )
    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', 'system.cpu')
    expect(dataTransfer.effectAllowed).toBe('copy')
  })
})
