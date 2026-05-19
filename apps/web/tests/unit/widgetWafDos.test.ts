import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import WidgetWafDosRate from '../../src/components/widgets/waf/WidgetWafDosRate.vue'
import WidgetWafDosTopIps from '../../src/components/widgets/waf/WidgetWafDosTopIps.vue'
import WidgetWafDosFeed from '../../src/components/widgets/waf/WidgetWafDosFeed.vue'
import { i18n, setLocale } from '../../src/i18n'
import { extractSeriesSample } from '../../src/lib/widgetSeries'

beforeEach(() => {
  setActivePinia(createPinia())
  setLocale('en-US')
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEFAULT_PROPS = {
  instanceId: 'w_test_01',
  integrationId: 'int_waf_01',
  catalogId: 'waf-dos-rate',
}

function makeBuckets(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    ts: new Date(Date.now() - i * 60_000).toISOString(),
    blocked: 10 + i,
    allowed: i > 2 ? 1 : 0,
  }))
}

const TOP_IPS_ROWS = [
  { ip: '10.10.10.10', count: 500, lastSeen: new Date().toISOString(), blocked: true },
  { ip: '10.10.10.20', count: 100, lastSeen: new Date().toISOString(), blocked: false },
]

const FEED_ITEMS = [
  { id: 'evt_1', ts: new Date().toISOString(), sourceIp: '10.10.10.10', action: 'block', severity: 'critical', message: 'HTTP flood detected', policy: 'lab-dos' },
  { id: 'evt_2', ts: new Date().toISOString(), sourceIp: '10.10.10.10', action: 'block', severity: 'high', message: 'SYN flood detected', policy: '' },
]

// ---------------------------------------------------------------------------
// WidgetWafDosRate
// ---------------------------------------------------------------------------

describe('WidgetWafDosRate', () => {
  it('renders without error when buckets is empty', () => {
    const wrapper = mount(WidgetWafDosRate, {
      props: { ...DEFAULT_PROPS, data: { buckets: [], source: 'siem' } },
    })
    expect(wrapper.exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows source label in glance', () => {
    const wrapper = mount(WidgetWafDosRate, {
      props: { ...DEFAULT_PROPS, data: { buckets: [], source: 'raw' } },
    })
    expect(wrapper.text()).toContain('raw')
    wrapper.unmount()
  })

  it('renders bar elements when buckets provided', () => {
    const wrapper = mount(WidgetWafDosRate, {
      props: { ...DEFAULT_PROPS, data: { buckets: makeBuckets(5), source: 'siem' } },
    })
    // Each bar div has a title attribute containing "Blocked:"
    const barEl = wrapper.find('[title*="Blocked:"]')
    expect(barEl.exists()).toBe(true)
    wrapper.unmount()
  })

  it('window tabs are rendered', () => {
    const wrapper = mount(WidgetWafDosRate, {
      props: { ...DEFAULT_PROPS, data: { buckets: [], source: 'siem' } },
    })
    const text = wrapper.text()
    expect(text).toContain('15m')
    expect(text).toContain('24h')
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// WidgetWafDosTopIps
// ---------------------------------------------------------------------------

describe('WidgetWafDosTopIps', () => {
  it('renders rows in glance', () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      props: { ...DEFAULT_PROPS, data: { rows: TOP_IPS_ROWS } },
    })
    const text = wrapper.text()
    expect(text).toContain('10.10.10.10')
    expect(text).toContain('10.10.10.20')
    wrapper.unmount()
  })

  it('blocked IP has text-red-400 class', () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      props: { ...DEFAULT_PROPS, data: { rows: TOP_IPS_ROWS } },
    })
    const redEl = wrapper.find('.text-red-400')
    expect(redEl.exists()).toBe(true)
    expect(redEl.text()).toContain('10.10.10.10')
    wrapper.unmount()
  })

  it('Blocked badge rendered for blocked row', async () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      props: { ...DEFAULT_PROPS, data: { rows: TOP_IPS_ROWS } },
      attachTo: document.body,
    })
    // Open the detail modal via the maximize button
    const detailBtn = wrapper.find('button[aria-label="Open detail view"]')
    expect(detailBtn.exists()).toBe(true)
    await detailBtn.trigger('click')
    expect(document.body.textContent).toContain('Blocked')
    wrapper.unmount()
  })

  it('Allowed badge rendered for non-blocked row', async () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      props: { ...DEFAULT_PROPS, data: { rows: TOP_IPS_ROWS } },
      attachTo: document.body,
    })
    const detailBtn = wrapper.find('button[aria-label="Open detail view"]')
    expect(detailBtn.exists()).toBe(true)
    await detailBtn.trigger('click')
    expect(document.body.textContent).toContain('Allowed')
    wrapper.unmount()
  })

  it('empty state when no rows', () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      props: { ...DEFAULT_PROPS, data: { rows: [] } },
    })
    expect(wrapper.text()).toContain('No attacking IPs')
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// WidgetWafDosFeed
// ---------------------------------------------------------------------------

