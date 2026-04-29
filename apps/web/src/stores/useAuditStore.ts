import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { AuditApiError, fetchAuditEvents, type AuditEvent } from '../services/auditClient'

export const useAuditStore = defineStore('audit', () => {
  const events = ref<AuditEvent[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const isEmpty = computed(() => !isLoading.value && events.value.length === 0)

  async function fetchEvents(limit = 50) {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchAuditEvents({ limit })
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
    isEmpty,
    fetchEvents,
  }
})
