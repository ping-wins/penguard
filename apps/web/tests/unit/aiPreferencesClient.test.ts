import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getAiPreferences,
  updateAiPreferences,
} from '../../src/services/aiPreferencesClient'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('aiPreferencesClient', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('getAiPreferences sends credentials and parses response', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(
      jsonResponse({
        mode: 'api',
        provider: 'gemini',
        model: 'gemini-flash-latest',
        apiKeySet: false,
        cliBinary: '',
        updatedAt: null,
      }),
    )
    vi.stubGlobal('fetch', fetcher)

    const result = await getAiPreferences()

    expect(fetcher).toHaveBeenCalledWith('/api/ai/preferences', expect.objectContaining({ credentials: 'include' }))
    expect(result.provider).toBe('gemini')
    expect(result.apiKeySet).toBe(false)
  })

  it('updateAiPreferences PUTs payload with CSRF header', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_z' }))
      .mockResolvedValueOnce(
        jsonResponse({
          mode: 'api',
          provider: 'gemini',
          model: 'gemini-flash-latest',
          apiKeySet: true,
          cliBinary: '',
          updatedAt: '2026-05-16T00:00:00.000Z',
        }),
      )
    vi.stubGlobal('fetch', fetcher)

    const result = await updateAiPreferences({
      mode: 'api',
      provider: 'gemini',
      model: 'gemini-flash-latest',
      apiKey: 'AIza-xyz',
    })

    const putCall = fetcher.mock.calls[1]
    expect(putCall[0]).toBe('/api/ai/preferences')
    expect(putCall[1].method).toBe('PUT')
    expect(putCall[1].headers['X-CSRF-Token']).toBe('csrf_z')
    const body = JSON.parse(putCall[1].body)
    expect(body.apiKey).toBe('AIza-xyz')
    expect(result.apiKeySet).toBe(true)
  })

  it('throws when server returns error detail', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'forbidden' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetcher)

    await expect(getAiPreferences()).rejects.toThrow('forbidden')
  })
})
