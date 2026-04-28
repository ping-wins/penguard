import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import DraggableWidget from '../../src/components/canvas/DraggableWidget.vue'
import { useDashboardStore } from '../../src/stores/useDashboardStore'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('DraggableWidget', () => {
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
})
