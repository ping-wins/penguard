export type PolicyProviderType = 'fortigate' | 'fortiweb'
export type PolicyAction = 'create' | 'edit' | 'enable' | 'disable' | 'delete'
export type PolicyOwnership = 'fortidashboard' | 'external' | 'unknown'

export type PolicyProviderSummary = {
  providerType: PolicyProviderType
  integrationId: string
  name: string
  capabilities: string[]
  policyKinds: string[]
}

export type PolicyRow = {
  id: string
  providerType: PolicyProviderType
  integrationId: string
  nativeId: string
  name: string
  kind: string
  status: string
  action?: string | null
  direction: Record<string, unknown>
  scope: Record<string, unknown>
  ownership: PolicyOwnership
  managedByFortiDashboard: boolean
  isMutable: boolean
  supports: string[]
  risk: Record<string, unknown>
  summary: string
  lastObservedAt?: string | null
  raw?: Record<string, unknown> | null
}

export type PolicyListResponse = {
  items: PolicyRow[]
  nextCursor?: string | null
}

export type PolicyFilters = {
  providerType?: PolicyProviderType
  integrationId?: string
  kind?: string
  status?: string
  ownership?: PolicyOwnership
  q?: string
}

export type PolicyReviewCreateRequest = {
  providerType: PolicyProviderType
  integrationId: string
  action: PolicyAction
  policyId?: string | null
  payload: Record<string, unknown>
}

export type PolicyReview = {
  id: string
  providerType: PolicyProviderType
  integrationId: string
  policyId?: string | null
  action: PolicyAction
  status: 'pending_review' | 'applied' | 'failed'
  title: string
  before: Record<string, unknown>
  after: Record<string, unknown>
  diff: Array<Record<string, unknown>>
  warnings: Array<Record<string, unknown>>
  rollback: string[]
  reviewHash: string
}

export type PolicyReviewApplyRequest = {
  reviewHash: string
  confirmed: boolean
}

export type PolicyApplyResult = {
  id: string
  status: 'applied' | 'failed' | string
  providerType: PolicyProviderType
  integrationId: string
  appliedResult?: Record<string, unknown>
}

type Fetcher = typeof fetch

export class PoliciesApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'PoliciesApiError'
    this.status = status
  }
}

async function parseJson(response: Response) {
  return response.json().catch(() => ({}))
}

async function request<T>(input: string, init: RequestInit, fetcher: Fetcher): Promise<T> {
  const response = await fetcher(input, { credentials: 'include', ...init })
  if (!response.ok) {
    const body = await parseJson(response)
    const detail = typeof body?.detail === 'string' ? body.detail : 'Request failed'
    throw new PoliciesApiError(detail, response.status)
  }
  return (await parseJson(response)) as T
}

function query(filters: PolicyFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value)
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

const defaultFetcher = () => globalThis.fetch.bind(globalThis)

export const policiesClient = {
  async listProviders(fetcher: Fetcher = defaultFetcher()): Promise<PolicyProviderSummary[]> {
    const data = await request<{ items: PolicyProviderSummary[] }>(
      '/api/policies/providers',
      { method: 'GET' },
      fetcher,
    )
    return data.items
  },

  async listPolicies(
    filters: PolicyFilters = {},
    fetcher: Fetcher = defaultFetcher(),
  ): Promise<PolicyListResponse> {
    return request<PolicyListResponse>(`/api/policies${query(filters)}`, { method: 'GET' }, fetcher)
  },

  async createReview(
    payload: PolicyReviewCreateRequest,
    csrfToken: string,
    fetcher: Fetcher = defaultFetcher(),
  ): Promise<PolicyReview> {
    return request<PolicyReview>(
      '/api/policies/reviews',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(payload),
      },
      fetcher,
    )
  },

  async applyReview(
    reviewId: string,
    payload: PolicyReviewApplyRequest,
    csrfToken: string,
    fetcher: Fetcher = defaultFetcher(),
  ): Promise<PolicyApplyResult> {
    return request<PolicyApplyResult>(
      `/api/policies/reviews/${encodeURIComponent(reviewId)}/apply`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(payload),
      },
      fetcher,
    )
  },
}
