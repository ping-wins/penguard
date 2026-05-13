import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  getEndpointRelatedIncidents,
  getEndpointTimeline,
  listEndpoints,
  type Endpoint,
  type EndpointRelatedIncident,
  type EndpointTimelineItem,
} from '../services/endpointsClient'

function latestCount(timeline: EndpointTimelineItem[], eventType: string, key: string) {
  const item = timeline.find((entry) => entry.eventType === eventType)
  const values = item?.attributes?.[key]
  return Array.isArray(values) ? values.length : 0
}

export const useEndpointsStore = defineStore('endpoints', () => {
  const endpoints = ref<Endpoint[]>([])
  const selectedEndpointId = ref<string | null>(null)
  const timeline = ref<EndpointTimelineItem[]>([])
  const relatedIncidents = ref<EndpointRelatedIncident[]>([])
  const isLoading = ref(false)
  const isLoadingTimeline = ref(false)
  const isLoadingRelatedIncidents = ref(false)
  const error = ref<string | null>(null)
  const relatedIncidentsError = ref<string | null>(null)
  let pollHandle: ReturnType<typeof setInterval> | null = null

  const selectedEndpoint = computed(() => {
    if (!selectedEndpointId.value) return null
    return endpoints.value.find((endpoint) => endpoint.id === selectedEndpointId.value) ?? null
  })
  const latestConnectionCount = computed(() => (
    latestCount(timeline.value, 'connection.snapshot', 'connections')
  ))
  const latestProcessCount = computed(() => (
    latestCount(timeline.value, 'process.snapshot', 'processes')
  ))

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      endpoints.value = await listEndpoints()
      if (!selectedEndpointId.value && endpoints.value.length > 0) {
        selectedEndpointId.value = endpoints.value[0].id
      }
      if (selectedEndpointId.value) {
        await loadTimeline(selectedEndpointId.value)
      }
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load endpoints'
    } finally {
      isLoading.value = false
    }
  }

  async function loadTimeline(endpointId: string) {
    isLoadingTimeline.value = true
    isLoadingRelatedIncidents.value = true
    relatedIncidentsError.value = null
    try {
      const [timelineResult, relatedResult] = await Promise.allSettled([
        getEndpointTimeline(endpointId),
        getEndpointRelatedIncidents(endpointId),
      ])
      if (timelineResult.status === 'fulfilled') {
        timeline.value = timelineResult.value
      } else {
        error.value = timelineResult.reason?.message ?? 'Failed to load endpoint timeline'
        timeline.value = []
      }
      if (relatedResult.status === 'fulfilled') {
        relatedIncidents.value = relatedResult.value.items
      } else {
        relatedIncidentsError.value = relatedResult.reason?.message ?? 'Failed to load related incidents'
        relatedIncidents.value = []
      }
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load endpoint timeline'
      timeline.value = []
      relatedIncidents.value = []
    } finally {
      isLoadingTimeline.value = false
      isLoadingRelatedIncidents.value = false
    }
  }

  async function selectEndpoint(endpointId: string) {
    selectedEndpointId.value = endpointId
    await loadTimeline(endpointId)
  }

  function startPolling(intervalMs = 10000) {
    stopPolling()
    refresh()
    pollHandle = setInterval(refresh, intervalMs)
  }

  function stopPolling() {
    if (pollHandle !== null) {
      clearInterval(pollHandle)
      pollHandle = null
    }
  }

  return {
    endpoints,
    selectedEndpointId,
    selectedEndpoint,
    timeline,
    relatedIncidents,
    isLoading,
    isLoadingTimeline,
    isLoadingRelatedIncidents,
    error,
    relatedIncidentsError,
    latestConnectionCount,
    latestProcessCount,
    refresh,
    selectEndpoint,
    startPolling,
    stopPolling,
  }
})
