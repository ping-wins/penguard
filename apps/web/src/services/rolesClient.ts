export type PermissionCatalogEntry = {
  slug: string
  category: string
  labelKey: string
  descriptionKey: string
}

export type RoleSummary = {
  id: string
  name: string
  description: string | null
  color: string | null
  isSystem: boolean
  permissions: string[]
  memberCount: number
  createdAt: string
  updatedAt: string
}

export type RoleMember = {
  userId: string
  email: string | null
  displayName: string | null
  grantedAt: string
  grantedBy: string | null
}

export type RolePill = {
  id: string
  name: string
  color: string | null
}

export type DirectoryUser = {
  userId: string
  email: string | null
  displayName: string | null
  roles: RolePill[]
  lastSeenAt: string | null
}

export type MePermissions = {
  permissions: string[]
  isAdmin: boolean
}

export type CreateRolePayload = {
  name: string
  description?: string | null
  color?: string | null
  permissions: string[]
}

export type UpdateRolePayload = Partial<CreateRolePayload>

type Fetcher = typeof fetch

export class RolesApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'RolesApiError'
    this.status = status
  }
}

async function parseJson(response: Response) {
  return response.json().catch(() => ({}))
}

async function request<T>(input: string, init: RequestInit, fetcher: Fetcher): Promise<T> {
  const response = await fetcher(input, { credentials: 'include', ...init })
  if (response.status === 204) {
    return undefined as T
  }
  if (!response.ok) {
    const body = await parseJson(response)
    const detail = typeof body?.detail === 'string' ? body.detail : 'Request failed'
    throw new RolesApiError(detail, response.status)
  }
  return (await parseJson(response)) as T
}

async function postWithCsrf<T>(
  url: string,
  body: unknown,
  method: 'POST' | 'PATCH' | 'DELETE',
  fetcher: Fetcher,
): Promise<T> {
  const csrfResponse = await fetcher('/api/auth/csrf', { credentials: 'include' })
  const csrfBody = await parseJson(csrfResponse)
  const csrfToken: string | undefined = csrfBody?.csrfToken
  const headers: Record<string, string> = {
    'X-CSRF-Token': csrfToken ?? '',
  }
  const init: RequestInit = { method, headers, credentials: 'include' }
  if (body !== undefined && body !== null) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  return request<T>(url, init, fetcher)
}

const defaultFetcher = () => globalThis.fetch.bind(globalThis)

export const rolesClient = {
  async listRoles(fetcher: Fetcher = defaultFetcher()): Promise<RoleSummary[]> {
    return request('/api/roles', { method: 'GET' }, fetcher)
  },
  async getCatalog(fetcher: Fetcher = defaultFetcher()): Promise<PermissionCatalogEntry[]> {
    return request('/api/roles/permissions/catalog', { method: 'GET' }, fetcher)
  },
  async createRole(payload: CreateRolePayload, fetcher: Fetcher = defaultFetcher()): Promise<RoleSummary> {
    return postWithCsrf('/api/roles', payload, 'POST', fetcher)
  },
  async updateRole(
    roleId: string,
    payload: UpdateRolePayload,
    fetcher: Fetcher = defaultFetcher(),
  ): Promise<RoleSummary> {
    return postWithCsrf(`/api/roles/${roleId}`, payload, 'PATCH', fetcher)
  },
  async deleteRole(roleId: string, fetcher: Fetcher = defaultFetcher()): Promise<void> {
    return postWithCsrf(`/api/roles/${roleId}`, null, 'DELETE', fetcher)
  },
  async listMembers(roleId: string, fetcher: Fetcher = defaultFetcher()): Promise<RoleMember[]> {
    return request(`/api/roles/${roleId}/members`, { method: 'GET' }, fetcher)
  },
  async addMember(
    roleId: string,
    body: { userId?: string; email?: string },
    fetcher: Fetcher = defaultFetcher(),
  ): Promise<RoleMember> {
    return postWithCsrf(`/api/roles/${roleId}/members`, body, 'POST', fetcher)
  },
  async removeMember(roleId: string, userId: string, fetcher: Fetcher = defaultFetcher()): Promise<void> {
    return postWithCsrf(`/api/roles/${roleId}/members/${userId}`, null, 'DELETE', fetcher)
  },
  async listUsers(q: string | null, fetcher: Fetcher = defaultFetcher()): Promise<DirectoryUser[]> {
    const url = q ? `/api/users?q=${encodeURIComponent(q)}` : '/api/users'
    return request(url, { method: 'GET' }, fetcher)
  },
  async updateUserRoles(
    userId: string,
    body: { add: string[]; remove: string[] },
    fetcher: Fetcher = defaultFetcher(),
  ): Promise<DirectoryUser> {
    return postWithCsrf(`/api/users/${userId}/roles`, body, 'PATCH', fetcher)
  },
  async fetchMyPermissions(fetcher: Fetcher = defaultFetcher()): Promise<MePermissions> {
    return request('/api/users/me/permissions', { method: 'GET' }, fetcher)
  },
}
