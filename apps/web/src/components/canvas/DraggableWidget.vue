<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, onMounted } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { useIntegrationsStore } from '../../stores/useIntegrationsStore'
import { useRealtimeStore } from '../../stores/useRealtimeStore'
import { useWidgetSeriesStore } from '../../stores/useWidgetSeriesStore'
import { useWidgetRealtimeStore } from '../../stores/useWidgetRealtimeStore'
import type { RealtimeWidgetSnapshot } from '../../stores/useRealtimeStore'
import { X, GripHorizontal, Loader2, AlertCircle, AlertTriangle, Clock3, WifiOff, Plug, ChevronDown, Check } from 'lucide-vue-next'
import WidgetSkeleton from '../widgets/shell/WidgetSkeleton.vue'
import { fetchWidgetData } from '../../services/widgetDataClient'
import { queryClient } from '../../services/queryClient'
import { widgetDataKey } from '../../services/queryKeys'
import type { WidgetDataErrorKind, WidgetDataResponse, WidgetFieldBinding, WidgetLayout } from '../../types/dashboard'
import { visualTemplatesById } from '../../constants/visualTemplates'
import { parseFieldBindingTransfer } from '../../utils/fieldDrag'
import { clampWidgetLayoutSize } from '../../utils/widgetLayout'

const props = defineProps<{
  instanceId: string
  catalogId: string
  integrationId: string
  layout: WidgetLayout
  fieldBindings?: WidgetFieldBinding[]
}>()

const emit = defineEmits<{
  'field-drop': [{ instanceId: string, binding: WidgetFieldBinding }]
}>()

const store = useDashboardStore()
const integrationsStore = useIntegrationsStore()
const realtimeStore = useRealtimeStore()
const widgetSeriesStore = useWidgetSeriesStore()
const widgetRealtimeStore = useWidgetRealtimeStore()

const isDragging = ref(false)
const zoom = computed(() => store.zoom)
const isRebindOpen = ref(false)
const isRebinding = ref(false)
const rebindError = ref('')

const isLoading = ref(true)
const isRefreshing = ref(false)
const fetchError = ref<string | null>(null)
const fetchErrorKind = ref<WidgetDataErrorKind | null>(null)
const widgetData = ref<any>(null)
const widgetResponse = ref<WidgetDataResponse | null>(null)
const catalogItem = computed(() => store.catalogItems.find(c => c.id === props.catalogId))
const sharedWidgetSnapshot = computed(() => widgetRealtimeStore.getSnapshot(props.catalogId, props.integrationId))
const visualTemplate = computed(() => visualTemplatesById[props.catalogId])
const isVisualTemplate = computed(() => Boolean(visualTemplate.value))
const widgetTitle = computed(() => catalogItem.value?.title ?? visualTemplate.value?.title ?? props.catalogId)
const rendererOwnsEmptyState = computed(() => {
  const source = catalogItem.value?.source
  return source === 'siem_kowalski' || source === 'xdr_rico' || source === 'soar_skipper' || source === 'soc'
})

let refreshTimeout: ReturnType<typeof setTimeout> | null = null
let realtimeRefreshTimeout: ReturnType<typeof setTimeout> | null = null
let unsubscribeRealtime: (() => void) | null = null

type WidgetQueryError = Error & {
  errorKind?: WidgetDataErrorKind
  response?: WidgetDataResponse
}

const widgetQueryKey = computed(() => widgetDataKey(props.catalogId, {
  integrationId: props.integrationId,
  dataEndpoint: catalogItem.value?.dataEndpoint ?? null,
}))

const isWidgetQueryEnabled = computed(() =>
  !isVisualTemplate.value
  && Boolean(catalogItem.value?.dataEndpoint)
  && Boolean(props.integrationId)
)

