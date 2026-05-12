import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useDashboardStore } from '../../src/stores/useDashboardStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useDashboardStore custom visual bindings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('binds a provider data field to a custom visual template without duplicating fields', () => {
    const store = useDashboardStore()
    store.addVisualTemplate('visual-template-card')
    const instanceId = store.activeWidgets[0].instanceId

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

    store.bindFieldToWidget(instanceId, binding)
    store.bindFieldToWidget(instanceId, binding)

    expect(store.activeWidgets[0].fieldBindings).toEqual([binding])
  })

  it('loads widget catalogs for connected integration types and deduplicates item ids', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('integrationType=fortigate')) {
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
            {
              id: 'shared-health',
              title: 'Provider Health',
              kind: 'kpi',
              source: 'fortigate',
              requiredCapabilities: [],
              defaultSize: { w: 3, h: 2 },
              dataEndpoint: '/api/widgets/shared-health/data',
            },
          ],
        }))
      }

      return Promise.resolve(jsonResponse({
        items: [
          {
            id: 'kowalski-open-incidents',
            title: 'Open Incidents',
            kind: 'kpi',
            source: 'siem_kowalski',
            requiredCapabilities: ['incidents'],
            defaultSize: { w: 3, h: 2 },
            dataEndpoint: '/api/widgets/kowalski-open-incidents/data',
          },
          {
            id: 'shared-health',
            title: 'Duplicate Health',
            kind: 'kpi',
            source: 'siem_kowalski',
            requiredCapabilities: [],
            defaultSize: { w: 3, h: 2 },
            dataEndpoint: '/api/widgets/shared-health/data',
          },
        ],
      }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = useDashboardStore()
    await store.fetchCatalog(['fortigate', 'siem_kowalski', 'fortigate'])

    expect(fetcher).toHaveBeenCalledWith('/api/widget-catalog?integrationType=fortigate', {
      credentials: 'include',
    })
    expect(fetcher).toHaveBeenCalledWith('/api/widget-catalog?integrationType=siem_kowalski', {
      credentials: 'include',
    })
    expect(store.catalogItems.map(item => item.id)).toEqual([
      'fortigate-system-status',
      'shared-health',
      'kowalski-open-incidents',
    ])
    expect(store.catalogItems.find(item => item.id === 'kowalski-open-incidents')).toMatchObject({
      source: 'siem_kowalski',
      integrationType: 'siem_kowalski',
    })
  })
})
