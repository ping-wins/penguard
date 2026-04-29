import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DraggableWidget from '../../src/components/canvas/DraggableWidget.vue'
import { useDashboardStore } from '../../src/stores/useDashboardStore'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('DraggableWidget', () => {
  afterEach(() => {
    vi.useRealTimers()
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

  it('refreshes widget data using the backend refresh interval', async () => {
    vi.useFakeTimers()
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
        integrationId: 'int_fgt_01',
        refreshedAt: '2026-04-26T23:45:01.000Z',
        status: 'ready',
        data: { sessions: 28 },
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

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Sessions: 28')
  })

  it('keeps the last good payload visible when a background refresh fails', async () => {
    vi.useFakeTimers()
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
        integrationId: 'int_fgt_01',
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

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(wrapper.text()).toContain('Sessions: 23')
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
    expect(wrapper.text()).toContain('Updated')
    expect(wrapper.text()).toContain('2026-04-26')
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
})
