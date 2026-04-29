import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../src/stores/useAuthStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('marks login authenticated only after /auth/me confirms the browser session', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_01' }))
      .mockResolvedValueOnce(jsonResponse({
        user: { id: 'usr_01', email: 'analyst@example.com', displayName: 'SOC Analyst', roles: ['analyst'] },
        session: { authenticated: true, expiresAt: '2026-04-26T22:30:00.000Z' },
      }))
      .mockResolvedValueOnce(jsonResponse({
        authenticated: true,
        user: { id: 'usr_01', email: 'analyst@example.com', displayName: 'SOC Analyst', roles: ['analyst'] },
      }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAuthStore()
    await store.login({
      email: 'analyst@example.com',
      password: 'correct-horse-battery-staple',
    })

    expect(store.isAuthenticated).toBe(true)
    expect(store.user.email).toBe('analyst@example.com')
    expect(store.isInitialized).toBe(true)
  })

  it('hydrates an existing browser session from /auth/me on reload', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(jsonResponse({
      authenticated: true,
      user: { id: 'usr_01', email: 'analyst@example.com', displayName: 'SOC Analyst', roles: ['analyst'] },
    }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAuthStore()
    await store.fetchSession()

    expect(fetcher).toHaveBeenCalledWith('/api/auth/me', { credentials: 'include' })
    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.email).toBe('analyst@example.com')
    expect(store.isInitialized).toBe(true)
  })

  it('marks the user unauthenticated when /auth/me returns no active session', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(jsonResponse({
      authenticated: false,
      user: null,
    }))
    vi.stubGlobal('fetch', fetcher)

    const store = useAuthStore()
    await store.fetchSession()

    expect(store.isAuthenticated).toBe(false)
    expect(store.user).toBeNull()
    expect(store.isInitialized).toBe(true)
  })
})
