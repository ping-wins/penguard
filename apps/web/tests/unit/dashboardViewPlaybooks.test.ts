import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DashboardView from '../../src/views/DashboardView.vue'
import { i18n, setLocale } from '../../src/i18n'
import { useAuthStore } from '../../src/stores/useAuthStore'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

describe('DashboardView playbooks surface', () => {
  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    setLocale('en-US')
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    })
    const authStore = useAuthStore()
    authStore.isAuthenticated = true
    authStore.csrfToken = 'csrf_01'
    authStore.user = {
      id: 'usr_admin',
      email: 'admin@example.com',
      displayName: 'SOC Admin',
      roles: ['admin'],
      isAdmin: true,
      permissions: ['*'],
    }
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses SOAR Playbooks as a main surface instead of opening a drawer widget area', async () => {
    const wrapper = mount(DashboardView, {
      global: {
        plugins: [i18n],
        stubs: {
          DashboardCanvas: { template: '<main data-test="workspace-canvas">Workspace</main>' },
          PlaybookBuilderSurface: { template: '<main data-test="playbook-builder-main-surface">Builder</main>' },
          PlaybooksPanel: { template: '<aside data-test="legacy-playbooks-drawer">Legacy drawer</aside>' },
          ThemeBuilderModal: { template: '<div />' },
          SettingsModal: { template: '<div />' },
          IncidentToastContainer: { template: '<div />' },
        },
      },
    })

    expect(wrapper.get('[data-test="workspace-canvas"]').exists()).toBe(true)

    await wrapper.get('[title="SOAR Playbooks"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="workspace-canvas"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="playbook-builder-main-surface"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="legacy-playbooks-drawer"]').exists()).toBe(false)

    await wrapper.get('[title="Dashboard"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="workspace-canvas"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="playbook-builder-main-surface"]').exists()).toBe(false)
  })
})
