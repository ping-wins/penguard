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
})
