import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../src/stores/useAuthStore'
import { useIntegrationConnectStore } from '../../src/stores/useIntegrationConnectStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useIntegrationConnectStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads the catalog', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      items: [
        {
          addonId: 'fortiweb-core',
          name: 'FortiWeb Core',
          vendor: 'Fortinet',
          category: 'waf',
          providerType: 'fortiweb',
          versions: ['8.0.5'],
          authFields: [],
          capabilities: {
            logSource: true,
            playbookTarget: true,
            managed: true,
          },
        },
      ],
    }))
    vi.stubGlobal('fetch', fetcher)

    const store = useIntegrationConnectStore()
    await store.fetchCatalog()

    expect(fetcher).toHaveBeenCalledWith('/api/integrations/catalog', {
      credentials: 'include',
    })
    expect(store.catalog).toHaveLength(1)
    expect(store.catalog[0].addonId).toBe('fortiweb-core')
    expect(store.error).toBe(null)
  })

  it('reports a connect-test failure message', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      ok: false,
      message: 'host unreachable',
    }))
    vi.stubGlobal('fetch', fetcher)

    const store = useIntegrationConnectStore()
    const result = await store.testConnection({
      addonId: 'fortiweb-core',
      version: '8.0.5',
      name: 'WAF',
      auth: {},
    })

    expect(result).toEqual({ success: false, error: 'host unreachable' })
    expect(fetcher).toHaveBeenCalledWith('/api/integrations/connect/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      },
      credentials: 'include',
      body: JSON.stringify({
        addonId: 'fortiweb-core',
        version: '8.0.5',
        name: 'WAF',
        auth: {},
      }),
    })
  })

  it('connects through the generic endpoint and clears submitting state', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const responseBody = {
      integration: { id: 'int_fweb_01', type: 'fortiweb', name: 'WAF' },
      wiring: { siem: null, soar: null },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(responseBody)))

    const store = useIntegrationConnectStore()
    const result = await store.connect({
      addonId: 'fortiweb-core',
      version: '8.0.5',
      name: 'WAF',
      auth: { host: 'https://fortiweb.local', apiKey: 'secret' },
      wire: { siem: true, soar: true },
    })

    expect(result).toEqual({ success: true, data: responseBody })
    expect(store.isSubmitting).toBe(false)
  })
})
