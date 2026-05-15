import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  installMarketplaceAddon,
  listMarketplaceAddons,
} from '../../src/services/marketplaceClient'

function mockFetch(response: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    json: vi.fn().mockResolvedValue(response),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('marketplaceClient', () => {
  it('lists add-ons with installed metadata', async () => {
    mockFetch({
      items: [
        {
          id: 'fortiweb-waf',
          version: '0.1.0',
          name: 'FortiWeb WAF',
          vendor: 'Fortinet',
          category: 'waf',
          description: 'WAF telemetry',
          provider: { type: 'fortiweb', auth: { kind: 'apiKey', fields: [] } },
          routes: [],
          widgets: [],
          siemEventTypes: ['waf.attack'],
          installed: true,
          installedVersion: '0.1.0',
        },
      ],
      count: 1,
    })

    const addons = await listMarketplaceAddons()

    expect(addons).toHaveLength(1)
    expect(addons[0].installed).toBe(true)
    expect(addons[0].installedVersion).toBe('0.1.0')
  })

  it('posts to install endpoint with version body', async () => {
    const fetchMock = mockFetch({ id: 'fortiweb-waf', status: 'installed' })

    await installMarketplaceAddon('fortiweb-waf', '0.1.0')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/marketplace/addons/fortiweb-waf/install',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version: '0.1.0' }),
      }),
    )
  })

  it('throws with detail message on install failure', async () => {
    mockFetch({ detail: 'tarball fetch returned HTTP 404' }, false)

    await expect(
      installMarketplaceAddon('missing-pkg', '9.9.9'),
    ).rejects.toThrow('tarball fetch returned HTTP 404')
  })
})
