import { describe, expect, it, vi } from 'vitest'
import {
  AuthApiError,
  fetchCsrfToken,
  loginWithBrowserSession,
  registerWithBrowserSession,
} from '../../src/services/authClient'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('authClient', () => {
  it('fetches CSRF with browser credentials and fails if token is missing', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({}))

    await expect(fetchCsrfToken(fetcher)).rejects.toMatchObject({
      message: 'Unable to start secure authentication flow',
      status: 502,
    })
    expect(fetcher).toHaveBeenCalledWith('/api/auth/csrf', { credentials: 'include' })
  })

  it('logs in with CSRF, cookie credentials, then confirms the browser session through /me', async () => {
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

    const result = await loginWithBrowserSession({
      email: 'analyst@example.com',
      password: 'correct-horse-battery-staple',
      fetcher,
    })

    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      },
      credentials: 'include',
      body: JSON.stringify({
        email: 'analyst@example.com',
        password: 'correct-horse-battery-staple',
      }),
    })
    expect(fetcher).toHaveBeenNthCalledWith(3, '/api/auth/me', { credentials: 'include' })
    expect(result).toEqual({
      authenticated: true,
      user: { id: 'usr_01', email: 'analyst@example.com', displayName: 'SOC Analyst', roles: ['analyst'] },
    })
  })

  it('refreshes CSRF once when login receives a stale-token 403', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'stale_csrf' }))
      .mockResolvedValueOnce(jsonResponse({ detail: 'CSRF validation failed' }, { status: 403 }))
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'fresh_csrf' }))
      .mockResolvedValueOnce(jsonResponse({
        user: { id: 'usr_01', email: 'analyst@example.com', displayName: 'SOC Analyst', roles: ['analyst'] },
        session: { authenticated: true, expiresAt: '2026-04-26T22:30:00.000Z' },
      }))
      .mockResolvedValueOnce(jsonResponse({
        authenticated: true,
        user: { id: 'usr_01', email: 'analyst@example.com', displayName: 'SOC Analyst', roles: ['analyst'] },
      }))

    await loginWithBrowserSession({
      email: 'analyst@example.com',
      password: 'correct-horse-battery-staple',
      fetcher,
    })

    expect(fetcher).toHaveBeenNthCalledWith(4, '/api/auth/login', expect.objectContaining({
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'fresh_csrf',
      },
    }))
  })

  it('maps backend auth errors to typed errors for the UI', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf_01' }))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Email already registered' }, { status: 409 }))

    await expect(registerWithBrowserSession({
      displayName: 'SOC Analyst',
      email: 'analyst@example.com',
      password: 'correct-horse-battery-staple',
      fetcher,
    })).rejects.toEqual(new AuthApiError('Email already registered', 409))
  })
})
