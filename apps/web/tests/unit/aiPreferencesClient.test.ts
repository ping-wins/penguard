import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getSocAssistantSettings,
  saveSocAssistantSettings,
  testSocAssistantSettings,
} from '../../src/services/socAssistantSettingsClient'
import { i18n } from '../../src/i18n'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('socAssistantSettingsClient', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    i18n.global.locale.value = 'pt-BR'
  })

  it('getSocAssistantSettings sends credentials and parses response', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(
      jsonResponse({
        provider: 'openai',
        model: 'gpt-4o',
        apiKeySet: false,
        configured: false,
        lastTestedAt: null,
        lastTestStatus: null,
        lastTestError: null,
        updatedBy: null,
        updatedAt: null,
      }),
    )
    vi.stubGlobal('fetch', fetcher)

    const result = await getSocAssistantSettings()

    expect(fetcher).toHaveBeenCalledWith(
      '/api/ai/agent/settings',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(result.provider).toBe('openai')
    expect(result.configured).toBe(false)
  })

  it('saveSocAssistantSettings PUTs payload with CSRF header', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_z' }))
      .mockResolvedValueOnce(
        jsonResponse({
          provider: 'anthropic',
          model: 'claude-sonnet-4-6',
          apiKeySet: true,
          configured: true,
          lastTestedAt: null,
          lastTestStatus: null,
          lastTestError: null,
          updatedBy: 'admin@example.com',
          updatedAt: '2026-05-18T12:01:00.000Z',
        }),
      )
    vi.stubGlobal('fetch', fetcher)

    const result = await saveSocAssistantSettings({
      provider: 'anthropic',
      model: 'claude-sonnet-4-6',
      apiKey: 'sk-ant-secret',
    })

    const putCall = fetcher.mock.calls[1]
    expect(putCall[0]).toBe('/api/ai/agent/settings')
    expect(putCall[1].method).toBe('PUT')
    expect(putCall[1].credentials).toBe('include')
    expect(putCall[1].headers['X-CSRF-Token']).toBe('csrf_z')
    expect(putCall[1].headers['Content-Type']).toBe('application/json')
    const body = JSON.parse(putCall[1].body)
    expect(body.apiKey).toBe('sk-ant-secret')
    expect(result.apiKeySet).toBe(true)
  })

  it('testSocAssistantSettings POSTs with CSRF and parses success status', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_z' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, status: 'success', error: null }))
    vi.stubGlobal('fetch', fetcher)

    const result = await testSocAssistantSettings()

    const postCall = fetcher.mock.calls[1]
    expect(postCall[0]).toBe('/api/ai/agent/settings/test')
    expect(postCall[1].method).toBe('POST')
    expect(postCall[1].credentials).toBe('include')
    expect(postCall[1].headers['X-CSRF-Token']).toBe('csrf_z')
    expect(result.status).toBe('success')
  })

  it('throws string detail from server errors', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'forbidden' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetcher)

    await expect(getSocAssistantSettings()).rejects.toThrow('forbidden')
  })

  it('uses localized fallback when server errors have no detail', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({}), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetcher)

    await expect(getSocAssistantSettings()).rejects.toThrow(
      'Falha ao carregar configurações do Assistente SOC.',
    )
  })
})
