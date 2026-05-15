import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMarketplaceStore } from '../../src/stores/useMarketplaceStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const fortiwebAddon = {
  id: 'fortiweb-waf',
  version: '0.1.0',
  name: 'FortiWeb WAF',
  vendor: 'Fortinet',
  category: 'waf',
  description: 'WAF telemetry',
  provider: { type: 'fortiweb', auth: { kind: 'apiKey' as const, fields: [] } },
  routes: [],
  widgets: [],
  siemEventTypes: ['waf.attack'],
  installed: false,
  installedVersion: null,
}

describe('useMarketplaceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('installs an add-on then refreshes the list with installed=true', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ id: 'fortiweb-waf', status: 'installed' }))
      .mockResolvedValueOnce(jsonResponse({
        items: [{ ...fortiwebAddon, installed: true, installedVersion: '0.1.0' }],
        count: 1,
      }))
    vi.stubGlobal('fetch', fetcher)

    const store = useMarketplaceStore()

    await store.install(fortiwebAddon)

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      '/api/marketplace/addons/fortiweb-waf/install',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      '/api/marketplace/addons',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(store.installingId).toBe(null)
    expect(store.addons[0].installed).toBe(true)
    expect(store.error).toBe(null)
  })

  it('captures install error and rethrows', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'tarball fetch returned HTTP 404' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetcher)

    const store = useMarketplaceStore()

    await expect(store.install(fortiwebAddon)).rejects.toThrow(
      'tarball fetch returned HTTP 404',
    )
    expect(store.error).toBe('tarball fetch returned HTTP 404')
    expect(store.installingId).toBe(null)
  })
})
