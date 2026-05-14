import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { h } from 'vue'
import WidgetShell from '../../src/components/widgets/shell/WidgetShell.vue'
import WidgetSparkline from '../../src/components/widgets/shell/WidgetSparkline.vue'
import { useWidgetSeriesStore } from '../../src/stores/useWidgetSeriesStore'
import { extractSeriesSample, SERIES_CAPACITY } from '../../src/lib/widgetSeries'
import { ageMs, formatAge, slaBucket, mttdEstimate, topByCount } from '../../src/composables/useSocMetrics'
import { normalizeSeverity, severityRank } from '../../src/lib/severityTokens'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('useSocMetrics helpers', () => {
  it('ageMs handles bad input and clamps negatives', () => {
    expect(ageMs(null)).toBeNull()
    expect(ageMs('not-a-date')).toBeNull()
    expect(ageMs('2024-01-01T00:00:00Z', new Date('2024-01-01T00:00:30Z').getTime())).toBe(30_000)
    expect(ageMs('2099-01-01T00:00:00Z', new Date('2024-01-01T00:00:00Z').getTime())).toBe(0)
  })

  it('formatAge picks the right unit', () => {
    expect(formatAge(15_000)).toBe('15s')
    expect(formatAge(120_000)).toBe('2m')
    expect(formatAge(3_660_000)).toBe('1h 1m')
    expect(formatAge(90_000_000)).toBe('1d 1h')
    expect(formatAge(null)).toBe('--')
  })

  it('slaBucket thresholds work', () => {
    expect(slaBucket(10 * 60 * 1000)).toBe('green')
    expect(slaBucket(20 * 60 * 1000)).toBe('amber')
    expect(slaBucket(2 * 60 * 60 * 1000)).toBe('red')
  })

  it('mttdEstimate returns delta to first timeline entry', () => {
    const inc = {
      createdAt: '2024-01-01T00:00:00Z',
      timeline: [{ at: '2024-01-01T00:01:30Z', type: 'investigating' }],
    }
    expect(mttdEstimate(inc)).toBe(90_000)
  })

  it('topByCount sorts and limits', () => {
    const out = topByCount([{ r: 'a' }, { r: 'b' }, { r: 'a' }, { r: 'c' }, { r: 'a' }], (i) => i.r, 2)
    expect(out).toEqual([{ key: 'a', count: 3 }, { key: 'b', count: 1 }])
  })
})

describe('severityTokens', () => {
  it('normalizeSeverity collapses synonyms and unknowns', () => {
    expect(normalizeSeverity('CRITICAL')).toBe('critical')
    expect(normalizeSeverity('warn')).toBe('warning')
    expect(normalizeSeverity('online')).toBe('healthy')
    expect(normalizeSeverity(undefined)).toBe('unknown')
    expect(normalizeSeverity('mystery')).toBe('unknown')
  })

  it('severityRank orders consistently', () => {
    expect(severityRank('critical')).toBeGreaterThan(severityRank('high'))
    expect(severityRank('high')).toBeGreaterThan(severityRank('medium'))
    expect(severityRank('medium')).toBeGreaterThan(severityRank('low'))
  })
})

describe('extractSeriesSample', () => {
  it('returns null for unknown widget ids', () => {
    expect(extractSeriesSample('not-a-real-widget', { foo: 1 })).toBeNull()
  })

  it('samples incidents-by-severity payload', () => {
    const sample = extractSeriesSample('soc-incidents-by-severity', {
      total: 7,
      items: [
        { severity: 'critical', count: 3 },
        { severity: 'high', count: 2 },
        { severity: 'low', count: 2 },
      ],
    })
    expect(sample).toEqual({ total: 7, critical: 3, high: 2, medium: 0, low: 2 })
  })

  it('handles missing fields without throwing', () => {
    expect(extractSeriesSample('xdr-endpoint-health', null)).toEqual({ total: 0, unhealthy: 0, healthy: 0 })
    expect(extractSeriesSample('soar-active-playbook-runs', {})).toEqual({ count: 0, running: 0, waitingApproval: 0 })
  })
})

