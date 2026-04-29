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
    expect(wrapper.text()).not.toContain('Audit activity')
    expect(wrapper.text()).not.toContain('integration.fortigate.created')
  })

  it('opens a real admin audit drawer from the sidebar', async () => {
    const authStore = useAuthStore()
    authStore.isAuthenticated = true
    authStore.user = {
      id: 'usr_admin',
      email: 'admin@example.com',
      displayName: 'SOC Admin',
      roles: ['admin'],
    }
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      items: [
        {
          id: 'audit_01',
          actor: { id: 'usr_01', email: 'analyst@example.com' },
          action: 'login',
          outcome: 'success',
          ipAddress: '192.0.2.10',
          userAgent: 'Vitest',
          details: {},
          createdAt: '2026-04-29T16:00:00.000Z',
        },
      ],
    }))
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(Sidebar)

    await wrapper.get('[title="Audit Trail"]').trigger('click')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith('/api/admin/audit/events?limit=50', {
      credentials: 'include',
    })
    expect(wrapper.text()).toContain('Admin audit trail')
    expect(wrapper.text()).toContain('Global SOC activity')
    expect(wrapper.text()).toContain('Login succeeded')
    expect(wrapper.text()).toContain('analyst@example.com')

    wrapper.unmount()
  })
})
