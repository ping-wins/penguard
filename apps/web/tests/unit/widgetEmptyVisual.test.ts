import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WidgetEmptyVisual from '../../src/components/widgets/WidgetEmptyVisual.vue'
import type { WidgetFieldBinding } from '../../src/types/dashboard'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const cpuBinding: WidgetFieldBinding = {
  fieldId: 'system.cpu',
  label: 'CPU Usage',
  type: 'number',
  unit: 'percent',
  source: 'fortigate-system-status',
  provider: 'fortigate',
  groupId: 'system',
  groupName: 'System Data',
}

const memoryBinding: WidgetFieldBinding = {
  fieldId: 'system.memory',
  label: 'Memory Usage',
  type: 'number',
  unit: 'percent',
  source: 'fortigate-system-status',
  provider: 'fortigate',
  groupId: 'system',
  groupName: 'System Data',
}

describe('WidgetEmptyVisual', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a bound card from live FortiGate field data', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-system-status',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-29T03:40:02.000Z',
      status: 'ready',
      data: { cpu: 74, memory: 41, sessions: 3812 },
      meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(WidgetEmptyVisual, {
      props: {
        catalogId: 'visual-template-card',
        integrationId: 'int_fgt_01',
        fieldBindings: [cpuBinding],
      } as any,
    })

    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith(
      '/api/widgets/fortigate-system-status/data?integrationId=int_fgt_01',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(wrapper.get('[data-test="custom-card-value"]').text()).toBe('74%')
    expect(wrapper.text()).toContain('CPU Usage')
    expect(wrapper.text()).not.toContain('Drop a live data field here')
  })

  it('renders bound numeric fields as bar chart rows from one shared source request', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-system-status',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-29T03:40:02.000Z',
      status: 'ready',
      data: { cpu: 74, memory: 41, sessions: 3812 },
      meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(WidgetEmptyVisual, {
      props: {
        catalogId: 'visual-template-bar',
        integrationId: 'int_fgt_01',
        fieldBindings: [cpuBinding, memoryBinding],
      } as any,
    })

    await flushPromises()

    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('CPU Usage')
    expect(wrapper.text()).toContain('Memory Usage')
    expect(wrapper.text()).toContain('74%')
    expect(wrapper.text()).toContain('41%')
    expect(wrapper.get('[data-test="custom-bar-system.cpu"]').attributes('style')).toContain('width: 74%')
    expect(wrapper.get('[data-test="custom-bar-system.memory"]').attributes('style')).toContain('width: 41%')
  })
})