function snapshotToWidgetResponse(snapshot: RealtimeWidgetSnapshot): WidgetDataResponse | null {
  if (!snapshot.widgetId || !snapshot.integrationId || !snapshot.data) return null
  return {
    widgetId: snapshot.widgetId,
    integrationId: snapshot.integrationId,
    refreshedAt: snapshot.refreshedAt || new Date().toISOString(),
    status: snapshot.status === 'error' ? 'error' : 'ready',
    data: snapshot.data,
    meta: snapshot.meta,
  }
}

const widgetQuery = useQuery<WidgetDataResponse, WidgetQueryError>({
  queryKey: widgetQueryKey,
  enabled: isWidgetQueryEnabled,
  retry: false,
  refetchInterval: false,
  refetchOnWindowFocus: false,
  initialData: () => {
    const snapshot = sharedWidgetSnapshot.value
    return snapshot ? snapshotToWidgetResponse(snapshot) ?? undefined : undefined
  },
  queryFn: async ({ signal }) => {
    const endpoint = catalogItem.value?.dataEndpoint
    if (!endpoint) throw new Error('Catalog item or endpoint not found')
    const result = await fetchWidgetData({
      dataEndpoint: endpoint,
      integrationId: props.integrationId,
      signal,
    })
    if (result.state === 'ready') return result.response
    const error = new Error(result.errorMessage) as WidgetQueryError
    error.errorKind = result.errorKind
    error.response = result.response
    throw error
  },
}, queryClient)

function clearRefreshTimeout() {
  if (refreshTimeout) {
    clearTimeout(refreshTimeout)
    refreshTimeout = null
  }
}

function scheduleRefresh(_response?: { meta?: { refreshIntervalSeconds?: number } }) {
  clearRefreshTimeout()
  // Do not run hidden per-widget polling loops. FortiGate security telemetry is
  // pushed into the backend through UDP syslog, and workspace widgets hydrate on
  // mount/rebind/navigation instead of hammering /api/widgets/*/data.
}

function scheduleRealtimeReload() {
  if (realtimeRefreshTimeout) return
  realtimeRefreshTimeout = setTimeout(() => {
    realtimeRefreshTimeout = null
    loadWidgetData({ showLoading: false })
  }, 400)
}

function applyRealtimeTicket(ticket: any) {
  if (!ticket || typeof ticket !== 'object') return false
  if (props.catalogId === 'soc-recent-incidents') {
    const current = widgetData.value && typeof widgetData.value === 'object' ? widgetData.value : {}
    const incidents = Array.isArray(current.incidents) ? current.incidents : []
    const alreadyPresent = incidents.some((incident: any) => incident?.id === ticket.id)
    const nextIncidents = alreadyPresent
      ? incidents.map((incident: any) => incident?.id === ticket.id ? ticket : incident)
      : [ticket, ...incidents]
    const nextData = {
      ...current,
      incidents: nextIncidents.slice(0, 10),
      count: (Number(current.count) || incidents.length) + (alreadyPresent ? 0 : 1),
    }
    applyRealtimeWidgetData(nextData)
    return true
  }
  if (props.catalogId === 'soc-incidents-by-severity') {
    const current = widgetData.value && typeof widgetData.value === 'object' ? widgetData.value : {}
    const severity = String(ticket.severity || 'informational').toLowerCase()
    const items = Array.isArray(current.items) ? [...current.items] : []
    const idx = items.findIndex((item: any) => String(item?.severity || '').toLowerCase() === severity)
    if (idx >= 0) {
      items[idx] = { ...items[idx], count: (Number(items[idx].count) || 0) + 1 }
    } else {
      items.push({ severity, count: 1 })
    }
    const nextData = {
      ...current,
      items,
      total: (Number(current.total) || 0) + 1,
    }
    applyRealtimeWidgetData(nextData)
    return true
  }
  return false
}

