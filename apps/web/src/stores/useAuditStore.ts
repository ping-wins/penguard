import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { AuditApiError, fetchAuditEvents, type AuditEvent, type AuditScope } from '../services/auditClient'

export const useAuditStore = defineStore('audit', () => {
  const events = ref<AuditEvent[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const scope = ref<AuditScope>('mine')

  const isEmpty = computed(() => !isLoading.value && events.value.length === 0)

  async function fetchEvents(options: number | { limit?: number, scope?: AuditScope } = 50) {
    const nextLimit = typeof options === 'number' ? options : options.limit ?? 50
    const nextScope = typeof options === 'number' ? scope.value : options.scope ?? scope.value
    isLoading.value = true
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
      isLoading.value = false
    }
  }

  return {
    events,
    isLoading,
    error,
    scope,
    isEmpty,
    fetchEvents,
  }
})
