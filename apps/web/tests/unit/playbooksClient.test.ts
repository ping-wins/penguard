import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createPlaybookWebhookDestination,
  listPlaybookNodeTypes,
  testPlaybookWebhookDestination,
} from '../../src/services/playbooksClient'

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

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('playbooksClient', () => {
  it('loads SOAR node catalog with dry-run and boundary metadata', async () => {
    const fetchMock = mockFetch({
      items: [
        {
          id: 'case.note',
          label: 'Create Case Note',
          category: 'action',
          sensitive: false,
          dryRunOnly: true,
          executionMode: 'dry_run',
          liveAvailable: false,
          boundary: 'case_note',
          configSchema: { type: 'object' },
        },
      ],
    })

    const items = await listPlaybookNodeTypes()

    expect(fetchMock).toHaveBeenCalledWith('/api/soc/playbook-node-types', { credentials: 'include' })
    expect(items).toEqual([
      expect.objectContaining({
        id: 'case.note',
        executionMode: 'dry_run',
        liveAvailable: false,
        boundary: 'case_note',
      }),
    ])
  })

  it('creates and tests server-side webhook destinations with CSRF protection', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ csrfToken: 'csrf-1' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          id: 'pwd_discord_soc',
          name: 'SOC Discord',
          kind: 'discord',
          redactedUrl: 'https://discord.com/api/webhooks/123456789/...',
          status: 'active',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ destinationId: 'pwd_discord_soc', statusCode: 204, ok: true }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const created = await createPlaybookWebhookDestination({
      name: 'SOC Discord',
      kind: 'discord',
      url: 'https://discord.com/api/webhooks/123456789/secret-token',
    })
    const tested = await testPlaybookWebhookDestination('pwd_discord_soc', 'FortiDashboard test')

    expect(created.redactedUrl).toBe('https://discord.com/api/webhooks/123456789/...')
    expect(tested).toEqual({ destinationId: 'pwd_discord_soc', statusCode: 204, ok: true })
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/auth/csrf', { credentials: 'include' })
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/soc/playbook-webhook-destinations',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-CSRF-Token': 'csrf-1',
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/soc/playbook-webhook-destinations/pwd_discord_soc/test',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-CSRF-Token': 'csrf-1',
        }),
      }),
    )
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body)).url).toContain('secret-token')
    expect(created).not.toHaveProperty('url')
  })
})
