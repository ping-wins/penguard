import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAuthStore } from './useAuthStore'

export type PenguinToolType = 'siem_kowalski' | 'xdr_rico' | 'soar_skipper'

export type FortiGateIngestionStatus = {
  id?: string
  integrationId: string
  enabled: boolean
  intervalSeconds: number
  status: 'idle' | 'running' | 'success' | 'failed' | string
  lastStartedAt: string | null
  lastFinishedAt: string | null
  lastSuccessAt: string | null
  lastError: string | null
  lastRawEventCount: number
  lastCreatedCount: number
  lastEventIds: string[]
  lastRunTrigger: string | null
  updatedAt: string
}

export type FortiGatePolicyIntent = 'lab_allow_log' | 'temporary_block'
export type FortiGatePolicyScope = 'source_only' | 'source_destination' | 'source_destination_service'

export type FortiGatePolicyPayload = {
  intent: FortiGatePolicyIntent
  scope: FortiGatePolicyScope
  source_interface: string
  destination_interface: string
  source_ip: string
  destination_ip?: string
  service?: string
  duration_minutes?: number
  incident_id?: string
  playbook_run_id?: string
}

export type FortiGatePolicyChange = {
  operation: 'create' | 'reuse'
  object_type: 'firewall.address' | 'firewall.policy'
  name: string
  payload: Record<string, unknown>
}

export type FortiGatePolicyPreflightResponse = {
  intent: FortiGatePolicyIntent
  scope: FortiGatePolicyScope
  integration_id: string
  existing_policy_count: number
  owned_policy_count: number
  proposed_policy_name: string
  placement: string
  warnings: string[]
  changes: FortiGatePolicyChange[]
  review_hash: string
}

export type FortiGatePolicyReviewResponse = FortiGatePolicyPreflightResponse & {
  request_id: string
  status: 'pending_review'
  expires_at?: string | null
}

export type FortiGatePolicyApplyResponse = {
  request_id: string
  status: 'applied'
  applied_changes: Array<Record<string, unknown>>
}

export type FortiGateLogForwardingRequest = {
  collectorHost: string
  port?: number
  mode?: 'udp' | 'legacy-reliable' | 'reliable'
  facility?: string
  format?: 'default' | 'csv' | 'cef' | 'rfc5424'
  severity?: string
  confirmed?: boolean
}

export type FortiGateLogReceiveStatus = {
  mode: 'syslog' | 'polling' | string
  pollingEnabled: boolean
  status: string | null
  lastReceivedAt: string | null
  lastEventIds: string[]
  lastError: string | null
  rawEventCount: number
  createdCount: number
}

export type FortiGateLogForwardingResponse = {
  integrationId?: string
  mode?: 'syslog_forwarding'
  configured: boolean
  current?: Record<string, any>
  desired?: Record<string, any>
  receiveStatus?: FortiGateLogReceiveStatus
  cliCommands?: string[]
  warnings?: string[]
  applied?: boolean
}

export type FortiGateCollectorTestResponse = {
  sent: boolean
  collectorHost: string
  collectorPort: number
  integrationId: string
  sentAt: string
  sample: string
  receiveStatus?: FortiGateLogReceiveStatus
}

