export type AuthUser = {
  id: string
  email: string
  displayName: string
  roles: string[]
  permissions?: string[]
  isAdmin?: boolean
}

export type BrowserSession = {
  authenticated: boolean
  user: AuthUser | null
}

type AuthPayload = {
  email: string
  password: string
}

type RegisterPayload = AuthPayload & {
  displayName: string
}

type Fetcher = typeof fetch

export class AuthApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'AuthApiError'
    this.status = status
  }
}

async function parseJson(response: Response) {
  return response.json().catch(() => ({}))
}

async function errorFromResponse(response: Response, fallback: string) {
  const data = await parseJson(response)
  const detail = data?.detail
  if (typeof detail === 'string') return new AuthApiError(detail, response.status)
  return new AuthApiError(fallback, response.status)
}

function isCsrfError(error: AuthApiError) {
  return error.status === 403 && /csrf/i.test(error.message)
}

export async function fetchCsrfToken(fetcher: Fetcher = globalThis.fetch.bind(globalThis)) {
  const response = await fetcher('/api/auth/csrf', { credentials: 'include' })
  if (!response.ok) {
    throw await errorFromResponse(response, 'Unable to start secure authentication flow')
  }

  const data = await parseJson(response)
  if (!data?.csrfToken || typeof data.csrfToken !== 'string') {
    throw new AuthApiError('Unable to start secure authentication flow', 502)
  }
  return data.csrfToken
}

async function postAuth(
  endpoint: '/api/auth/login' | '/api/auth/register' | '/api/auth/logout',
  payload: AuthPayload | RegisterPayload | null,
  fetcher: Fetcher,
) {
  const send = async (csrfToken: string) => {
    const headers: Record<string, string> = { 'X-CSRF-Token': csrfToken }
    const init: RequestInit = {
      method: 'POST',
      headers,
      credentials: 'include',
    }
    if (payload !== null) {
      headers['Content-Type'] = 'application/json'
      init.body = JSON.stringify(payload)
    }

    const response = await fetcher(endpoint, init)
    if (!response.ok) {
      throw await errorFromResponse(response, 'Authentication request failed')
    }
    return parseJson(response)
  }

  try {
    return await send(await fetchCsrfToken(fetcher))
  } catch (error) {
    if (error instanceof AuthApiError && isCsrfError(error)) {
      return send(await fetchCsrfToken(fetcher))
    }
    throw error
  }
}

export async function fetchBrowserSession(
  fetcher: Fetcher = globalThis.fetch.bind(globalThis),
): Promise<BrowserSession> {
  const response = await fetcher('/api/auth/me', { credentials: 'include' })
  if (!response.ok) {
    throw await errorFromResponse(response, 'Unable to verify browser session')
  }
  return parseJson(response) as Promise<BrowserSession>
}

export async function loginWithBrowserSession({
  email,
  password,
  fetcher = globalThis.fetch.bind(globalThis),
}: AuthPayload & { fetcher?: Fetcher }): Promise<BrowserSession> {
  await postAuth('/api/auth/login', { email, password }, fetcher)
  return fetchBrowserSession(fetcher)
}

export async function registerWithBrowserSession({
  displayName,
  email,
  password,
  fetcher = globalThis.fetch.bind(globalThis),
}: RegisterPayload & { fetcher?: Fetcher }): Promise<BrowserSession> {
  await postAuth('/api/auth/register', { displayName, email, password }, fetcher)
  return fetchBrowserSession(fetcher)
}

export function ssoKerberosLoginUrl(): string {
  return '/api/auth/sso/kerberos/init'
}

export async function logoutBrowserSession(
  fetcher: Fetcher = globalThis.fetch.bind(globalThis),
): Promise<BrowserSession> {
  await postAuth('/api/auth/logout', null, fetcher)
  return { authenticated: false, user: null }
}
