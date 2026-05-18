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

  it('shows per-destination wiring results after connect', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      calls.push(url)
      if (url.endsWith('/catalog')) {
        return Promise.resolve({ ok: true, json: async () => ({ items: CATALOG }) })
      }
      if (url.endsWith('/auth/csrf')) {
        return Promise.resolve({ ok: true, json: async () => ({ csrfToken: 'csrf-test' }) })
      }
      if (url.endsWith('/connect/test')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ ok: true, device: { hostname: 'FWB' } }),
        })
      }
      if (url.endsWith('/connect')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            integration: {
              id: 'int_fweb_1',
              telemetry: {
                status: 'pending',
                endpointPath: '/api/soc/ingest/fortiweb/int_fweb_1',
                token: 'fweb_native_token',
                lastEventAt: null,
                lastError: null,
                eventsReceived: 0,
              },
            },
            wiring: {
              siem: { ok: true, detail: 'Managed source registered' },
              soar: { ok: false, detail: 'no actions' },
            },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({ items: [] }) })
    }))

    const wrapper = mountWizard()
    await flushPromises()
    await wrapper.get('[data-test="addon-fortiweb-core"]').trigger('click')
    await wrapper.get('[data-test="next"]').trigger('click')
    await wrapper.get('[data-test="next"]').trigger('click')
    await wrapper.get('[data-test="auth-host"]').setValue('https://x')
    await wrapper.get('[data-test="test"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="finish"]').trigger('click')
    await flushPromises()

    expect(calls.some(url => url.endsWith('/connect'))).toBe(true)
    expect(wrapper.get('[data-test="telemetry-token"]').text()).toContain('fweb_native_token')
    expect(wrapper.get('[data-test="wiring-siem"]').text()).toContain('Managed source registered')
    expect(wrapper.get('[data-test="wiring-soar"]').text()).toContain('no actions')
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
