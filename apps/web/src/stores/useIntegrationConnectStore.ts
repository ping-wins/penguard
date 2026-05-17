import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useAuthStore } from './useAuthStore'

export type CatalogAuthField = {
  id: string
  label: string
  type: 'text' | 'url' | 'secret' | 'boolean' | 'number'
  required?: boolean
  default?: unknown
  placeholder?: string | null
}

export type CatalogEntry = {
  addonId: string
  name: string
  vendor: string
  category: string
  icon?: string | null
  providerType: string
  versions: string[]
  authFields: CatalogAuthField[]
  capabilities: {
    logSource: boolean
    playbookTarget: boolean
    managed: boolean
  }
}

export type ConnectPayload = {
  addonId: string
  version: string
  name: string
  auth: Record<string, unknown>
  wire?: {
    siem: boolean
    soar: boolean
  }
}

export const useIntegrationConnectStore = defineStore('integrationConnect', () => {
  const catalog = ref<CatalogEntry[]>([])
  const isLoading = ref(false)
  const isSubmitting = ref(false)
  const error = ref<string | null>(null)

  async function csrfHeaders() {
    const auth = useAuthStore()
    if (!auth.csrfToken) await auth.fetchCsrf()
    return {
      'Content-Type': 'application/json',
      'X-CSRF-Token': auth.csrfToken,
    }
  }

  async function fetchCatalog() {
    isLoading.value = true
    error.value = null
    try {
      const res = await fetch('/api/integrations/catalog', {
        credentials: 'include',
      })
      if (!res.ok) {
        if (res.status === 401) await useAuthStore().fetchSession()
        error.value = await responseErrorMessage(res, 'Failed to load catalog')
        return
      }
      const data = await res.json()
      catalog.value = Array.isArray(data.items) ? data.items : []
    } catch (e) {
      error.value = 'Network error while loading catalog'
    } finally {
      isLoading.value = false
    }
  }

  async function testConnection(payload: ConnectPayload) {
    try {
      const res = await fetch('/api/integrations/connect/test', {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok === true) return { success: true as const, data }
      if (res.status === 401) await useAuthStore().fetchSession()
      return {
        success: false as const,
        error: data.message ?? data.detail ?? 'Connection failed',
      }
    } catch (e) {
      return { success: false as const, error: 'Network error' }
    }
  }

  async function connect(payload: ConnectPayload) {
    isSubmitting.value = true
    try {
      const res = await fetch('/api/integrations/connect', {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) return { success: true as const, data }
      if (res.status === 401) await useAuthStore().fetchSession()
      return {
        success: false as const,
        error: data.detail ?? 'Failed to connect',
      }
    } catch (e) {
      return { success: false as const, error: 'Network error' }
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    catalog,
    isLoading,
    isSubmitting,
    error,
    fetchCatalog,
    testConnection,
    connect,
  }
})

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
