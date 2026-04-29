import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useDashboardStore } from '../../src/stores/useDashboardStore'

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
})
