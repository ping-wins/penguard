import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DashboardCanvas from '../../src/components/canvas/DashboardCanvas.vue'
import { useDashboardStore } from '../../src/stores/useDashboardStore'
import { useIntegrationsStore } from '../../src/stores/useIntegrationsStore'

const WORKSPACE_TEST_ORIGIN = 100000

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
    expect(wrapper.text()).toContain('Visual analysis')
    expect(wrapper.text()).toContain('1 preset ready')
    expect(wrapper.text()).toContain('Template binding: Data fields')
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

    expect(wrapper.text()).toContain('FortiGate data model')
    expect(wrapper.text()).toContain('1 field available')
    expect(wrapper.text()).toContain('Fields available for empty visual templates')
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

  it('shows loading and empty states for FortiGate visual presets', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))

    const dashboardStore = useDashboardStore()
    dashboardStore.catalogItems = []
    dashboardStore.isCatalogLoaded = false
    const integrationsStore = useIntegrationsStore()
    integrationsStore.integrations = [
      {
        id: 'int_fgt_01',
        type: 'fortigate',
        name: 'FortiGate Lab',
        status: 'connected',
      },
    ]

    const wrapper = mount(DashboardCanvas, {
      global: {
        plugins: [pinia],
        directives: { motion: {} },
        stubs: {
          DraggableWidget: { template: '<div />' },
        },
      },
    })

    expect(wrapper.text()).toContain('Loading FortiGate presets')

    dashboardStore.isCatalogLoaded = true
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('No FortiGate presets available')
    expect(wrapper.text()).toContain('Catalog status: unavailable; visual templates remain available')
  })

  it('shows a provider data retry affordance when field loading fails', async () => {
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
              status: 'connected',
            },
          ],
        }))
      }
      if (url.startsWith('/api/widget-catalog')) {
        return Promise.resolve(jsonResponse({ items: [] }))
      }
      if (url.startsWith('/api/providers/fortigate/data-fields')) {
        return Promise.resolve(jsonResponse({ detail: 'Provider data unavailable' }, { status: 503 }))
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
    await wrapper.get('[data-test="build-tab-data"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Data model unavailable')
    expect(wrapper.text()).toContain('Provider data unavailable')
    expect(wrapper.text()).toContain('Retry fields')
  })

  it('keeps a stable dot canvas background while zooming and panning', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/auth/csrf')) return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url.startsWith('/api/integrations')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/widget-catalog')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/workspaces/ws_default')) {
        return Promise.resolve(jsonResponse({ id: 'ws_default', name: 'SOC Overview', widgets: [] }))
      }
      return Promise.resolve(jsonResponse({}))
    }))

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

    const store = useDashboardStore()
    const viewport = wrapper.get('[data-test="workspace-viewport"]')
    const grid = wrapper.get('[data-test="workspace-grid"]')
    const viewportElement = viewport.element as HTMLElement

    const dotStyle = viewport.attributes('style') ?? ''
    expect(dotStyle).toContain('radial-gradient')
    expect(dotStyle).toContain('background-size: 24px 24px')
    expect(dotStyle).not.toContain('linear-gradient')
    expect(dotStyle).not.toContain('background-position')

    viewportElement.scrollLeft = 240
    viewportElement.scrollTop = 160
    await viewport.trigger('scroll')

    expect(viewport.attributes('style')).toBe(dotStyle)
    expect(grid.attributes('style') ?? '').not.toContain('radial-gradient')

    await viewport.trigger('wheel', {
      ctrlKey: true,
      deltaY: -240,
      clientX: 300,
      clientY: 180,
    })

    expect(store.zoom).toBeGreaterThan(1)
    expect(viewport.attributes('style')).toBe(dotStyle)
    expect(wrapper.get('[data-test="workspace-stage"]').attributes('style')).toContain('scale(')
  })

  it('supports Power BI style wheel and space-drag workspace panning', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/auth/csrf')) return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url.startsWith('/api/integrations')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/widget-catalog')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/workspaces/ws_default')) {
        return Promise.resolve(jsonResponse({ id: 'ws_default', name: 'SOC Overview', widgets: [] }))
      }
      return Promise.resolve(jsonResponse({}))
    }))

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

    const viewportWrapper = wrapper.get('[data-test="workspace-viewport"]')
    const viewport = viewportWrapper.element as HTMLElement
    viewport.scrollLeft = 100
    viewport.scrollTop = 200

    await viewportWrapper.trigger('wheel', {
      shiftKey: true,
      deltaY: 80,
      deltaX: 0,
    })
    expect(viewport.scrollLeft).toBe(180)
    expect(viewport.scrollTop).toBe(200)

    await viewportWrapper.trigger('wheel', {
      deltaY: 60,
      deltaX: 0,
    })
    expect(viewport.scrollTop).toBe(260)

    await viewportWrapper.trigger('keydown', { code: 'Space', key: ' ' })
    await viewportWrapper.trigger('pointerdown', {
      clientX: 300,
      clientY: 200,
    })
    window.dispatchEvent(new MouseEvent('pointermove', {
      clientX: 260,
      clientY: 170,
    }))
    window.dispatchEvent(new MouseEvent('pointerup'))

    expect(viewport.scrollLeft).toBe(220)
    expect(viewport.scrollTop).toBe(290)
  })

  it('uses space-drag to pan when the pointer starts over a widget', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/auth/csrf')) return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url.startsWith('/api/integrations')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/widget-catalog')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/workspaces/ws_default')) {
        return Promise.resolve(jsonResponse({
          id: 'ws_default',
          name: 'SOC Overview',
          widgets: [{
            instanceId: 'w_01',
            catalogId: 'visual-template-card',
            integrationId: '',
            layout: { x: 0, y: 0, w: 3, h: 2, z: 10 },
          }],
        }))
      }
      return Promise.resolve(jsonResponse({}))
    }))

    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(DashboardCanvas, {
      global: {
        plugins: [pinia],
        directives: { motion: {} },
        stubs: {
          DraggableWidget: {
            template: '<div data-workspace-widget="true" data-test="stub-widget">Widget text</div>',
            props: ['instanceId', 'catalogId', 'integrationId', 'layout', 'fieldBindings'],
          },
        },
      },
    })
    await flushPromises()

    const viewportWrapper = wrapper.get('[data-test="workspace-viewport"]')
    const viewport = viewportWrapper.element as HTMLElement
    viewport.scrollLeft = 500
    viewport.scrollTop = 600

    await viewportWrapper.trigger('keydown', { code: 'Space', key: ' ' })
    await wrapper.get('[data-test="stub-widget"]').trigger('pointerdown', {
      clientX: 300,
      clientY: 200,
    })
    window.dispatchEvent(new MouseEvent('pointermove', {
      clientX: 260,
      clientY: 170,
    }))
    window.dispatchEvent(new MouseEvent('pointerup'))

    expect(viewport.scrollLeft).toBe(540)
    expect(viewport.scrollTop).toBe(630)
  })

  it('adds a FortiGate preset by dragging it from Visuals onto the workspace', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/auth/csrf')) return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url.startsWith('/api/integrations')) {
        return Promise.resolve(jsonResponse({
          items: [{
            id: 'int_fgt_01',
            type: 'fortigate',
            name: 'FortiGate Lab',
            status: 'connected',
          }],
        }))
      }
      if (url.startsWith('/api/widget-catalog')) {
        return Promise.resolve(jsonResponse({
          items: [{
            id: 'fortigate-system-status',
            title: 'System Status',
            kind: 'kpi',
            source: 'fortigate',
            requiredCapabilities: ['system'],
            defaultSize: { w: 3, h: 2 },
            dataEndpoint: '/api/widgets/fortigate-system-status/data',
          }],
        }))
      }
      if (url.startsWith('/api/providers/fortigate/data-fields')) {
        return Promise.resolve(jsonResponse({ provider: 'fortigate', groups: [] }))
      }
      if (url.startsWith('/api/workspaces/ws_default')) {
        return Promise.resolve(jsonResponse({ id: 'ws_default', name: 'SOC Overview', widgets: [] }))
      }
      return Promise.resolve(jsonResponse({}))
    }))

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

    const store = useDashboardStore()
    store.setZoom(2)
    const viewportWrapper = wrapper.get('[data-test="workspace-viewport"]')
    const viewport = viewportWrapper.element as HTMLElement
    viewport.scrollLeft = WORKSPACE_TEST_ORIGIN * 2 + 200
    viewport.scrollTop = WORKSPACE_TEST_ORIGIN * 2 + 120

    const dragPayload: Record<string, string> = {}
    const dataTransfer = {
      setData: vi.fn((type: string, value: string) => {
        dragPayload[type] = value
      }),
      getData: vi.fn((type: string) => dragPayload[type] ?? ''),
      effectAllowed: '',
      dropEffect: '',
    }

    await wrapper.get('[data-test="catalog-widget-fortigate-system-status"]').trigger('dragstart', {
      dataTransfer,
    })
    await viewportWrapper.trigger('drop', {
      dataTransfer,
      clientX: 300,
      clientY: 220,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })

    expect(store.activeWidgets).toHaveLength(1)
    expect(store.activeWidgets[0]).toEqual(expect.objectContaining({
      catalogId: 'fortigate-system-status',
      integrationId: 'int_fgt_01',
    }))
    expect(store.activeWidgets[0].layout).toEqual(expect.objectContaining({
      x: 250,
      y: 170,
      w: 320,
      h: 200,
    }))
  })

  it('adds an empty visual template by dragging it from Visuals onto the workspace', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/auth/csrf')) return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url.startsWith('/api/integrations')) {
        return Promise.resolve(jsonResponse({
          items: [{
            id: 'int_fgt_01',
            type: 'fortigate',
            name: 'FortiGate Lab',
            status: 'connected',
          }],
        }))
      }
      if (url.startsWith('/api/widget-catalog')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/providers/fortigate/data-fields')) {
        return Promise.resolve(jsonResponse({ provider: 'fortigate', groups: [] }))
      }
      if (url.startsWith('/api/workspaces/ws_default')) {
        return Promise.resolve(jsonResponse({ id: 'ws_default', name: 'SOC Overview', widgets: [] }))
      }
      return Promise.resolve(jsonResponse({}))
    }))

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

    const dragPayload: Record<string, string> = {}
    const dataTransfer = {
      setData: vi.fn((type: string, value: string) => {
        dragPayload[type] = value
      }),
      getData: vi.fn((type: string) => dragPayload[type] ?? ''),
      effectAllowed: '',
      dropEffect: '',
    }

    await wrapper.get('[data-test="visual-template-visual-template-card"]').trigger('dragstart', {
      dataTransfer,
    })
    const viewport = wrapper.get('[data-test="workspace-viewport"]').element as HTMLElement
    viewport.scrollLeft = WORKSPACE_TEST_ORIGIN
    viewport.scrollTop = WORKSPACE_TEST_ORIGIN
    await wrapper.get('[data-test="workspace-viewport"]').trigger('drop', {
      dataTransfer,
      clientX: 140,
      clientY: 90,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })

    const store = useDashboardStore()
    expect(store.activeWidgets).toHaveLength(1)
    expect(store.activeWidgets[0]).toEqual(expect.objectContaining({
      catalogId: 'visual-template-card',
      integrationId: 'int_fgt_01',
    }))
    expect(store.activeWidgets[0].layout).toEqual(expect.objectContaining({
      x: 140,
      y: 90,
      w: 320,
      h: 200,
    }))
  })

  it('renders a minimap with widget markers and the current viewport', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.startsWith('/api/auth/csrf')) return Promise.resolve(jsonResponse({ csrfToken: 'csrf_01' }))
      if (url.startsWith('/api/integrations')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/widget-catalog')) return Promise.resolve(jsonResponse({ items: [] }))
      if (url.startsWith('/api/workspaces/ws_default')) {
        return Promise.resolve(jsonResponse({
          id: 'ws_default',
          name: 'SOC Overview',
          widgets: [{
            instanceId: 'w_01',
            catalogId: 'visual-template-card',
            integrationId: '',
            layout: { x: -240, y: 160, w: 3, h: 2, z: 10 },
          }],
        }))
      }
      return Promise.resolve(jsonResponse({}))
    }))

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

    expect(wrapper.get('[data-test="workspace-minimap"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="workspace-viewport"]').find('[data-test="workspace-minimap"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="minimap-viewport"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="minimap-widget-w_01"]').exists()).toBe(true)
  })
})
