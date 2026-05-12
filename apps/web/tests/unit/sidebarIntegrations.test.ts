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

  it('shows Penguin tool connector cards with connected state', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [
        {
          id: 'int_kowalski_01',
          type: 'siem_kowalski',
          name: 'Kowalski SIEM',
          status: 'connected',
          capabilities: ['events', 'incidents'],
        },
      ],
    })))

    const wrapper = mount(Sidebar)

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Penguin SOC Lite')
    expect(wrapper.text()).toContain('Kowalski SIEM-lite')
    expect(wrapper.text()).toContain('XDR/EDR-lite manager')
    expect(wrapper.text()).toContain('SOAR-lite workflows')
    expect(wrapper.text()).toContain('Connected as Kowalski SIEM')
    expect(wrapper.get('[data-test="penguin-connect-siem_kowalski"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="penguin-connect-xdr_rico"]').attributes('disabled')).toBeUndefined()
  })

  it('groups integration connectors by provider category', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [],
    })))

    const wrapper = mount(Sidebar)

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Fortinet Providers')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Adicionar FortiGate')
    expect(wrapper.get('[data-test="integration-group-penguin"]').text()).toContain('Penguin SOC Lite')
    expect(wrapper.get('[data-test="integration-group-penguin"]').text()).toContain('Kowalski SIEM-lite')
    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).toContain('Endpoint Sensor / Future')
    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).not.toContain('agent_private')
    expect(wrapper.get('[data-test="integration-toggle-endpoint"]').attributes('aria-expanded')).toBe('false')

    await wrapper.get('[data-test="integration-toggle-endpoint"]').trigger('click')

    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).toContain('agent_private')
    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).toContain('Future onboarding')
    expect(wrapper.find('[data-test="penguin-connect-agent_private"]').exists()).toBe(false)
  })

  it('collapses and expands integration groups from their headers', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [],
    })))

    const wrapper = mount(Sidebar)

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="integration-toggle-fortinet"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Adicionar FortiGate')

    await wrapper.get('[data-test="integration-toggle-fortinet"]').trigger('click')

    expect(wrapper.get('[data-test="integration-toggle-fortinet"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).not.toContain('Adicionar FortiGate')

    await wrapper.get('[data-test="integration-toggle-fortinet"]').trigger('click')

    expect(wrapper.get('[data-test="integration-toggle-fortinet"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Adicionar FortiGate')
  })
})
