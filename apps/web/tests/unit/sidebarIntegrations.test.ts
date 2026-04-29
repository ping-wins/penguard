import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Sidebar from '../../src/components/layout/Sidebar.vue'
import { useAuthStore } from '../../src/stores/useAuthStore'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Sidebar integrations panel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the connector host below the integration name', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [
        {
          id: 'int_fgt_01',
          type: 'fortigate',
          name: 'FortiGate Lab',
          host: 'https://192.0.2.118',
          status: 'connected',
        },
      ],
    })))

    const wrapper = mount(Sidebar)

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('FortiGate Lab')
    expect(wrapper.text()).toContain('https://192.0.2.118')
    expect(wrapper.text()).toContain('Domain verification')
    expect(wrapper.text()).toContain('DNS TXT pending')
    expect(wrapper.text()).toContain('Audit activity')
    expect(wrapper.text()).toContain('integration.fortigate.created')
  })
})
