import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Sidebar from '../../src/components/layout/Sidebar.vue'
import { i18n, setLocale } from '../../src/i18n'
import { useAuthStore } from '../../src/stores/useAuthStore'
import { useDashboardStore } from '../../src/stores/useDashboardStore'
import { useIntegrationsStore } from '../../src/stores/useIntegrationsStore'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

let pinia: ReturnType<typeof createPinia>

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Sidebar integrations panel', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    })
    setLocale('pt-BR')
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

    const wrapper = mountSidebar()

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('FortiGate Lab')
    expect(wrapper.text()).toContain('https://192.0.2.118')
    expect(wrapper.text()).not.toContain('Audit activity')
    expect(wrapper.text()).not.toContain('integration.fortigate.created')
  })

  it('shows FortiGate ingestion status and can trigger a run now', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/integrations') {
        return Promise.resolve(jsonResponse({
          items: [
            {
              id: 'int_fgt_01',
              type: 'fortigate',
              name: 'FortiGate Lab',
              host: 'https://192.0.2.118',
              status: 'connected',
            },
          ],
        }))
      }
      if (url.endsWith('/ingestion-status')) {
        return Promise.resolve(jsonResponse({
          integrationId: 'int_fgt_01',
          enabled: true,
          intervalSeconds: 30,
          status: 'idle',
          lastStartedAt: null,
          lastFinishedAt: null,
          lastSuccessAt: null,
          lastError: null,
          lastRawEventCount: 0,
          lastCreatedCount: 0,
          lastEventIds: [],
          lastRunTrigger: null,
          updatedAt: '2026-05-13T18:00:00.000Z',
        }))
      }
      if (url.endsWith('/ingest-events')) {
        expect(init?.method).toBe('POST')
        return Promise.resolve(jsonResponse({
          integrationId: 'int_fgt_01',
          rawEventCount: 4,
          createdCount: 1,
          eventIds: ['evt_01'],
          ingestion: {
            integrationId: 'int_fgt_01',
            enabled: true,
            intervalSeconds: 30,
            status: 'success',
            lastStartedAt: '2026-05-13T18:01:00.000Z',
            lastFinishedAt: '2026-05-13T18:01:02.000Z',
            lastSuccessAt: '2026-05-13T18:01:02.000Z',
            lastError: null,
            lastRawEventCount: 4,
            lastCreatedCount: 1,
            lastEventIds: ['evt_01'],
            lastRunTrigger: 'manual',
            updatedAt: '2026-05-13T18:01:02.000Z',
          },
        }))
      }
      return Promise.resolve(jsonResponse({ items: [] }))
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mountSidebar()

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="fortigate-ingestion-status-int_fgt_01"]').text()).toContain('Pipeline idle')

    await wrapper.get('[data-test="fortigate-ingest-run-int_fgt_01"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="fortigate-ingestion-status-int_fgt_01"]').text()).toContain('Pipeline success')
    expect(wrapper.get('[data-test="fortigate-ingestion-status-int_fgt_01"]').text()).toContain('4 raw')
    expect(wrapper.get('[data-test="fortigate-ingestion-status-int_fgt_01"]').text()).toContain('1 SIEM')
  })

  it('keeps FortiGate policy management out of the integrations drawer', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/integrations') {
        return Promise.resolve(jsonResponse({
          items: [
            {
              id: 'int_fgt_01',
              type: 'fortigate',
              name: 'FortiGate Lab',
              host: 'https://192.0.2.118',
              status: 'connected',
            },
          ],
        }))
      }
      return Promise.resolve(jsonResponse({
        integrationId: 'int_fgt_01',
        enabled: false,
        intervalSeconds: 30,
        status: 'idle',
        lastStartedAt: null,
        lastFinishedAt: null,
        lastSuccessAt: null,
        lastError: null,
        lastRawEventCount: 0,
        lastCreatedCount: 0,
        lastEventIds: [],
        lastRunTrigger: null,
        updatedAt: '2026-05-13T18:00:00.000Z',
      }))
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mountSidebar()

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="fortigate-policy-draft-int_fgt_01"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Traffic policy helper')
    expect(wrapper.text()).not.toContain('Draft CLI')
    expect(wrapper.text()).not.toContain('Lab policy wizard')
    expect(wrapper.find('[data-test="fortigate-lab-policy-wizard-int_fgt_01"]').exists()).toBe(false)
  })

  it('selects the SOAR playbooks main surface from the sidebar', async () => {
    const wrapper = mountSidebar()

    await wrapper.get('[title="Playbooks SOAR"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('select-surface')).toEqual([['playbooks']])
    expect(wrapper.text()).not.toContain('Port scan triage')
    wrapper.unmount()
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

    const wrapper = mountSidebar()

    await wrapper.get('[title="Trilha de auditoria"]').trigger('click')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith('/api/admin/audit/events?limit=50', {
      credentials: 'include',
    })
    expect(wrapper.text()).toContain('Trilha de auditoria do admin')
    expect(wrapper.text()).toContain('Atividade global do SOC')
    expect(wrapper.text()).toContain('Login concluído')
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

    const wrapper = mountSidebar()

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Penguin SOC Lite')
    expect(wrapper.text()).toContain('Kowalski SIEM')
    expect(wrapper.text()).toContain('siem_kowalski')
    expect(wrapper.find('[data-test="penguin-connect-siem_kowalski"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="penguin-connect-xdr_rico"]').exists()).toBe(false)
  })

  it('groups integration connectors by provider category', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [],
    })))

    const wrapper = mountSidebar()

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Provedores Fortinet')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Nenhum provedor Fortinet conectado')
    expect(wrapper.get('[data-test="integration-group-penguin"]').text()).toContain('Penguin SOC Lite')
    expect(wrapper.get('[data-test="integration-group-penguin"]').text()).toContain('Não conectado')
    expect(wrapper.get('[data-test="open-connect-wizard"]').text()).toContain('Conectar uma máquina')
    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).toContain('Sensor de endpoint / onboarding')
    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).not.toContain('agent_private')
    expect(wrapper.get('[data-test="integration-toggle-endpoint"]').attributes('aria-expanded')).toBe('false')

    await wrapper.get('[data-test="integration-toggle-endpoint"]').trigger('click')

    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).toContain('agent_private')
    expect(wrapper.get('[data-test="integration-group-endpoint"]').text()).toContain('Onboarding no XDR')
    expect(wrapper.find('[data-test="penguin-connect-agent_private"]').exists()).toBe(false)
  })

  it('collapses and expands integration groups from their headers', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [],
    })))

    const wrapper = mountSidebar()

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="integration-toggle-fortinet"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Nenhum provedor Fortinet conectado')

    await wrapper.get('[data-test="integration-toggle-fortinet"]').trigger('click')

    expect(wrapper.get('[data-test="integration-toggle-fortinet"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).not.toContain('Nenhum provedor Fortinet conectado')

    await wrapper.get('[data-test="integration-toggle-fortinet"]').trigger('click')

    expect(wrapper.get('[data-test="integration-toggle-fortinet"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="integration-group-fortinet"]').text()).toContain('Nenhum provedor Fortinet conectado')
  })

  it('opens the unified connect wizard from the integrations drawer', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/integrations/catalog') {
        return Promise.resolve(jsonResponse({
          items: [
            {
              addonId: 'fortiweb-core',
              name: 'FortiWeb Core',
              vendor: 'Fortinet',
              category: 'waf',
              providerType: 'fortiweb',
              versions: ['8.0.5'],
              authFields: [],
              capabilities: { logSource: true, playbookTarget: true, managed: true },
            },
          ],
        }))
      }
      return Promise.resolve(jsonResponse({ items: [] }))
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mountSidebar()

    await wrapper.get('[title="Integrações SOC"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="open-connect-wizard"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('FortiWeb Core')
  })

  it('renders AI widget drafts and inserts them into the workspace after confirmation', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const integrationsStore = useIntegrationsStore()
    integrationsStore.integrations = [
      {
        id: 'int_fgt_01',
        type: 'fortigate',
        name: 'FortiGate Lab',
        status: 'connected',
      },
    ]
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/ai/status') {
        return Promise.resolve(jsonResponse({
          provider: 'scripted',
          model: 'scripted-cockpit',
          ready: true,
          runtime: 'pydantic_ai',
        }))
      }
      if (url === '/api/ai/chat') {
        expect(init?.method).toBe('POST')
        return Promise.resolve(jsonResponse({
          reply: 'draft_widget criou um rascunho card para CPU Usage. Revise o preview e confirme antes de adicionar na workspace.',
          provider: 'pydantic_ai.scripted',
          model: 'scripted-cockpit',
          runtime: 'pydantic_ai',
          widgetDrafts: [
            {
              toolName: 'draft_widget',
              status: 'draft',
              requiresConfirmation: true,
              draft: {
                status: 'draft',
                provider: 'fortigate',
                integrationId: null,
                visualType: 'card',
                title: 'CPU Usage',
                fieldBindings: [
                  {
                    fieldId: 'system.cpu',
                    label: 'CPU Usage',
                    type: 'number',
                    unit: 'percent',
                    source: 'fortigate-system-status',
                    provider: 'fortigate',
                    integrationId: null,
                  },
                ],
                layout: { w: 2, h: 2 },
                settings: { aggregation: 'latest' },
              },
              preview: {
                source: 'simulation',
                values: { 'system.cpu': 0 },
              },
              validation: { valid: true, warnings: [], errors: [] },
            },
          ],
        }))
      }
      if (url === '/api/workspaces/ws_default') {
        return Promise.resolve(jsonResponse({ ok: true }))
      }
      return Promise.resolve(jsonResponse({ items: [] }))
    })
    vi.stubGlobal('fetch', fetcher)

    const dashboardStore = useDashboardStore()
    const wrapper = mountSidebar()

    await wrapper.get('[title="Assistente SOC"]').trigger('click')
    await flushPromises()
    await wrapper.get('input[placeholder="Pergunte ao assistente ou peça um painel..."]').setValue('crie um card usando system.cpu')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-test="ai-widget-draft"]').text()).toContain('CPU Usage')
    expect(wrapper.get('[data-test="ai-widget-draft"]').text()).toContain('system.cpu')

    await wrapper.get('[data-test="ai-widget-draft-add"]').trigger('click')

    expect(dashboardStore.activeWidgets).toHaveLength(1)
    expect(dashboardStore.activeWidgets[0]).toMatchObject({
      catalogId: 'visual-template-card',
      integrationId: 'int_fgt_01',
      fieldBindings: [
        {
          fieldId: 'system.cpu',
          integrationId: 'int_fgt_01',
          integrationType: 'fortigate',
        },
      ],
    })
    expect(wrapper.text()).toContain('Adicionei o visual "CPU Usage" na workspace.')
  })
})

function mountSidebar() {
  return mount(Sidebar, {
    global: {
      plugins: [pinia, i18n],
    },
  })
}