export const useIntegrationsStore = defineStore('integrations', () => {
  const integrations = ref<any[]>([])
  const isLoading = ref(false)
  const isTesting = ref(false)
  const isDeleting = ref<Record<string, boolean>>({})
  const isIngesting = ref<Record<string, boolean>>({})
  const ingestionStatusById = ref<Record<string, FortiGateIngestionStatus>>({})
  const error = ref<string | null>(null)

  const hasFortigate = computed(() => integrations.value.some(i => i.type === 'fortigate'))
  const hasWorkspaceIntegrations = computed(() => integrations.value.length > 0)
  const connectedIntegrationTypes = computed(() => {
    return Array.from(new Set(
      integrations.value
        .map(item => item.type)
        .filter((type): type is string => typeof type === 'string' && type.length > 0),
    ))
  })

  async function fetchIntegrations() {
    isLoading.value = true
    error.value = null
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch('/api/integrations', {
        headers: { 'X-CSRF-Token': authStore.csrfToken },
        credentials: 'include'
      })
      
      if (res.ok) {
        const data = await res.json()
        integrations.value = data.items || []
        await Promise.all(
          integrations.value
            .filter(integration => integration.type === 'fortigate')
            .map(integration => fetchFortigateIngestionStatus(integration.id)),
        )
      } else {
        error.value = 'Failed to load integrations'
      }
    } catch (e) {
      error.value = 'Network error while loading integrations'
    } finally {
      isLoading.value = false
    }
  }

  async function testFortigate(host: string, apiKey: string, verifyTls: boolean) {
    isTesting.value = true
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch('/api/integrations/fortigate/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify({ host, apiKey, verifyTls })
      })

      if (res.ok) {
        const data = await res.json()
        if (data.ok === true) {
          return { success: true, data }
        }
        return { success: false, error: data.error?.message ?? 'Connection failed' }
      }
      if (res.status === 401) await useAuthStore().fetchSession()
      return { success: false, error: await responseErrorMessage(res, 'Connection failed') }
    } catch (e) {
      return { success: false, error: 'Network error' }
    } finally {
      isTesting.value = false
    }
  }

  async function addFortigate(name: string, host: string, apiKey: string, verifyTls: boolean) {
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const collectorHost = window.location.hostname && window.location.hostname !== 'localhost'
        ? window.location.hostname
        : undefined
      const res = await fetch('/api/integrations/fortigate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify({ name, host, apiKey, verifyTls, collectorHost })
      })

      if (res.ok) {
        const data = await res.json()
        // Replace existing with same ID or add new
        const idx = integrations.value.findIndex(i => i.id === data.id)
        if (idx >= 0) integrations.value[idx] = data
        else integrations.value.push(data)
        await fetchFortigateIngestionStatus(data.id)
        
        return { success: true, data }
      }
      if (res.status === 401) await useAuthStore().fetchSession()
      return { success: false, error: await responseErrorMessage(res, 'Failed to add integration') }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  async function testPenguinTool(type: PenguinToolType) {
    isTesting.value = true
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch('/api/integrations/penguin-tools/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify({ type })
      })

      if (res.ok) {
        const data = await res.json()
        if (data.ok === true) {
          return { success: true, data }
        }
        return { success: false, error: data.error?.message ?? 'Connection failed' }
      }
      if (res.status === 401) await useAuthStore().fetchSession()
      return { success: false, error: await responseErrorMessage(res, 'Connection failed') }
    } catch (e) {
      return { success: false, error: 'Network error' }
    } finally {
      isTesting.value = false
    }
  }

  async function addPenguinTool(type: PenguinToolType, name?: string) {
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const body: { type: PenguinToolType, name?: string } = { type }
      if (name?.trim()) body.name = name.trim()

      const res = await fetch('/api/integrations/penguin-tools', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify(body)
      })

      if (res.ok) {
        const data = await res.json()
        const idx = integrations.value.findIndex(i => i.id === data.id)
        if (idx >= 0) integrations.value[idx] = data
        else integrations.value.push(data)

        return { success: true, data }
      }
      return { success: false, error: await responseErrorMessage(res, 'Failed to add integration') }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  async function removeIntegration(integrationId: string) {
    isDeleting.value[integrationId] = true
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch(`/api/integrations/${encodeURIComponent(integrationId)}`, {
        method: 'DELETE',
        headers: { 'X-CSRF-Token': authStore.csrfToken },
        credentials: 'include',
      })

      if (res.ok) {
        const data = await res.json()
        integrations.value = integrations.value.filter(item => item.id !== integrationId)
        delete ingestionStatusById.value[integrationId]
        return { success: true, data }
      }
      return { success: false, error: await responseErrorMessage(res, 'Failed to remove integration') }
    } catch (e) {
      return { success: false, error: 'Network error' }
    } finally {
      delete isDeleting.value[integrationId]
    }
  }

  async function fetchFortigateIngestionStatus(integrationId: string) {
    try {
      const res = await fetch(`/api/soc/fortigate/${encodeURIComponent(integrationId)}/ingestion-status`, {
        credentials: 'include',
      })
      if (!res.ok) return { success: false, error: await responseErrorMessage(res, 'Failed to load ingestion status') }
      const data = await res.json()
      if (isFortiGateIngestionStatus(data)) {
        ingestionStatusById.value[integrationId] = data
      }
      return { success: true, data }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  async function configureFortigateIngestion(
    integrationId: string,
    payload: { enabled: boolean, intervalSeconds: number },
  ) {
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch(`/api/soc/fortigate/${encodeURIComponent(integrationId)}/ingestion-status`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        return { success: false, error: await responseErrorMessage(res, 'Failed to configure ingestion') }
      }
      const data = await res.json()
      if (isFortiGateIngestionStatus(data)) {
        ingestionStatusById.value[integrationId] = data
      }
      return { success: true, data }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  async function runFortigateIngestion(integrationId: string) {
    isIngesting.value[integrationId] = true
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch(`/api/soc/fortigate/${encodeURIComponent(integrationId)}/ingest-events`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': authStore.csrfToken },
        credentials: 'include',
      })
      if (!res.ok) {
        return { success: false, error: await responseErrorMessage(res, 'Failed to ingest events') }
      }
      const data = await res.json()
      if (isFortiGateIngestionStatus(data.ingestion)) {
        ingestionStatusById.value[integrationId] = data.ingestion
      }
      return { success: true, data }
    } catch (e) {
      return { success: false, error: 'Network error' }
    } finally {
      delete isIngesting.value[integrationId]
    }
  }

  async function preflightFortigatePolicy(
    integrationId: string,
    payload: FortiGatePolicyPayload,
  ): Promise<{ success: true, data: FortiGatePolicyPreflightResponse } | { success: false, error: string }> {
    return postFortigatePolicy<FortiGatePolicyPreflightResponse>(integrationId, 'preflight', payload)
  }

  async function createFortigatePolicyReview(
    integrationId: string,
    payload: FortiGatePolicyPayload,
  ): Promise<{ success: true, data: FortiGatePolicyReviewResponse } | { success: false, error: string }> {
    return postFortigatePolicy<FortiGatePolicyReviewResponse>(integrationId, 'review', payload)
  }

  async function applyFortigatePolicy(
    integrationId: string,
    payload: { request_id: string, review_hash: string },
  ): Promise<{ success: true, data: FortiGatePolicyApplyResponse } | { success: false, error: string }> {
    return postFortigatePolicy<FortiGatePolicyApplyResponse>(integrationId, 'apply', payload)
  }

  async function postFortigatePolicy<T>(
    integrationId: string,
    action: 'preflight' | 'review' | 'apply',
    payload: Record<string, unknown>,
  ): Promise<{ success: true, data: T } | { success: false, error: string }> {
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch(`/api/integrations/fortigate/${encodeURIComponent(integrationId)}/policy/${action}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        return { success: false, error: await responseErrorMessage(res, 'Failed to configure FortiGate policy') }
      }
      return { success: true, data: await res.json() }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  async function fetchFortigateLogForwardingStatus(
    integrationId: string,
  ): Promise<{ success: true, data: FortiGateLogForwardingResponse } | { success: false, error: string }> {
    try {
      const res = await fetch(`/api/integrations/fortigate/${encodeURIComponent(integrationId)}/log-forwarding/status`, {
        credentials: 'include',
      })
      if (!res.ok) {
        return { success: false, error: await responseErrorMessage(res, 'Failed to load FortiGate log forwarding status') }
      }
      return { success: true, data: await res.json() }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  async function applyFortigateLogForwarding(
    integrationId: string,
    payload: FortiGateLogForwardingRequest & { confirmed: true },
  ): Promise<{ success: true, data: FortiGateLogForwardingResponse } | { success: false, error: string }> {
    return postFortigateLogForwarding(integrationId, 'apply', payload)
  }

  async function testFortigateLogForwardingCollector(
    integrationId: string,
    payload: Pick<FortiGateLogForwardingRequest, 'collectorHost' | 'port'>,
  ): Promise<{ success: true, data: FortiGateCollectorTestResponse } | { success: false, error: string }> {
    return postFortigateLogForwarding(integrationId, 'test-collector', payload) as Promise<
      { success: true, data: FortiGateCollectorTestResponse } | { success: false, error: string }
    >
  }

  async function postFortigateLogForwarding(
    integrationId: string,
    action: 'apply' | 'test-collector',
    payload: FortiGateLogForwardingRequest | Pick<FortiGateLogForwardingRequest, 'collectorHost' | 'port'>,
  ): Promise<{ success: true, data: FortiGateLogForwardingResponse } | { success: false, error: string }> {
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch(`/api/integrations/fortigate/${encodeURIComponent(integrationId)}/log-forwarding/${action}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        return { success: false, error: await responseErrorMessage(res, 'Failed to configure FortiGate log forwarding') }
      }
      return { success: true, data: await res.json() }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  return {
    integrations,
    isLoading,
    isTesting,
    isDeleting,
    isIngesting,
    ingestionStatusById,
    error,
    hasFortigate,
    hasWorkspaceIntegrations,
    connectedIntegrationTypes,
    fetchIntegrations,
    testFortigate,
    addFortigate,
    testPenguinTool,
    addPenguinTool,
    removeIntegration,
    fetchFortigateIngestionStatus,
    configureFortigateIngestion,
    runFortigateIngestion,
    preflightFortigatePolicy,
    createFortigatePolicyReview,
    applyFortigatePolicy,
    fetchFortigateLogForwardingStatus,
    applyFortigateLogForwarding,
    testFortigateLogForwardingCollector,
  }
})

function isFortiGateIngestionStatus(value: any): value is FortiGateIngestionStatus {
  return Boolean(
    value
      && typeof value === 'object'
      && typeof value.integrationId === 'string'
      && typeof value.status === 'string'
      && typeof value.intervalSeconds === 'number',
  )
}

async function responseErrorMessage(response: Response, fallback: string) {
  if (response.status === 401) {
    return 'Session expired. Please sign in again.'
  }
  if (response.status === 403) {
    return 'CSRF validation failed. Refresh the page and try again.'
  }
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      return body.detail[0]?.msg ?? fallback
    }
  } catch (e) {
    return fallback
  }
  return fallback
}