describe('useWidgetSeriesStore', () => {
  it('caps series at SERIES_CAPACITY (FIFO)', () => {
    const store = useWidgetSeriesStore()
    for (let i = 1; i <= SERIES_CAPACITY + 5; i += 1) {
      store.recordSample('inst-1', 'soc-recent-incidents', { count: i, incidents: [] })
    }
    const points = store.getSeries('inst-1', 'count')
    expect(points).toHaveLength(SERIES_CAPACITY)
    expect(points[0]).toBe(6)
    expect(points[points.length - 1]).toBe(SERIES_CAPACITY + 5)
  })

  it('clearInstance removes only that instance', () => {
    const store = useWidgetSeriesStore()
    store.recordSample('inst-a', 'soc-recent-incidents', { count: 1, incidents: [] })
    store.recordSample('inst-b', 'soc-recent-incidents', { count: 2, incidents: [] })
    store.clearInstance('inst-a')
    expect(store.getSeries('inst-a', 'count')).toEqual([])
    expect(store.getSeries('inst-b', 'count')).toEqual([2])
  })

  it('clearAll wipes buffer + sibling data', () => {
    const store = useWidgetSeriesStore()
    store.recordSample('inst-1', 'soc-recent-incidents', { count: 3, incidents: [{ id: 'i1' }] }, 'int-1')
    expect(store.getSiblingData('soc-recent-incidents', 'int-1')).toBeTruthy()
    store.clearAll()
    expect(store.getSeries('inst-1', 'count')).toEqual([])
    expect(store.getSiblingData('soc-recent-incidents', 'int-1')).toBeNull()
  })

  it('records sibling data when integrationId provided', () => {
    const store = useWidgetSeriesStore()
    store.recordSample('inst-1', 'soc-recent-incidents', { count: 1, incidents: [{ id: 'x' }] }, 'int-1')
    const sibling = store.getSiblingData('soc-recent-incidents', 'int-1') as any
    expect(sibling?.incidents?.[0]?.id).toBe('x')
  })
})

describe('WidgetShell drill mode', () => {
  function mountShell(opts: { detail?: boolean, disableDrill?: boolean } = {}) {
    return mount(WidgetShell, {
      props: {
        widgetId: 'test-widget',
        title: 'Test',
        disableDrill: opts.disableDrill ?? false,
      },
      slots: {
        glance: () => h('div', { class: 'glance-slot' }, 'Glance content'),
        drill: () => h('div', { class: 'drill-slot' }, 'Drill content'),
        ...(opts.detail !== false
          ? { detail: () => h('div', { class: 'detail-slot' }, 'Detail content') }
          : {}),
      },
      attachTo: document.body,
    })
  }

  it('renders glance by default and shows drill on click', async () => {
    const wrapper = mountShell()
    expect(wrapper.find('.glance-slot').exists()).toBe(true)
    expect(wrapper.find('.drill-slot').exists()).toBe(false)
    await wrapper.find('[role="button"]').trigger('click')
    expect(wrapper.find('.drill-slot').exists()).toBe(true)
    wrapper.unmount()
  })

  it('disableDrill prevents drill expansion', async () => {
    const wrapper = mountShell({ disableDrill: true })
    expect(wrapper.find('[role="button"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('detail toggle opens modal', async () => {
    const wrapper = mountShell()
    const detailBtn = wrapper.find('button[aria-label="Open detail view"]')
    expect(detailBtn.exists()).toBe(true)
    await detailBtn.trigger('click')
    const teleported = document.querySelector('[role="dialog"]')
    expect(teleported).toBeTruthy()
    wrapper.unmount()
  })
})

describe('WidgetSparkline', () => {
  it('renders dashed placeholder when no points', () => {
    const wrapper = mount(WidgetSparkline, { props: { points: [] } })
    expect(wrapper.find('line').exists()).toBe(true)
    expect(wrapper.find('polyline').exists()).toBe(false)
  })

  it('renders polyline with 2+ points', () => {
    const wrapper = mount(WidgetSparkline, { props: { points: [1, 2, 3, 4] } })
    expect(wrapper.find('polyline').exists()).toBe(true)
  })

  it('renders circle for single point', () => {
    const wrapper = mount(WidgetSparkline, { props: { points: [5] } })
    expect(wrapper.find('circle').exists()).toBe(true)
  })
})
