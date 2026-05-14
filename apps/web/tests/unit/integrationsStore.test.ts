import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../src/stores/useAuthStore'
import { useIntegrationsStore } from '../../src/stores/useIntegrationsStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useIntegrationsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('treats a FortiGate probe with ok=false as a failed connection', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      ok: false,
      status: 'disconnected',
      error: { message: 'FortiGate API request failed with HTTP 404' },
    }))
    vi.stubGlobal('fetch', fetcher)

    const store = useIntegrationsStore()

    await expect(store.testFortigate(
      'https://fortigate.local',
      'invalid-but-long-key',
      false,
    )).resolves.toEqual({
      success: false,
      error: 'FortiGate API request failed with HTTP 404',
    })
  })

  it('removes an integration through the API and local state', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      deleted: true,
      id: 'int_fgt_01',
    }))
    vi.stubGlobal('fetch', fetcher)

    const store = useIntegrationsStore()
    store.integrations = [
      { id: 'int_fgt_01', type: 'fortigate', name: 'Lab A', status: 'connected' },
      { id: 'int_fgt_02', type: 'fortigate', name: 'Lab B', status: 'connected' },
    ]

    await expect(store.removeIntegration('int_fgt_01')).resolves.toEqual({
      success: true,
      data: { deleted: true, id: 'int_fgt_01' },
    })

    expect(fetcher).toHaveBeenCalledWith('/api/integrations/int_fgt_01', {
      method: 'DELETE',
      headers: { 'X-CSRF-Token': 'csrf_01' },
      credentials: 'include',
    })
    expect(store.integrations.map(item => item.id)).toEqual(['int_fgt_02'])
  })

  it('tests a Penguin tool with CSRF credentials', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      ok: true,
      status: 'connected',
      service: 'siem_kowalski',
      capabilities: ['events', 'incidents'],
    }))
    vi.stubGlobal('fetch', fetcher)

    const store = useIntegrationsStore()

    await expect(store.testPenguinTool('siem_kowalski')).resolves.toEqual({
      success: true,
      data: {
        ok: true,
        status: 'connected',
        service: 'siem_kowalski',
        capabilities: ['events', 'incidents'],
      },
    })

    expect(fetcher).toHaveBeenCalledWith('/api/integrations/penguin-tools/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      },
      credentials: 'include',
      body: JSON.stringify({ type: 'siem_kowalski' }),
    })
  })

  it('adds a Penguin tool integration and updates local state', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const responseBody = {
      id: 'int_kowalski_01',
      type: 'siem_kowalski',
      name: 'Kowalski SIEM',
      status: 'connected',
      capabilities: ['events', 'incidents'],
      lastCheckedAt: '2026-05-08T12:00:00.000Z',
    }
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(responseBody))
    vi.stubGlobal('fetch', fetcher)

    const store = useIntegrationsStore()

    await expect(store.addPenguinTool('siem_kowalski', 'Kowalski SIEM')).resolves.toEqual({
      success: true,
      data: responseBody,
    })

    expect(fetcher).toHaveBeenCalledWith('/api/integrations/penguin-tools', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      },
      credentials: 'include',
      body: JSON.stringify({ type: 'siem_kowalski', name: 'Kowalski SIEM' }),
    })
    expect(store.integrations).toEqual([responseBody])
  })

  it('keeps local integrations when removal fails', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(
      { detail: 'Integration not found' },
      { status: 404 },
    )))

    const store = useIntegrationsStore()
    store.integrations = [
      { id: 'int_fgt_01', type: 'fortigate', name: 'Lab A', status: 'connected' },
    ]

    await expect(store.removeIntegration('int_fgt_01')).resolves.toEqual({
      success: false,
      error: 'Integration not found',
    })
    expect(store.integrations.map(item => item.id)).toEqual(['int_fgt_01'])
  })

  it('fetches and triggers FortiGate ingestion status with CSRF credentials', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/ingestion-status') && init?.method === 'PUT') {
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

    const store = useIntegrationsStore()

    await expect(store.configureFortigateIngestion('int_fgt_01', {
      enabled: true,
      intervalSeconds: 30,
    })).resolves.toEqual({
      success: true,
      data: expect.objectContaining({
        enabled: true,
        intervalSeconds: 30,
      }),
    })
    await expect(store.runFortigateIngestion('int_fgt_01')).resolves.toEqual({
      success: true,
      data: expect.objectContaining({
        rawEventCount: 4,
        createdCount: 1,
      }),
    })

    expect(fetcher).toHaveBeenCalledWith('/api/soc/fortigate/int_fgt_01/ingestion-status', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      },
      credentials: 'include',
      body: JSON.stringify({ enabled: true, intervalSeconds: 30 }),
    })
    expect(fetcher).toHaveBeenCalledWith('/api/soc/fortigate/int_fgt_01/ingest-events', {
      method: 'POST',
      headers: { 'X-CSRF-Token': 'csrf_01' },
      credentials: 'include',
    })
    expect(store.ingestionStatusById.int_fgt_01).toMatchObject({
      enabled: true,
      status: 'success',
      lastRawEventCount: 4,
      lastCreatedCount: 1,
      lastEventIds: ['evt_01'],
    })
  })
})