function applyRealtimeWidgetSnapshot(snapshot: RealtimeWidgetSnapshot) {
  if (!snapshot || snapshot.widgetId !== props.catalogId) return false
  if (snapshot.integrationId && snapshot.integrationId !== props.integrationId) return false
  if (!snapshot.data || typeof snapshot.data !== 'object') return false
  if (
    widgetResponse.value?.widgetId === snapshot.widgetId
    && widgetResponse.value?.integrationId === snapshot.integrationId
    && widgetResponse.value?.refreshedAt === snapshot.refreshedAt
  ) {
    return true
  }
  applyRealtimeWidgetData(snapshot.data, snapshot)
  return true
}

function applyRealtimeWidgetData(nextData: any, snapshot?: RealtimeWidgetSnapshot) {
  const status = snapshot?.status === 'error' ? 'error' : 'ready'
  const refreshedAt = snapshot?.refreshedAt || new Date().toISOString()
  widgetData.value = nextData
  widgetResponse.value = {
    widgetId: snapshot?.widgetId || props.catalogId,
    integrationId: snapshot?.integrationId || props.integrationId,
    status,
    data: nextData,
    refreshedAt,
    meta: snapshot?.meta || {
      source: catalogItem.value?.source ?? 'siem_kowalski',
      cacheTtlSeconds: 0,
      refreshIntervalSeconds: 0,
    },
  }
  fetchError.value = status === 'error'
    ? snapshot?.meta?.error?.message || 'Widget error occurred'
    : null
  fetchErrorKind.value = status === 'error' ? 'widget_error' : null
  isLoading.value = false
  isRefreshing.value = false
  widgetSeriesStore.recordSample(props.instanceId, props.catalogId, nextData, props.integrationId)
}

function applyWidgetResponse(response: WidgetDataResponse) {
  if (response.status === 'ready') {
    widgetData.value = response.data || {}
    widgetResponse.value = response
    fetchError.value = null
    fetchErrorKind.value = null
    widgetRealtimeStore.upsertSnapshot(response)
    widgetSeriesStore.recordSample(props.instanceId, props.catalogId, response.data || {}, props.integrationId)
  } else {
    fetchError.value = response.meta?.error?.message || 'Widget error occurred'
    fetchErrorKind.value = 'widget_error'
    if (!widgetResponse.value) widgetResponse.value = response
  }
  isLoading.value = false
  isRefreshing.value = false
  scheduleRefresh(response)
}

function applySharedWidgetSnapshot() {
  const snapshot = sharedWidgetSnapshot.value
  if (!snapshot) return false
  return applyRealtimeWidgetSnapshot(snapshot)
}

const hasWidgetData = computed(() => widgetData.value !== null && widgetData.value !== undefined)

const hasRenderableData = computed(() => {
  const data = widgetData.value
  if (!data || typeof data !== 'object') return Boolean(data)

  const values = Object.values(data)
  if (values.length === 0) return false

  return values.some((value) => {
    if (Array.isArray(value)) return value.length > 0
    if (value && typeof value === 'object') return Object.keys(value).length > 0
    return value !== null && value !== undefined && value !== ''
  })
})

const isBlockingError = computed(() => Boolean(fetchError.value) && !hasWidgetData.value)
const isStaleWarning = computed(() => Boolean(fetchError.value) && hasWidgetData.value)
const isEmpty = computed(() => (
  !rendererOwnsEmptyState.value
  && !isLoading.value
  && !fetchError.value
  && hasWidgetData.value
  && !hasRenderableData.value
))

const statusIcon = computed(() => {
  if (fetchErrorKind.value === 'invalid_connection') return WifiOff
  return AlertCircle
})

const lastUpdatedLabel = computed(() => {
  const refreshedAt = widgetResponse.value?.refreshedAt
  if (!refreshedAt) return null

  const date = new Date(refreshedAt)
  if (Number.isNaN(date.getTime())) return refreshedAt

  return date.toISOString().replace('T', ' ').slice(0, 19)
})

