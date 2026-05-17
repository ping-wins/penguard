import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ConnectWizard from '../../src/components/integrations/ConnectWizard.vue'
import { i18n, setLocale } from '../../src/i18n'

const CATALOG = [
  {
    addonId: 'fortiweb-core',
    name: 'FortiWeb Core',
    vendor: 'Fortinet',
    category: 'waf',
    providerType: 'fortiweb',
    versions: ['8.0.5'],
    authFields: [{ id: 'host', label: 'URL', type: 'url', required: true }],
    capabilities: { logSource: true, playbookTarget: true, managed: true },
  },
]

describe('ConnectWizard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('en-US')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows empty state when no add-ons installed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    }))
    const wrapper = mountWizard()
    await flushPromises()
    expect(wrapper.text()).toContain('Marketplace')
  })

  it('progresses type to version to credentials and renders dynamic fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: CATALOG }),
    }))
    const wrapper = mountWizard()
    await flushPromises()
    await wrapper.get('[data-test="addon-fortiweb-core"]').trigger('click')
    await wrapper.get('[data-test="next"]').trigger('click')
    await wrapper.get('[data-test="next"]').trigger('click')
    expect(wrapper.find('[data-test="auth-host"]').exists()).toBe(true)
  })
})

function mountWizard() {
  return mount(ConnectWizard, {
    global: {
      plugins: [i18n],
      stubs: {
        RouterLink: {
          props: ['to'],
          template: '<a><slot /></a>',
        },
      },
    },
  })
}

async function flushPromises() {
  await new Promise(resolve => setTimeout(resolve, 0))
}