describe('WidgetWafDosFeed', () => {
  it('renders event messages', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: {
        plugins: [i18n],
      },
      props: { ...DEFAULT_PROPS, data: { items: FEED_ITEMS } },
    })
    const text = wrapper.text()
    expect(text).toContain('HTTP flood detected')
    expect(text).toContain('SYN flood detected')
    wrapper.unmount()
  })

  it('critical badge has bg-red-500/20 class', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: {
        plugins: [i18n],
      },
      props: { ...DEFAULT_PROPS, data: { items: FEED_ITEMS } },
    })
    // Use querySelector with escaped slash for Tailwind class bg-red-500/20
    const el = wrapper.element.querySelector('.bg-red-500\\/20')
    expect(el).not.toBeNull()
    wrapper.unmount()
  })

  it('high badge has bg-orange-500/20 class', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: {
        plugins: [i18n],
      },
      props: { ...DEFAULT_PROPS, data: { items: FEED_ITEMS } },
    })
    const el = wrapper.element.querySelector('.bg-orange-500\\/20')
    expect(el).not.toBeNull()
    wrapper.unmount()
  })

  it('medium badge has bg-amber-500/20 class', () => {
    const mediumItem = {
      id: 'evt_3',
      ts: new Date().toISOString(),
      sourceIp: '10.10.10.30',
      action: 'block',
      severity: 'medium',
      message: 'Rate limit exceeded',
      policy: '',
    }
    const wrapper = mount(WidgetWafDosFeed, {
      global: {
        plugins: [i18n],
      },
      props: { ...DEFAULT_PROPS, data: { items: [mediumItem] } },
    })
    const el = wrapper.element.querySelector('.bg-amber-500\\/20')
    expect(el).not.toBeNull()
    wrapper.unmount()
  })

  it('empty state when no items', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: {
        plugins: [i18n],
      },
      props: { ...DEFAULT_PROPS, data: { items: [] } },
    })
    expect(wrapper.text()).toContain('No DoS events')
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// widgetSeries samplers
// ---------------------------------------------------------------------------

describe('widgetSeries samplers', () => {
  it('waf-dos-rate sampler aggregates blocked/allowed', () => {
    const result = extractSeriesSample('waf-dos-rate', {
      buckets: [
        { ts: new Date().toISOString(), blocked: 5, allowed: 2 },
        { ts: new Date().toISOString(), blocked: 3, allowed: 0 },
      ],
    })
    expect(result).toEqual({ blocked: 8, allowed: 2, total: 10 })
  })

  it('waf-dos-feed sampler counts items', () => {
    const result = extractSeriesSample('waf-dos-feed', {
      items: [{ id: '1' }, { id: '2' }, { id: '3' }],
    })
    expect(result).toEqual({ events: 3 })
  })
})
