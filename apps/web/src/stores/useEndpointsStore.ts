import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createEndpointEnrollment,
  deleteEndpoint,
  getEndpointRelatedIncidents,
  getEndpointTimeline,
  listEndpoints,
  type Endpoint,
  type EndpointEnrollment,
  type EndpointEnrollmentRequest,
  type EndpointRelatedIncident,
  type EndpointTimelineItem,
} from '../services/endpointsClient'

function latestCount(timeline: EndpointTimelineItem[], eventType: string, key: string) {
  const item = timeline.find((entry) => entry.eventType === eventType)
  const values = item?.attributes?.[key]
  return Array.isArray(values) ? values.length : 0
}

function sameText(left: string | null | undefined, right: string | null | undefined) {
  return Boolean(left && right && left.toLocaleLowerCase() === right.toLocaleLowerCase())
}

function isAtOrAfter(value: string | null | undefined, floor: string) {
  if (!value) return false
  const valueMs = Date.parse(value)
  const floorMs = Date.parse(floor)
  return Number.isFinite(valueMs) && Number.isFinite(floorMs) && valueMs >= floorMs
}

function endpointMatchesPending(endpoint: Endpoint, pending: PendingEnrollment) {
  if (endpoint.id === pending.enrollmentId) return true
  if (
    pending.hostnameHint
    && sameText(endpoint.hostname, pending.hostnameHint)
    && isAtOrAfter(endpoint.lastSeenAt, pending.createdAt)
  ) {
    return true
  }
  return false
}

export type PendingEnrollment = {
  enrollmentId: string
  displayName: string
  hostnameHint: string | null
  createdAt: string
  enrollmentToken: string
  status: 'pending' | 'online'
}

export const useEndpointsStore = defineStore('endpoints', () => {
  const endpoints = ref<Endpoint[]>([])
  const pendingEnrollments = ref<PendingEnrollment[]>([])
  const selectedEndpointId = ref<string | null>(null)
  const timeline = ref<EndpointTimelineItem[]>([])
  const relatedIncidents = ref<EndpointRelatedIncident[]>([])
  const isLoading = ref(false)
  const isLoadingTimeline = ref(false)
  const isLoadingRelatedIncidents = ref(false)
  const error = ref<string | null>(null)
  const relatedIncidentsError = ref<string | null>(null)

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

  function resolvePendingEnrollments() {
    pendingEnrollments.value = pendingEnrollments.value.filter((pending) => {
      return !endpoints.value.some((endpoint) => endpointMatchesPending(endpoint, pending))
    })
  }

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      endpoints.value = await listEndpoints()
      resolvePendingEnrollments()
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

  async function createEnrollment(payload: EndpointEnrollmentRequest): Promise<EndpointEnrollment> {
    const enrollment = await createEndpointEnrollment(payload)
    pendingEnrollments.value.push({
      enrollmentId: enrollment.id,
      displayName: enrollment.displayName ?? payload.displayName ?? enrollment.hostnameHint ?? 'Windows endpoint',
      hostnameHint: enrollment.hostnameHint ?? payload.hostnameHint ?? null,
      createdAt: enrollment.createdAt,
      enrollmentToken: enrollment.token,
      status: 'pending',
    })
    return enrollment
  }

  function forgetEnrollmentToken(enrollmentId: string) {
    pendingEnrollments.value = pendingEnrollments.value.map((pending) => {
      if (pending.enrollmentId !== enrollmentId) return pending
      return { ...pending, enrollmentToken: '' }
    })
  }

  function dismissPendingEnrollment(enrollmentId: string) {
    pendingEnrollments.value = pendingEnrollments.value.filter((pending) => (
      pending.enrollmentId !== enrollmentId
    ))
  }

  async function removeEndpoint(endpointId: string) {
    await deleteEndpoint(endpointId)
    endpoints.value = endpoints.value.filter((endpoint) => endpoint.id !== endpointId)
    if (selectedEndpointId.value === endpointId) {
      selectedEndpointId.value = endpoints.value[0]?.id ?? null
      timeline.value = []
      relatedIncidents.value = []
      if (selectedEndpointId.value) {
        await loadTimeline(selectedEndpointId.value)
      }
    }
  }

  async function selectEndpoint(endpointId: string) {
    selectedEndpointId.value = endpointId
    await loadTimeline(endpointId)
  }

  return {
    endpoints,
    pendingEnrollments,
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
    createEnrollment,
    forgetEnrollmentToken,
    dismissPendingEnrollment,
    removeEndpoint,
    selectEndpoint,
  }
})
