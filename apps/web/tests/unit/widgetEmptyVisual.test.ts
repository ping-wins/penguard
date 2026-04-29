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

const uptimeBinding: WidgetFieldBinding = {
  fieldId: 'system.uptimeSeconds',
  label: 'Uptime',
  type: 'duration',
  unit: 'seconds',
  source: 'fortigate-system-status',
  provider: 'fortigate',
  groupId: 'system',
  groupName: 'System Data',
}

const interfacesBinding: WidgetFieldBinding = {
  fieldId: 'interfaces',
  label: 'Interfaces',
  type: 'array',
  source: 'fortigate-network-traffic',
  provider: 'fortigate',
  groupId: 'interfaces',
  groupName: 'Interfaces',
}

const eventsBinding: WidgetFieldBinding = {
  fieldId: 'events',
  label: 'Recent Events',
  type: 'array',
  source: 'fortigate-recent-events',
  provider: 'fortigate',
  groupId: 'events',
  groupName: 'Events',
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

  it('renders FortiGate uptime bindings as a readable duration', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-system-status',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-29T03:40:02.000Z',
      status: 'ready',
      data: { uptimeSeconds: 92420 },
      meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(WidgetEmptyVisual, {
      props: {
        catalogId: 'visual-template-card',
        integrationId: 'int_fgt_01',
        fieldBindings: [uptimeBinding],
      } as any,
    })

    await flushPromises()

    expect(wrapper.get('[data-test="custom-card-value"]').text()).toBe('1d 1h 40m')
    expect(wrapper.text()).toContain('Uptime')
  })

  it('renders a gauge from a bound percentage field without fabricating history', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-system-status',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-29T03:40:02.000Z',
      status: 'ready',
      data: { cpu: 82, memory: 41, sessions: 3812 },
      meta: { source: 'fortigate', cacheTtlSeconds: 2 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(WidgetEmptyVisual, {
      props: {
        catalogId: 'visual-template-gauge',
        integrationId: 'int_fgt_01',
        fieldBindings: [cpuBinding],
      } as any,
    })

    await flushPromises()

    expect(wrapper.get('[data-test="custom-gauge-value"]').text()).toBe('82%')
    expect(wrapper.get('[data-test="custom-gauge-fill"]').attributes('style')).toContain('width: 82%')
    expect(wrapper.text()).toContain('CPU Usage')
    expect(wrapper.text()).not.toContain('Trend')
  })

  it('renders a table with scalar rows and flattened array values', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-network-traffic',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-29T03:40:02.000Z',
      status: 'ready',
      data: {
        interfaces: [
          { name: 'port1', status: 'up' },
          { name: 'wan1', status: 'down' },
        ],
      },
      meta: { source: 'fortigate', cacheTtlSeconds: 2 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(WidgetEmptyVisual, {
      props: {
        catalogId: 'visual-template-table',
        integrationId: 'int_fgt_01',
        fieldBindings: [interfacesBinding, cpuBinding],
      } as any,
    })

    await flushPromises()

    const rows = wrapper.findAll('[data-test="custom-table-row"]')
    expect(rows.length).toBeGreaterThanOrEqual(5)
    expect(wrapper.text()).toContain('Interfaces 1 Name')
    expect(wrapper.text()).toContain('port1')
    expect(wrapper.text()).toContain('Interfaces 2 Status')
    expect(wrapper.text()).toContain('down')
    expect(wrapper.text()).toContain('CPU Usage')
    expect(wrapper.text()).toContain('fortigate-network-traffic')
  })

  it('renders event feed rows from bound array values', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-recent-events',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-29T03:40:02.000Z',
      status: 'ready',
      data: {
        events: [
          { severity: 'high', message: 'Blocked malware callback', sourceIp: '10.0.0.8' },
          { severity: 'info', message: 'VPN login accepted', sourceIp: '10.0.0.12' },
        ],
      },
      meta: { source: 'fortigate', cacheTtlSeconds: 5 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(WidgetEmptyVisual, {
      props: {
        catalogId: 'visual-template-feed',
        integrationId: 'int_fgt_01',
        fieldBindings: [eventsBinding],
      } as any,
    })

    await flushPromises()

    const rows = wrapper.findAll('[data-test="custom-feed-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Blocked malware callback')
    expect(rows[0].text()).toContain('high')
    expect(rows[1].text()).toContain('VPN login accepted')
  })

  it('renders signal list rows with numeric severity accents', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-system-status',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-29T03:40:02.000Z',
      status: 'ready',
      data: { cpu: 91, memory: 43 },
      meta: { source: 'fortigate', cacheTtlSeconds: 2 },
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(WidgetEmptyVisual, {
      props: {
        catalogId: 'visual-template-list',
        integrationId: 'int_fgt_01',
        fieldBindings: [cpuBinding, memoryBinding],
      } as any,
    })

    await flushPromises()

    const rows = wrapper.findAll('[data-test="custom-signal-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].attributes('data-severity')).toBe('critical')
    expect(rows[0].text()).toContain('CPU Usage')
    expect(rows[0].text()).toContain('91%')
    expect(rows[1].attributes('data-severity')).toBe('normal')
  })
})
