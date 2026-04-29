import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { AuditApiError, fetchAuditEvents, type AuditEvent, type AuditScope } from '../services/auditClient'

type FetchEventsOptions = {
  limit?: number
  scope?: AuditScope
  silent?: boolean
}

type PollingOptions = FetchEventsOptions & {
  intervalMs?: number
}

export const useAuditStore = defineStore('audit', () => {
  const events = ref<AuditEvent[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const scope = ref<AuditScope>('mine')
  const isPolling = ref(false)
  let pollingTimer: ReturnType<typeof setInterval> | null = null

  const isEmpty = computed(() => !isLoading.value && events.value.length === 0)

  async function fetchEvents(options: number | FetchEventsOptions = 50) {
    const nextLimit = typeof options === 'number' ? options : options.limit ?? 50
    const nextScope = typeof options === 'number' ? scope.value : options.scope ?? scope.value
    const silent = typeof options === 'number' ? false : options.silent ?? false
    if (!silent) {
      isLoading.value = true
    }
    error.value = null
    scope.value = nextScope
    try {
      const response = await fetchAuditEvents({ limit: nextLimit, scope: nextScope })
      events.value = response.items
    } catch (caught) {
      error.value = caught instanceof AuditApiError
        ? caught.message
        : 'Unable to load audit trail'
    } finally {
      if (!silent) {
        isLoading.value = false
      }
    }
  }

  function stopPolling() {
    if (pollingTimer !== null) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
    isPolling.value = false
  }

  function startPolling(options: PollingOptions = {}) {
    stopPolling()
    const limit = options.limit ?? 50
    const nextScope = options.scope ?? scope.value
    const intervalMs = options.intervalMs ?? 5000
    isPolling.value = true
    void fetchEvents({ limit, scope: nextScope })
    pollingTimer = setInterval(() => {
      void fetchEvents({ limit, scope: nextScope, silent: true })
    }, intervalMs)
  }

  return {
    events,
    isLoading,
    error,
    scope,
    isPolling,
    isEmpty,
    fetchEvents,
    startPolling,
    stopPolling,
  }
})
