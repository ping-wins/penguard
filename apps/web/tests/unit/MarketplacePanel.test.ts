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

  it('localizes marketplace add-on manifest metadata in the active locale', async () => {
    setLocale('pt-BR')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      items: [
        {
          id: 'fortianalyzer-core',
          name: 'FortiAnalyzer Core Beta',
          vendor: 'Fortinet',
          category: 'siem',
          description: 'SIEM analytics beta for FortiAnalyzer.',
          latestVersion: '0.1.0-beta.1',
          versions: ['0.1.0-beta.1'],
          installed: false,
          installedVersion: null,
          provider: {
            type: 'fortianalyzer',
            auth: {
              kind: 'apiKey',
              fields: [
                {
                  id: 'host',
                  label: 'FortiAnalyzer URL',
                  type: 'url',
                  required: true,
                  placeholder: 'https://fortianalyzer.example.local',
                },
                {
                  id: 'apiKey',
                  label: 'API key',
                  type: 'secret',
                  required: true,
                },
                {
                  id: 'verifyTls',
                  label: 'Verify TLS',
                  type: 'boolean',
                  default: false,
                },
              ],
            },
          },
          routes: [
            {
              id: 'jsonrpc-system-status',
              method: 'POST',
              path: '/jsonrpc',
              summary: 'Read-only JSON-RPC request for /sys/status.',
            },
          ],
          widgets: [
            'fortianalyzer-health-preview',
            'fortianalyzer-adom-log-posture',
            'fortianalyzer-top-event-types',
            'fortianalyzer-ingestion-readiness',
          ],
          siemEventTypes: ['fortianalyzer.analytics.preview'],
        },
      ],
      count: 1,
    })))

    const wrapper = mount(MarketplacePanel, {
      global: {
        plugins: [i18n],
        stubs: { Teleport: true },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Beta de analytics SIEM para FortiAnalyzer')

    const detailsButton = wrapper.findAll('button')
      .find(button => button.text().includes('Detalhes'))
    expect(detailsButton).toBeTruthy()
    await detailsButton!.trigger('click')

    expect(wrapper.text()).toContain('URL do FortiAnalyzer')
    expect(wrapper.text()).toContain('Chave de API')
    expect(wrapper.text()).toContain('Verificar TLS')
    expect(wrapper.text()).toContain('Requisição JSON-RPC read-only para /sys/status.')
    expect(wrapper.text()).toContain('Saúde do FortiAnalyzer (preview)')
    expect(wrapper.text()).toContain('Postura de logs/ADOM (preview)')
    expect(wrapper.text()).toContain('Tipos de evento principais (preview)')
    expect(wrapper.text()).toContain('Prontidão de ingestão (preview)')
    expect(wrapper.text()).toContain('Analytics do FortiAnalyzer (preview)')
  })
})

async function flushPromises() {
  await new Promise(resolve => setTimeout(resolve, 0))
}
