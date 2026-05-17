import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MarketplacePanel from '../../src/components/marketplace/MarketplacePanel.vue'
import { i18n, setLocale } from '../../src/i18n'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('MarketplacePanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('en-US')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders remote catalog summary items without manifest-only fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [
        {
          id: 'fortiweb-core',
          name: 'FortiWeb Core',
          vendor: 'Fortinet',
          category: 'waf',
          icon: 'fortinet',
          description: 'Connect a FortiWeb WAF.',
          latestVersion: '8.0.5',
          versions: ['8.0.5'],
          tagTemplate: 'fortiweb-core-v{version}',
          installed: false,
          installedVersion: null,
        },
      ],
      count: 1,
    })))

    const wrapper = mount(MarketplacePanel, {
      global: {
        plugins: [i18n],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('FortiWeb Core')
    expect(wrapper.text()).toContain('8.0.5')
  })

  it('allows installing newer remote version over an older installed add-on', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [
        {
          id: 'fortiweb-core',
          name: 'FortiWeb Core',
          vendor: 'Fortinet',
          category: 'waf',
          description: 'Connect a FortiWeb WAF.',
          latestVersion: '8.0.5.2',
          versions: ['8.0.5.2', '8.0.5.1', '8.0.5'],
          installed: true,
          installedVersion: '8.0.5',
        },
      ],
      count: 1,
    })))

    const wrapper = mount(MarketplacePanel, {
      global: {
        plugins: [i18n],
      },
    })
    await flushPromises()

    const installButton = wrapper.get('button[data-test="marketplace-install-fortiweb-core"]')
    expect(installButton.attributes('disabled')).toBeUndefined()
  })
})

async function flushPromises() {
  await new Promise(resolve => setTimeout(resolve, 0))
}
