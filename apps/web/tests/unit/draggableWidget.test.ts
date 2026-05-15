import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DraggableWidget from '../../src/components/canvas/DraggableWidget.vue'
import { useDashboardStore } from '../../src/stores/useDashboardStore'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners: Record<string, Array<(message: MessageEvent) => void>> = {}
  onmessage: ((message: MessageEvent) => void) | null = null
  url: string

  constructor(url: string) {
    this.url = url
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

  close() {}
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('DraggableWidget', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    FakeEventSource.instances = []
  })

  it('waits for the catalog before fetching persisted widget data', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-kpi-sessions',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-26T23:45:00.000Z',
      status: 'ready',
      data: { sessions: 3812 },
      meta: { source: 'fortigate', cacheTtlSeconds: 30 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = []
    store.isCatalogLoaded = false

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_sessions',
        catalogId: 'fortigate-kpi-sessions',
        integrationId: 'int_fgt_01',
        layout: { x: 0, y: 0, w: 320, h: 200, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, `Sessions: ${widgetData?.sessions ?? ''}`),
      },
    })

    expect(wrapper.text()).toContain('Loading')
    expect(fetcher).not.toHaveBeenCalled()

    store.catalogItems = [{
      id: 'fortigate-kpi-sessions',
      title: 'Active Sessions',
      kind: 'kpi',
      source: 'fortigate',
      requiredCapabilities: ['system'],
      defaultSize: { w: 3, h: 2 },
      dataEndpoint: '/api/widgets/fortigate-kpi-sessions/data',
    }]
    store.isCatalogLoaded = true

    await nextTick()
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith(
      '/api/widgets/fortigate-kpi-sessions/data?integrationId=int_fgt_01',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(wrapper.text()).toContain('Sessions: 3812')
  })

  it('does not start a hidden per-widget polling loop from refresh interval metadata', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn()
      .mockResolvedValue(jsonResponse({
        widgetId: 'fortigate-kpi-sessions',
        integrationId: 'int_fgt_01',
        refreshedAt: '2026-04-26T23:45:00.000Z',
        status: 'ready',
        data: { sessions: 23 },
        meta: { source: 'fortigate', cacheTtlSeconds: 1, refreshIntervalSeconds: 1 },
      }))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = [{
      id: 'fortigate-kpi-sessions',
      title: 'Active Sessions',
      kind: 'kpi',
      source: 'fortigate',
      requiredCapabilities: ['system'],
      defaultSize: { w: 3, h: 2 },
      dataEndpoint: '/api/widgets/fortigate-kpi-sessions/data',
    }]
    store.isCatalogLoaded = true

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_sessions',
        catalogId: 'fortigate-kpi-sessions',
        integrationId: 'int_fgt_01',
        layout: { x: 0, y: 0, w: 320, h: 200, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, `Sessions: ${widgetData?.sessions ?? ''}`),
      },
    })

    await flushPromises()
    expect(wrapper.text()).toContain('Sessions: 23')

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()

    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Sessions: 23')
  })

  it('applies realtime ticket payloads to SIEM incident widgets without refetching', async () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetcher = vi.fn()
      .mockResolvedValue(jsonResponse({
        widgetId: 'soc-recent-incidents',
        integrationId: 'int_kowalski_01',
        refreshedAt: '2026-05-15T12:00:00.000Z',
        status: 'ready',
        data: { incidents: [], count: 0 },
        meta: { source: 'siem_kowalski', cacheTtlSeconds: 5, refreshIntervalSeconds: 5 },
      }))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = [{
      id: 'soc-recent-incidents',
      title: 'Recent Incidents',
      kind: 'feed',
      source: 'siem_kowalski',
      requiredCapabilities: ['incidents'],
      defaultSize: { w: 4, h: 3 },
      dataEndpoint: '/api/widgets/soc-recent-incidents/data',
    }]
    store.isCatalogLoaded = true

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_recent_incidents',
        catalogId: 'soc-recent-incidents',
        integrationId: 'int_kowalski_01',
        layout: { x: 0, y: 0, w: 360, h: 260, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, `Count: ${widgetData?.count ?? ''}`),
      },
    })

    await flushPromises()
    expect(wrapper.text()).toContain('Count: 0')

    FakeEventSource.instances[0].emit('audit.siem.event', {
      type: 'audit.siem.event',
      ticket: {
        id: 'inc_audit_01',
        title: 'Repeated failed FortiDashboard logins',
        severity: 'medium',
        triageLevel: 'T2',
        ticketStatus: 'new',
        createdAt: '2026-05-15T12:05:00.000Z',
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Count: 1')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('applies realtime widget snapshots to FortiGate widgets without refetching', async () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetcher = vi.fn()
      .mockImplementation(() => Promise.resolve(jsonResponse({
        widgetId: 'fortigate-system-status',
        integrationId: 'int_fgt_01',
        refreshedAt: '2026-05-15T12:00:00.000Z',
        status: 'ready',
        data: { cpu: 4, memory: 49, sessions: 12, uptimeSeconds: 25080 },
        meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
      })))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = [{
      id: 'fortigate-system-status',
      title: 'System Status',
      kind: 'health',
      source: 'fortigate',
      requiredCapabilities: ['system'],
      defaultSize: { w: 4, h: 3 },
      dataEndpoint: '/api/widgets/fortigate-system-status/data',
    }]
    store.isCatalogLoaded = true

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_system_status',
        catalogId: 'fortigate-system-status',
        integrationId: 'int_fgt_01',
        layout: { x: 0, y: 0, w: 360, h: 260, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, `CPU: ${widgetData?.cpu ?? ''} Sessions: ${widgetData?.sessions ?? ''}`),
      },
    })

    await flushPromises()
    expect(wrapper.text()).toContain('CPU: 4 Sessions: 12')

    FakeEventSource.instances[0].emit('fortigate.syslog.event', {
      type: 'fortigate.syslog.event',
      integrationId: 'int_fgt_01',
      widgets: [
        {
          widgetId: 'fortigate-system-status',
          integrationId: 'int_fgt_01',
          refreshedAt: '2026-05-15T12:00:05.000Z',
          status: 'ready',
          data: { cpu: 7, memory: 52, sessions: 18, uptimeSeconds: 25085 },
          meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
        },
      ],
    })
    await flushPromises()

    expect(wrapper.text()).toContain('CPU: 7 Sessions: 18')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('hydrates duplicate FortiGate widgets from the latest shared realtime snapshot', async () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetcher = vi.fn()
      .mockImplementation(() => Promise.resolve(jsonResponse({
        widgetId: 'fortigate-system-status',
        integrationId: 'int_fgt_01',
        refreshedAt: '2026-05-15T12:00:00.000Z',
        status: 'ready',
        data: { cpu: 4, memory: 49, sessions: 12, uptimeSeconds: 25080 },
        meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
      })))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = [{
      id: 'fortigate-system-status',
      title: 'System Status',
      kind: 'health',
      source: 'fortigate',
      requiredCapabilities: ['system'],
      defaultSize: { w: 4, h: 3 },
      dataEndpoint: '/api/widgets/fortigate-system-status/data',
    }]
    store.isCatalogLoaded = true

    const first = mount(DraggableWidget, {
      props: {
        instanceId: 'w_system_status_first',
        catalogId: 'fortigate-system-status',
        integrationId: 'int_fgt_01',
        layout: { x: 0, y: 0, w: 360, h: 260, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, `CPU: ${widgetData?.cpu ?? ''} Sessions: ${widgetData?.sessions ?? ''}`),
      },
    })

    await flushPromises()
    expect(first.text()).toContain('CPU: 4 Sessions: 12')

    FakeEventSource.instances[0].emit('fortigate.syslog.event', {
      type: 'fortigate.syslog.event',
      integrationId: 'int_fgt_01',
      widgets: [
        {
          widgetId: 'fortigate-system-status',
          integrationId: 'int_fgt_01',
          refreshedAt: '2026-05-15T12:00:05.000Z',
          status: 'ready',
          data: { cpu: 7, memory: 52, sessions: 18, uptimeSeconds: 25085 },
          meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
        },
      ],
    })
    await flushPromises()
    expect(first.text()).toContain('CPU: 7 Sessions: 18')

    const second = mount(DraggableWidget, {
      props: {
        instanceId: 'w_system_status_second',
        catalogId: 'fortigate-system-status',
        integrationId: 'int_fgt_01',
        layout: { x: 380, y: 0, w: 360, h: 260, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, `CPU: ${widgetData?.cpu ?? ''} Sessions: ${widgetData?.sessions ?? ''}`),
      },
    })

    await flushPromises()

    expect(second.text()).toContain('CPU: 7 Sessions: 18')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('shows a blocking error when an explicit reload fails after rebinding', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        widgetId: 'fortigate-kpi-sessions',
        integrationId: 'int_fgt_01',
        refreshedAt: '2026-04-26T23:45:00.000Z',
        status: 'ready',
        data: { sessions: 23 },
        meta: { source: 'fortigate', cacheTtlSeconds: 1, refreshIntervalSeconds: 1 },
      }))
      .mockResolvedValueOnce(jsonResponse({
        widgetId: 'fortigate-kpi-sessions',
        integrationId: 'int_fgt_02',
        refreshedAt: '2026-04-26T23:45:01.000Z',
        status: 'error',
        data: {},
        meta: {
          source: 'fortigate',
          cacheTtlSeconds: 1,
          refreshIntervalSeconds: 1,
          error: { message: 'FortiGate API request failed with HTTP 404' },
        },
      }))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = [{
      id: 'fortigate-kpi-sessions',
      title: 'Active Sessions',
      kind: 'kpi',
      source: 'fortigate',
      requiredCapabilities: ['system'],
      defaultSize: { w: 3, h: 2 },
      dataEndpoint: '/api/widgets/fortigate-kpi-sessions/data',
    }]
    store.isCatalogLoaded = true

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_sessions',
        catalogId: 'fortigate-kpi-sessions',
        integrationId: 'int_fgt_01',
        layout: { x: 0, y: 0, w: 320, h: 200, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, `Sessions: ${widgetData?.sessions ?? ''}`),
      },
    })

    await flushPromises()
    expect(wrapper.text()).toContain('Sessions: 23')

    await wrapper.setProps({ integrationId: 'int_fgt_02' })
    await flushPromises()

    expect(wrapper.text()).not.toContain('Sessions: 23')
    expect(wrapper.text()).toContain('Widget unavailable')
    expect(wrapper.text()).toContain('FortiGate API request failed with HTTP 404')
  })

  it('shows empty state and last update metadata for ready responses without data', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-firewall-policies',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-26T23:45:00.000Z',
      status: 'ready',
      data: {},
      meta: { source: 'fortigate', cacheTtlSeconds: 15, refreshIntervalSeconds: 15 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = [{
      id: 'fortigate-firewall-policies',
      title: 'Firewall Policies',
      kind: 'table',
      source: 'fortigate',
      requiredCapabilities: ['policies'],
      defaultSize: { w: 5, h: 4 },
      dataEndpoint: '/api/widgets/fortigate-firewall-policies/data',
    }]
    store.isCatalogLoaded = true

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_policies',
        catalogId: 'fortigate-firewall-policies',
        integrationId: 'int_fgt_01',
        layout: { x: 0, y: 0, w: 380, h: 260, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: ({ widgetData }: any) => h('div', { class: 'payload' }, JSON.stringify(widgetData)),
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('No data returned')
    expect(wrapper.html()).toContain('2026-04-26')
  })

  it('lets SOC renderers handle empty ready payloads', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'soc-top-entities',
      integrationId: 'int_siem_01',
      refreshedAt: '2026-05-08T12:00:00.000Z',
      status: 'ready',
      data: { entities: [] },
      meta: { source: 'siem_kowalski', cacheTtlSeconds: 5, refreshIntervalSeconds: 5 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = [{
      id: 'soc-top-entities',
      title: 'Top Entities',
      kind: 'table',
      source: 'siem_kowalski',
      requiredCapabilities: ['incidents'],
      defaultSize: { w: 5, h: 4 },
      dataEndpoint: '/api/widgets/soc-top-entities/data',
    }]
    store.isCatalogLoaded = true

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_entities',
        catalogId: 'soc-top-entities',
        integrationId: 'int_siem_01',
        layout: { x: 0, y: 0, w: 420, h: 280, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: () => h('div', { class: 'renderer-empty-state' }, 'Renderer empty state'),
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Renderer empty state')
    expect(wrapper.text()).not.toContain('The widget endpoint responded successfully')
  })

  it('emits a field drop payload when a provider field is dropped onto a custom visual template', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)

    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = []
    store.isCatalogLoaded = true

    const binding = {
      fieldId: 'system.cpu',
      label: 'CPU Usage',
      type: 'number',
      unit: 'percent',
      source: 'fortigate-system-status',
      provider: 'fortigate',
      groupId: 'system',
      groupName: 'System Data',
    }

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_custom',
        catalogId: 'visual-template-card',
        integrationId: '',
        layout: { x: 0, y: 0, w: 320, h: 200, z: 10 },
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: () => h('div', { class: 'payload' }, 'Empty custom visual'),
      },
    })

    await wrapper.trigger('drop', {
      dataTransfer: {
        getData: (type: string) => (
          type === 'application/x-fortidashboard-provider-field'
            ? JSON.stringify(binding)
            : ''
        ),
        dropEffect: 'copy',
      },
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })

    expect(fetcher).not.toHaveBeenCalled()
    expect(wrapper.emitted('field-drop')).toEqual([
      [{ instanceId: 'w_custom', binding }],
    ])
  })

  it('does not resize a visual template below its minimum readable size', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = []
    store.isCatalogLoaded = true
    store.activeWidgets = [{
      instanceId: 'w_table',
      catalogId: 'visual-template-table',
      integrationId: '',
      layout: { x: 100, y: 120, w: 500, h: 360, z: 10 },
    }]

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_table',
        catalogId: 'visual-template-table',
        integrationId: '',
        layout: store.activeWidgets[0].layout,
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: () => h('div', { class: 'payload' }, 'Custom table'),
      },
    })

    await wrapper.get('[data-test="resize-handle-se"]').trigger('pointerdown', {
      clientX: 0,
      clientY: 0,
    })
    window.dispatchEvent(new MouseEvent('pointermove', {
      clientX: -1000,
      clientY: -1000,
    }))
    window.dispatchEvent(new MouseEvent('pointerup'))

    expect(store.activeWidgets[0].layout.w).toBe(420)
    expect(store.activeWidgets[0].layout.h).toBe(300)
  })

  it('does not resize a visual template above its maximum readable size', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = []
    store.isCatalogLoaded = true
    store.activeWidgets = [{
      instanceId: 'w_table',
      catalogId: 'visual-template-table',
      integrationId: '',
      layout: { x: 100, y: 120, w: 500, h: 360, z: 10 },
    }]

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_table',
        catalogId: 'visual-template-table',
        integrationId: '',
        layout: store.activeWidgets[0].layout,
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: () => h('div', { class: 'payload' }, 'Custom table'),
      },
    })

    await wrapper.get('[data-test="resize-handle-se"]').trigger('pointerdown', {
      clientX: 0,
      clientY: 0,
    })
    window.dispatchEvent(new MouseEvent('pointermove', {
      clientX: 2000,
      clientY: 2000,
    }))
    window.dispatchEvent(new MouseEvent('pointerup'))

    expect(store.activeWidgets[0].layout.w).toBe(960)
    expect(store.activeWidgets[0].layout.h).toBe(720)
  })

  it('allows dragging widgets into negative workspace coordinates', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDashboardStore()
    store.catalogItems = []
    store.isCatalogLoaded = true
    store.activeWidgets = [{
      instanceId: 'w_card',
      catalogId: 'visual-template-card',
      integrationId: '',
      layout: { x: 10, y: 15, w: 320, h: 200, z: 10 },
    }]

    const wrapper = mount(DraggableWidget, {
      props: {
        instanceId: 'w_card',
        catalogId: 'visual-template-card',
        integrationId: '',
        layout: store.activeWidgets[0].layout,
      },
      global: {
        plugins: [pinia],
        directives: { motion: {} },
      },
      slots: {
        default: () => h('div', { class: 'payload' }, 'Custom card'),
      },
    })

    await wrapper.get('[data-test="widget-drag-handle"]').trigger('pointerdown', {
      clientX: 100,
      clientY: 100,
    })
    window.dispatchEvent(new MouseEvent('pointermove', {
      clientX: 20,
      clientY: 30,
    }))
    window.dispatchEvent(new MouseEvent('pointerup'))

    expect(store.activeWidgets[0].layout.x).toBe(-70)
    expect(store.activeWidgets[0].layout.y).toBe(-55)
  })
})
