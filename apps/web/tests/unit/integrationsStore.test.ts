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
})
