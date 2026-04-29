<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { X, GripHorizontal, Loader2, AlertCircle, AlertTriangle, Clock3, WifiOff } from 'lucide-vue-next'
import { fetchWidgetData } from '../../services/widgetDataClient'
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

const isDragging = ref(false)
const zoom = computed(() => store.zoom)

const isLoading = ref(true)
const isRefreshing = ref(false)
const fetchError = ref<string | null>(null)
const fetchErrorKind = ref<WidgetDataErrorKind | null>(null)
const widgetData = ref<any>(null)
const widgetResponse = ref<WidgetDataResponse | null>(null)
const catalogItem = computed(() => store.catalogItems.find(c => c.id === props.catalogId))
const visualTemplate = computed(() => visualTemplatesById[props.catalogId])
const isVisualTemplate = computed(() => Boolean(visualTemplate.value))
const widgetTitle = computed(() => catalogItem.value?.title ?? visualTemplate.value?.title ?? props.catalogId)

let currentController: AbortController | null = null
let requestId = 0
let refreshTimeout: ReturnType<typeof setTimeout> | null = null

function clearRefreshTimeout() {
  if (refreshTimeout) {
    clearTimeout(refreshTimeout)
    refreshTimeout = null
  }
}

function scheduleRefresh(response?: { meta?: { refreshIntervalSeconds?: number } }) {
  clearRefreshTimeout()
  const refreshIntervalSeconds = response?.meta?.refreshIntervalSeconds
  if (!refreshIntervalSeconds || refreshIntervalSeconds <= 0) return

  refreshTimeout = setTimeout(() => {
    loadWidgetData({ showLoading: false })
  }, refreshIntervalSeconds * 1000)
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
const isEmpty = computed(() => !isLoading.value && !fetchError.value && hasWidgetData.value && !hasRenderableData.value)

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

const lastUpdatedAge = computed(() => {
  const refreshedAt = widgetResponse.value?.refreshedAt
  if (!refreshedAt) return null

  const elapsedMs = Date.now() - new Date(refreshedAt).getTime()
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return null

  const elapsedSeconds = Math.floor(elapsedMs / 1000)
  if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`

  const elapsedMinutes = Math.floor(elapsedSeconds / 60)
  if (elapsedMinutes < 60) return `${elapsedMinutes}m ago`

  const elapsedHours = Math.floor(elapsedMinutes / 60)
  return `${elapsedHours}h ago`
})

async function loadWidgetData(options: { showLoading?: boolean } = {}) {
  const showLoading = options.showLoading ?? true
  requestId += 1
  const currentRequestId = requestId
  currentController?.abort()
  currentController = null
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

  const controller = new AbortController()
  currentController = controller
  if (showLoading) {
    isLoading.value = true
  }

  try {
    const result = await fetchWidgetData({
      dataEndpoint: catalogItem.value.dataEndpoint,
      integrationId: props.integrationId,
      signal: controller.signal,
    })

    if (currentRequestId !== requestId || controller.signal.aborted) return

    if (result.state === 'ready') {
      widgetData.value = result.data
      widgetResponse.value = result.response
    } else {
      fetchError.value = result.errorMessage
      fetchErrorKind.value = result.errorKind
      if (!widgetResponse.value && result.response) {
        widgetResponse.value = result.response
      }
    }
    scheduleRefresh(result.response || widgetResponse.value || undefined)
  } catch (e: any) {
    if (controller.signal.aborted) return
    fetchError.value = e.message || 'Network Error'
    fetchErrorKind.value = 'network'
    scheduleRefresh(widgetResponse.value || undefined)
  } finally {
    if (currentRequestId === requestId) {
      isLoading.value = false
      isRefreshing.value = false
      currentController = null
    }
  }
}

watch(
  [catalogItem, visualTemplate, () => props.integrationId, () => store.catalogItems.length],
  () => {
    loadWidgetData()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  requestId += 1
  clearRefreshTimeout()
  currentController?.abort()
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
      class="h-10 bg-theme-bg/80 border-b border-theme-border flex items-center justify-between px-3 cursor-move select-none rounded-t-md"
      @pointerdown="startDrag"
    >
      <div class="flex items-center gap-2 text-theme-text-muted">
        <GripHorizontal :size="16" />
        <span class="text-xs font-semibold text-theme-text uppercase tracking-wider">{{ widgetTitle }}</span>
      </div>
      <button @click.stop="handleRemove" class="text-theme-text-muted hover:text-theme-primary transition-colors" title="Remove Widget">
        <X :size="16" />
      </button>
    </div>

    <!-- Content slot -->
    <div class="flex-1 p-4 overflow-hidden relative pointer-events-auto bg-gradient-to-br from-transparent to-black/10 rounded-b-md">
      <div class="absolute top-2 right-3 z-10 flex items-center gap-2 text-[10px] text-theme-text-muted pointer-events-none">
        <div v-if="isRefreshing" class="flex items-center gap-1 text-theme-primary">
          <Loader2 :size="12" class="animate-spin" />
          <span>Refreshing</span>
        </div>
        <div v-if="lastUpdatedLabel" class="flex items-center gap-1">
          <Clock3 :size="12" />
          <span>Updated {{ lastUpdatedLabel }}</span>
          <span v-if="lastUpdatedAge">({{ lastUpdatedAge }})</span>
        </div>
      </div>

      <div v-if="isLoading" class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-theme-text-muted bg-theme-panel/70 backdrop-blur-sm z-20">
        <Loader2 :size="24" class="animate-spin text-theme-primary" />
        <span class="text-xs">Loading widget data...</span>
      </div>
      <div v-else-if="isBlockingError" class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-red-300 bg-red-950/25 backdrop-blur-sm z-20 p-4 text-center">
        <component :is="statusIcon" :size="24" />
        <span class="text-xs font-semibold">{{ fetchErrorKind === 'invalid_connection' ? 'Connection invalid' : 'Widget unavailable' }}</span>
        <span class="text-xs text-red-200/90">{{ fetchError }}</span>
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