const ageTick = ref(Date.now())
let ageInterval: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  widgetRealtimeStore.startRealtime()
  ageInterval = setInterval(() => { ageTick.value = Date.now() }, 1000)
  unsubscribeRealtime = realtimeStore.subscribe((event) => {
    if (event.ticket && applyRealtimeTicket(event.ticket)) return
    if (!event.refresh?.includes('widgets')) return
    // A FortiGate syslog event updates SIEM-backed SOC widgets too. Do not
    // filter by the event integrationId here: workspace SOC widgets are often
    // bound to the siem_kowalski integration, while the realtime event carries
    // the originating FortiGate integration id.
    scheduleRealtimeReload()
  })
})

watch(
  sharedWidgetSnapshot,
  (snapshot) => {
    if (snapshot) applyRealtimeWidgetSnapshot(snapshot)
  },
)

const lastUpdatedAge = computed(() => {
  const refreshedAt = widgetResponse.value?.refreshedAt
  if (!refreshedAt) return null

  const elapsedMs = ageTick.value - new Date(refreshedAt).getTime()
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return null

  const elapsedSeconds = Math.floor(elapsedMs / 1000)
  if (elapsedSeconds < 5) return 'just now'
  if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`

  const elapsedMinutes = Math.floor(elapsedSeconds / 60)
  if (elapsedMinutes < 60) return `${elapsedMinutes}m ago`

  const elapsedHours = Math.floor(elapsedMinutes / 60)
  return `${elapsedHours}h ago`
})

async function loadWidgetData(options: { showLoading?: boolean } = {}) {
  const showLoading = options.showLoading ?? true
  clearRefreshTimeout()

  fetchError.value = null
  fetchErrorKind.value = null
  if (showLoading) {
    widgetData.value = null
    widgetResponse.value = null
    isRefreshing.value = false
  } else {
    isRefreshing.value = true
  }

  if (isVisualTemplate.value) {
    isLoading.value = false
    isRefreshing.value = false
    return
  }

  if (!catalogItem.value?.dataEndpoint) {
    if (!store.isCatalogLoaded && store.catalogItems.length === 0) {
      isLoading.value = true
      isRefreshing.value = false
      return
    }

    isLoading.value = false
    isRefreshing.value = false
    fetchError.value = 'Catalog item or endpoint not found'
    fetchErrorKind.value = 'widget_error'
    return
  }

  if (showLoading && applySharedWidgetSnapshot()) return

  if (showLoading) {
    isLoading.value = true
  }

  try {
    const result = await widgetQuery.refetch()
    if (result.data) applyWidgetResponse(result.data)
    if (result.error) throw result.error
  } catch (e: any) {
    fetchError.value = e.message || 'Network Error'
    fetchErrorKind.value = e.errorKind || 'network'
    if (!widgetResponse.value && e.response) widgetResponse.value = e.response
    scheduleRefresh(widgetResponse.value || undefined)
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

watch(
  () => widgetQuery.data.value,
  (response) => {
    if (response) applyWidgetResponse(response)
  },
  { immediate: true },
)

watch(
  () => widgetQuery.error.value,
  (error) => {
    if (!error) return
    fetchError.value = error.message || 'Network Error'
    fetchErrorKind.value = error.errorKind || 'network'
    if (!widgetResponse.value && error.response) widgetResponse.value = error.response
    isLoading.value = false
    isRefreshing.value = false
  },
)

watch(
  [isWidgetQueryEnabled, () => store.catalogItems.length, () => store.isCatalogLoaded],
  () => {
    if (isVisualTemplate.value) {
      isLoading.value = false
      isRefreshing.value = false
      return
    }
    if (isWidgetQueryEnabled.value || isVisualTemplate.value) return
    if (!catalogItem.value?.dataEndpoint && !store.isCatalogLoaded && store.catalogItems.length === 0) {
      isLoading.value = true
      return
    }
    if (!catalogItem.value?.dataEndpoint && store.isCatalogLoaded) {
      isLoading.value = false
      fetchError.value = 'Catalog item or endpoint not found'
      fetchErrorKind.value = 'widget_error'
    }
  },
  { immediate: true },
)

watch(
  () => widgetQuery.isFetching.value,
  (fetching) => {
    if (!fetching) return
    if (hasWidgetData.value) isRefreshing.value = true
    else isLoading.value = true
  },
  { immediate: true },
)

watch(
  () => props.integrationId,
  (next, previous) => {
    if (previous !== undefined && next !== previous) {
      widgetData.value = null
      widgetResponse.value = null
      fetchError.value = null
      fetchErrorKind.value = null
      isLoading.value = true
      isRefreshing.value = false
      widgetSeriesStore.clearInstance(props.instanceId)
    }
  },
)

onBeforeUnmount(() => {
  clearRefreshTimeout()
  if (realtimeRefreshTimeout) {
    clearTimeout(realtimeRefreshTimeout)
    realtimeRefreshTimeout = null
  }
  unsubscribeRealtime?.()
  unsubscribeRealtime = null
  widgetSeriesStore.clearInstance(props.instanceId)
  if (ageInterval) clearInterval(ageInterval)
})

const clampedLayout = computed(() => clampWidgetLayoutSize(props.layout, props.catalogId))
const widthPx = computed(() => clampedLayout.value.w)
const heightPx = computed(() => clampedLayout.value.h)

function handleRemove() {
  store.removeWidget(props.instanceId)
}

function bringToFront() {
  store.bringToFront(props.instanceId)
}

function handleFieldDragOver(event: DragEvent) {
  if (!isVisualTemplate.value) return
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

function handleFieldDrop(event: DragEvent) {
  if (!isVisualTemplate.value) return
  event.preventDefault()
  event.stopPropagation()
  const binding = parseFieldBindingTransfer(event.dataTransfer)
  if (!binding) return
  emit('field-drop', { instanceId: props.instanceId, binding })
}

let startX = 0
let startY = 0
let initialDragX = 0
let initialDragY = 0

function startDrag(e: PointerEvent) {
  isDragging.value = true
  bringToFront()
  
  startX = e.clientX
  startY = e.clientY
  initialDragX = props.layout.x
  initialDragY = props.layout.y
  
  window.addEventListener('pointermove', onDrag)
  window.addEventListener('pointerup', stopDrag)
  e.preventDefault()
}

function onDrag(e: PointerEvent) {
  if (!isDragging.value) return
  const dx = (e.clientX - startX) / zoom.value
  const dy = (e.clientY - startY) / zoom.value
  
  const newX = initialDragX + dx
  const newY = initialDragY + dy
  
  store.updateWidgetPosition(props.instanceId, newX, newY)
}

function stopDrag() {
  isDragging.value = false
  window.removeEventListener('pointermove', onDrag)
  window.removeEventListener('pointerup', stopDrag)
}

let startResizeX = 0
let startResizeY = 0
let initialW = 0
let initialH = 0
let initialX = 0
let initialY = 0
let resizeDir = ''

function startResize(e: PointerEvent, dir: string) {
  bringToFront()
  startResizeX = e.clientX
  startResizeY = e.clientY
  initialW = props.layout.w
  initialH = props.layout.h
  initialX = props.layout.x
  initialY = props.layout.y
  resizeDir = dir
  
  window.addEventListener('pointermove', onResize)
  window.addEventListener('pointerup', stopResize)
  e.preventDefault()
  e.stopPropagation()
}

function onResize(e: PointerEvent) {
  const dx = (e.clientX - startResizeX) / zoom.value
  const dy = (e.clientY - startResizeY) / zoom.value
  
  let newW = initialW
  let newH = initialH
  let newX = initialX
  let newY = initialY
  
  if (resizeDir.includes('e')) {
    newW = initialW + dx
  } else if (resizeDir.includes('w')) {
    newW = initialW - dx
  }
  
  if (resizeDir.includes('s')) {
    newH = initialH + dy
  } else if (resizeDir.includes('n')) {
    newH = initialH - dy
  }

  const clamped = clampWidgetLayoutSize(
    { x: newX, y: newY, w: newW, h: newH, z: props.layout.z },
    props.catalogId,
  )
  newW = clamped.w
  newH = clamped.h

  if (resizeDir.includes('w')) {
    newX = initialX + (initialW - newW)
  }
  if (resizeDir.includes('n')) {
    newY = initialY + (initialH - newH)
  }
  
  store.updateWidgetSize(props.instanceId, newW, newH)
  if (newX !== initialX || newY !== initialY) {
    store.updateWidgetPosition(props.instanceId, newX, newY)
  }
}

function stopResize() {
  window.removeEventListener('pointermove', onResize)
  window.removeEventListener('pointerup', stopResize)
}

const widgetProviderType = computed(() => {
  const source = catalogItem.value?.source ?? (catalogItem.value as any)?.integrationType
  if (source) return source
  const id = props.catalogId
  if (id.startsWith('fortigate-')) return 'fortigate'
  if (id.startsWith('siem-')) return 'siem_kowalski'
  if (id.startsWith('soar-')) return 'soar_skipper'
  if (id.startsWith('xdr-')) return 'xdr_rico'
  return null
})

const compatibleIntegrations = computed(() => {
  const type = widgetProviderType.value
  if (!type) return integrationsStore.integrations
  return integrationsStore.integrations.filter((i: any) => i.type === type)
})

const currentIntegration = computed(() =>
  integrationsStore.integrations.find((i: any) => i.id === props.integrationId) ?? null,
)

const currentIntegrationLabel = computed(() => {
  if (currentIntegration.value) return currentIntegration.value.name || currentIntegration.value.id
  if (!props.integrationId) return 'No integration'
  return props.integrationId
})

function toggleRebindMenu() {
  rebindError.value = ''
  isRebindOpen.value = !isRebindOpen.value
}

async function selectIntegration(integrationId: string) {
  if (integrationId === props.integrationId) {
    isRebindOpen.value = false
    return
  }
  rebindError.value = ''
  isRebinding.value = true
  try {
    await store.rebindWidget(props.instanceId, integrationId)
    isRebindOpen.value = false
    loadWidgetData({ showLoading: true })
  } catch (err: any) {
    rebindError.value = err?.message ?? 'Failed to rebind'
  } finally {
    isRebinding.value = false
  }
}
</script>

<template>
  <div
    data-workspace-widget="true"
    data-test="draggable-widget"
    class="absolute flex flex-col bg-theme-panel border border-theme-border rounded-md shadow-2xl transition-shadow group"
    :class="{ 'ring-2 ring-theme-primary/50 shadow-theme-primary/10': isDragging }"
    :style="{
      width: `${widthPx}px`,
      height: `${heightPx}px`,
      transform: `translate(${layout.x}px, ${layout.y}px)`,
      zIndex: layout.z
    }"
    @mousedown="bringToFront"
    v-motion
    :initial="{ opacity: 0, scale: 0.9, y: 20 }"
    :enter="{ opacity: 1, scale: 1, y: 0, transition: { type: 'spring', stiffness: 250, damping: 20 } }"
    @dragover="handleFieldDragOver"
    @drop="handleFieldDrop"
  >
    <!-- Header -->
    <div
      data-test="widget-drag-handle"
      class="h-10 bg-theme-bg/80 border-b border-theme-border flex items-center justify-between px-3 select-none rounded-t-md relative cursor-move"
      @pointerdown="startDrag"
    >
      <div class="flex items-center gap-2 text-theme-text-muted min-w-0">
        <GripHorizontal :size="16" />
        <span class="text-xs font-semibold text-theme-text uppercase tracking-wider truncate">{{ widgetTitle }}</span>
        <span
          v-if="isRefreshing"
          class="flex items-center gap-1 text-[10px] text-theme-primary"
          :title="lastUpdatedLabel ? `Last updated ${lastUpdatedLabel}` : undefined"
        >
          <Loader2 :size="11" class="animate-spin" />
          <span class="normal-case tracking-normal">Refreshing</span>
        </span>
        <span
          v-else-if="lastUpdatedAge"
          class="flex items-center gap-1 text-[10px] text-theme-text-muted normal-case tracking-normal"
          :title="lastUpdatedLabel ? `Last updated ${lastUpdatedLabel}` : undefined"
        >
          <Clock3 :size="11" />
          <span>{{ lastUpdatedAge }}</span>
        </span>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <div class="relative">
          <button
            type="button"
            @click.stop="toggleRebindMenu"
            @pointerdown.stop
            :class="[
              'flex items-center gap-1 px-2 py-1 rounded text-[10px] uppercase tracking-wider transition-colors',
              !props.integrationId
                ? 'border border-amber-500/50 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20'
                : 'text-theme-text-muted hover:bg-theme-border hover:text-theme-text border border-transparent',
            ]"
            :title="`Integration: ${currentIntegrationLabel}`"
          >
            <Plug :size="12" />
            <span class="max-w-[140px] truncate normal-case">{{ currentIntegrationLabel }}</span>
            <ChevronDown :size="11" />
          </button>
          <div
            v-if="isRebindOpen"
            class="absolute right-0 top-full mt-1 w-64 bg-theme-panel border border-theme-border rounded-md shadow-2xl z-50"
            @pointerdown.stop
            @click.stop
          >
            <div class="px-3 py-2 border-b border-theme-border text-[10px] uppercase tracking-wider text-theme-text-muted">
              Rebind widget integration
            </div>
            <ul v-if="compatibleIntegrations.length" class="max-h-56 overflow-auto">
              <li
                v-for="integration in compatibleIntegrations"
                :key="integration.id"
              >
                <button
                  type="button"
                  :disabled="isRebinding"
                  @click="selectIntegration(integration.id)"
                  class="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm text-theme-text hover:bg-theme-border/60 disabled:opacity-50"
                >
                  <div class="min-w-0">
                    <div class="truncate font-medium">{{ integration.name || integration.id }}</div>
                    <div class="text-xs text-theme-text-muted">{{ integration.type }}</div>
                  </div>
                  <Check v-if="integration.id === props.integrationId" :size="14" class="text-theme-primary shrink-0" />
                </button>
              </li>
            </ul>
            <div v-else class="px-3 py-3 text-xs text-theme-text-muted">
              No matching integration connected. Open the Integrations panel to add one.
            </div>
            <div v-if="rebindError" class="px-3 py-2 border-t border-red-500/30 bg-red-500/10 text-xs text-red-300">
              {{ rebindError }}
            </div>
          </div>
        </div>
        <button @click.stop="handleRemove" class="text-theme-text-muted hover:text-theme-primary transition-colors" title="Remove Widget">
          <X :size="16" />
        </button>
      </div>
    </div>

    <!-- Content slot -->
    <div class="flex-1 p-4 overflow-hidden relative pointer-events-auto bg-gradient-to-br from-transparent to-black/10 rounded-b-md">
      <div v-if="isLoading" class="absolute inset-0 z-20 bg-theme-panel/85 backdrop-blur-sm p-4">
        <WidgetSkeleton />
      </div>
      <div v-else-if="isBlockingError" class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-red-300 bg-red-950/25 backdrop-blur-sm z-20 p-4 text-center">
        <component :is="statusIcon" :size="24" />
        <span class="text-xs font-semibold">{{ fetchErrorKind === 'invalid_connection' ? 'Connection invalid' : 'Widget unavailable' }}</span>
        <span class="text-xs text-red-200/90">{{ fetchError }}</span>
        <button
          v-if="compatibleIntegrations.length"
          type="button"
          @click.stop="toggleRebindMenu"
          class="mt-2 inline-flex items-center gap-1 px-3 py-1 rounded border border-amber-400/40 bg-amber-400/15 text-amber-200 text-xs font-semibold hover:bg-amber-400/25"
        >
          <Plug :size="12" />
          Choose integration
        </button>
      </div>
      <div v-else-if="isEmpty" class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-theme-text-muted bg-theme-panel/45 backdrop-blur-[1px] z-20 p-4 text-center">
        <AlertCircle :size="22" class="text-theme-primary" />
        <span class="text-xs font-semibold text-theme-text">No data returned</span>
        <span class="text-xs">The widget endpoint responded successfully, but there is nothing to display yet.</span>
      </div>
      <template v-else>
        <div v-if="isStaleWarning" class="absolute left-3 right-3 top-3 z-20 flex items-start gap-2 rounded-md border border-amber-400/30 bg-amber-950/60 px-3 py-2 text-xs text-amber-100 shadow-lg backdrop-blur-sm">
          <AlertTriangle :size="15" class="mt-0.5 shrink-0 text-amber-300" />
          <div class="min-w-0">
            <div class="font-semibold">Showing last good data</div>
            <div class="truncate text-amber-100/90">{{ fetchError }}</div>
          </div>
        </div>
        <slot
          :widgetData="widgetData"
          :widgetMeta="widgetResponse?.meta"
          :refreshedAt="widgetResponse?.refreshedAt"
          :fieldBindings="fieldBindings ?? []"
        />
      </template>
    </div>

    <!-- Handles - Visíveis no hover do container -->
    <div class="opacity-0 group-hover:opacity-100 transition-opacity">
      <!-- Edges -->
      <div data-test="resize-handle-n" class="absolute top-0 left-2 right-2 h-1.5 cursor-ns-resize -translate-y-1/2" @pointerdown.stop="startResize($event, 'n')"></div>
      <div data-test="resize-handle-s" class="absolute bottom-0 left-2 right-2 h-1.5 cursor-ns-resize translate-y-1/2" @pointerdown.stop="startResize($event, 's')"></div>
      <div data-test="resize-handle-w" class="absolute top-2 bottom-2 left-0 w-1.5 cursor-ew-resize -translate-x-1/2" @pointerdown.stop="startResize($event, 'w')"></div>
      <div data-test="resize-handle-e" class="absolute top-2 bottom-2 right-0 w-1.5 cursor-ew-resize translate-x-1/2" @pointerdown.stop="startResize($event, 'e')"></div>
      
      <!-- Corners -->
      <div data-test="resize-handle-nw" class="absolute top-0 left-0 w-3 h-3 cursor-nwse-resize -translate-x-1/2 -translate-y-1/2 z-10" @pointerdown.stop="startResize($event, 'nw')"></div>
      <div data-test="resize-handle-ne" class="absolute top-0 right-0 w-3 h-3 cursor-nesw-resize translate-x-1/2 -translate-y-1/2 z-10" @pointerdown.stop="startResize($event, 'ne')"></div>
      <div data-test="resize-handle-sw" class="absolute bottom-0 left-0 w-3 h-3 cursor-nesw-resize -translate-x-1/2 translate-y-1/2 z-10" @pointerdown.stop="startResize($event, 'sw')"></div>
      
      <div 
        data-test="resize-handle-se"
        class="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize flex items-end justify-end p-0.5 hover:text-theme-primary transition-colors text-theme-text-muted z-10" 
        @pointerdown.stop="startResize($event, 'se')"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <path d="M21 15l-6 6M21 9l-12 12M21 3l-18 18" />
        </svg>
      </div>
    </div>
  </div>
</template>
