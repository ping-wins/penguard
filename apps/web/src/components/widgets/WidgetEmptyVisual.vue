<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Activity, BarChart2, Database, Network, Table } from 'lucide-vue-next'
import { visualTemplatesById } from '../../constants/visualTemplates'
import { fetchWidgetData } from '../../services/widgetDataClient'
import type { WidgetDataResponse, WidgetFieldBinding } from '../../types/dashboard'

const props = defineProps<{
  catalogId: string
  integrationId?: string
  fieldBindings?: WidgetFieldBinding[]
}>()

type SourceSnapshot = {
  state: 'ready' | 'error'
  data: Record<string, unknown>
  response?: WidgetDataResponse
  errorMessage?: string
}

type ResolvedField = {
  binding: WidgetFieldBinding
  rawValue: unknown
  formattedValue: string
  numericValue: number | null
}

const template = computed(() => visualTemplatesById[props.catalogId])
const boundFields = computed(() => props.fieldBindings ?? [])
const sourceSnapshots = ref<Record<string, SourceSnapshot>>({})
const isLoadingLiveData = ref(false)

let requestId = 0
let refreshTimer: ReturnType<typeof setTimeout> | null = null

const sourceIds = computed(() => {
  return Array.from(new Set(
    boundFields.value
      .map(field => field.source)
      .filter(source => source.length > 0),
  ))
})

const icon = computed(() => {
  switch (template.value?.kind) {
    case 'card':
    case 'gauge':
      return Activity
    case 'table':
      return Table
    case 'bar':
    case 'line':
      return BarChart2
    case 'feed':
      return Database
    case 'list':
      return Network
    default:
      return BarChart2
  }
})

const resolvedFields = computed<ResolvedField[]>(() => {
  return boundFields.value.map((binding) => {
    const snapshot = sourceSnapshots.value[binding.source]
    const rawValue = extractFieldValue(snapshot?.data ?? {}, binding.fieldId)
    return {
      binding,
      rawValue,
      formattedValue: formatFieldValue(rawValue, binding),
      numericValue: numericValue(rawValue),
    }
  })
})

const primaryField = computed(() => resolvedFields.value[0] ?? null)
const numericFields = computed(() => resolvedFields.value.filter(field => field.numericValue !== null))
const sourceError = computed(() => Object.values(sourceSnapshots.value).find(snapshot => snapshot.state === 'error')?.errorMessage ?? null)

const barMax = computed(() => {
  if (numericFields.value.some(field => field.binding.unit === 'percent')) return 100
  const max = Math.max(...numericFields.value.map(field => field.numericValue ?? 0))
  return max > 0 ? max : 1
})

function clearRefreshTimer() {
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
}

function scheduleRefresh(intervalSeconds: number | null) {
  clearRefreshTimer()
  if (!intervalSeconds || intervalSeconds <= 0) return
  refreshTimer = setTimeout(() => {
    loadLiveData({ showLoading: false })
  }, intervalSeconds * 1000)
}

async function loadLiveData(options: { showLoading?: boolean } = {}) {
  requestId += 1
  const currentRequestId = requestId
  clearRefreshTimer()

  if (!props.integrationId || sourceIds.value.length === 0) {
    sourceSnapshots.value = {}
    isLoadingLiveData.value = false
    return
  }

  if (options.showLoading ?? true) {
    isLoadingLiveData.value = true
  }

  const results = await Promise.all(sourceIds.value.map(async (source) => {
    try {
      const result = await fetchWidgetData({
        dataEndpoint: `/api/widgets/${encodeURIComponent(source)}/data`,
        integrationId: props.integrationId ?? '',
      })
      return { source, result }
    } catch (error: any) {
      return {
        source,
        result: {
          state: 'error' as const,
          errorKind: 'network' as const,
          errorMessage: error?.message ?? 'Network Error',
        },
      }
    }
  }))

  if (currentRequestId !== requestId) return

  const nextSnapshots: Record<string, SourceSnapshot> = { ...sourceSnapshots.value }
  let nextRefreshInterval: number | null = null

  for (const { source, result } of results) {
    if (result.state === 'ready') {
      nextSnapshots[source] = {
        state: 'ready',
        data: result.data,
        response: result.response,
      }

      const refreshInterval = result.response.meta?.refreshIntervalSeconds
      if (refreshInterval && refreshInterval > 0) {
        nextRefreshInterval = nextRefreshInterval === null
          ? refreshInterval
          : Math.min(nextRefreshInterval, refreshInterval)
      }
    } else {
      nextSnapshots[source] = {
        state: 'error',
        data: nextSnapshots[source]?.data ?? {},
        response: 'response' in result ? result.response : undefined,
        errorMessage: result.errorMessage,
      }
    }
  }

  sourceSnapshots.value = nextSnapshots
  isLoadingLiveData.value = false
  scheduleRefresh(nextRefreshInterval)
}

function getPathValue(data: Record<string, unknown>, path: string) {
  const segments = path.split('.').filter(Boolean)
  let current: unknown = data

  for (const segment of segments) {
    if (Array.isArray(current)) {
      current = current
        .map(item => item && typeof item === 'object'
          ? (item as Record<string, unknown>)[segment]
          : undefined)
        .filter(value => value !== undefined)
      continue
    }

    if (!current || typeof current !== 'object' || !(segment in current)) {
      return undefined
    }

    current = (current as Record<string, unknown>)[segment]
  }

  return current
}

function extractFieldValue(data: Record<string, unknown>, fieldId: string) {
  const directValue = getPathValue(data, fieldId)
  if (directValue !== undefined) return directValue

  const segments = fieldId.split('.').filter(Boolean)
  for (let start = 1; start < segments.length; start += 1) {
    const value = getPathValue(data, segments.slice(start).join('.'))
    if (value !== undefined) return value
  }

  return undefined
}

function numericValue(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function formatFieldValue(value: unknown, binding: WidgetFieldBinding) {
  if (value === undefined || value === null) return '--'
  if (Array.isArray(value)) return `${value.length} items`

  const parsedNumber = numericValue(value)
  if (parsedNumber !== null) {
    if (binding.unit === 'percent') return `${Math.round(parsedNumber)}%`
    if (binding.unit === 'bytes') return formatBytes(parsedNumber)
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(parsedNumber)
  }

  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function formatBytes(value: number) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let amount = value
  let unitIndex = 0
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024
    unitIndex += 1
  }
  return `${amount.toFixed(amount >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

function barWidth(field: ResolvedField) {
  if (field.numericValue === null) return '0%'
  const width = Math.max(0, Math.min(100, (field.numericValue / barMax.value) * 100))
  return `${Math.round(width)}%`
}

function barTestId(field: ResolvedField) {
  return `custom-bar-${field.binding.fieldId}`
}

watch(
  () => `${props.integrationId ?? ''}|${sourceIds.value.join('|')}`,
  () => {
    loadLiveData()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  requestId += 1
  clearRefreshTimer()
})
</script>

<template>
  <div v-if="!boundFields.length" class="flex h-full flex-col items-center justify-center gap-3 text-center text-theme-text-muted">
    <div class="flex size-12 items-center justify-center rounded-md border border-dashed border-theme-border bg-theme-bg/60 text-theme-primary">
      <component :is="icon" :size="24" />
    </div>
    <div class="min-w-0">
      <h3 class="text-sm font-semibold text-theme-text">{{ template?.title ?? 'Empty visual' }}</h3>
      <p class="mt-1 max-w-[14rem] text-xs leading-relaxed">Drop a live data field here</p>
    </div>
    <span class="rounded border border-theme-border px-2 py-1 text-[10px] uppercase tracking-wider">
      {{ template?.kind ?? 'visual' }}
    </span>
  </div>

  <div v-else-if="template?.kind === 'card'" class="flex h-full flex-col justify-between gap-3 text-theme-text">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="truncate text-xs font-semibold uppercase tracking-wider text-theme-text-muted">{{ primaryField?.binding.label }}</p>
        <p class="mt-1 truncate text-[11px] text-theme-text-muted">{{ primaryField?.binding.source }}</p>
      </div>
      <div class="flex size-9 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="20" />
      </div>
    </div>

    <div>
      <div data-test="custom-card-value" class="truncate text-5xl font-semibold leading-none text-theme-text">
        {{ primaryField?.formattedValue ?? '--' }}
      </div>
      <div class="mt-2 flex items-center gap-2 text-xs text-theme-text-muted">
        <span v-if="primaryField?.binding.unit">{{ primaryField.binding.unit }}</span>
        <span v-if="isLoadingLiveData">Refreshing</span>
        <span v-if="sourceError" class="truncate text-amber-300">{{ sourceError }}</span>
      </div>
    </div>
  </div>

  <div v-else-if="template?.kind === 'bar'" class="flex h-full flex-col gap-3 text-theme-text">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ template.title }}</h3>
        <p class="truncate text-[11px] text-theme-text-muted">{{ numericFields.length }} live fields</p>
      </div>
      <div class="flex size-8 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="18" />
      </div>
    </div>

    <div class="flex min-h-0 flex-1 flex-col justify-center gap-3">
      <div v-for="field in numericFields" :key="field.binding.fieldId" class="grid grid-cols-[minmax(0,1fr)_3.5rem] items-center gap-3">
        <div class="min-w-0">
          <div class="mb-1 flex items-center justify-between gap-2 text-xs">
            <span class="truncate font-medium">{{ field.binding.label }}</span>
            <span class="shrink-0 tabular-nums text-theme-text-muted">{{ field.formattedValue }}</span>
          </div>
          <div class="h-3 overflow-hidden rounded-sm bg-theme-bg/80">
            <div
              :data-test="barTestId(field)"
              class="h-full rounded-sm bg-theme-primary shadow-[0_0_16px_rgba(0,255,136,0.18)]"
              :style="{ width: barWidth(field) }"
            />
          </div>
        </div>
        <div class="text-right text-[10px] uppercase tracking-wider text-theme-text-muted">{{ field.binding.unit ?? field.binding.type }}</div>
      </div>
    </div>

    <p v-if="sourceError" class="truncate text-xs text-amber-300">{{ sourceError }}</p>
  </div>

  <div v-else class="flex h-full flex-col justify-center gap-2 text-theme-text">
    <div
      v-for="field in resolvedFields"
      :key="field.binding.fieldId"
      class="rounded border border-theme-border bg-theme-bg/70 px-2 py-1.5"
    >
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="truncate text-xs font-semibold text-theme-text">{{ field.binding.label }}</div>
          <div class="mt-0.5 truncate text-[10px] text-theme-text-muted">
            {{ field.binding.type }}<template v-if="field.binding.unit"> / {{ field.binding.unit }}</template>
          </div>
        </div>
        <div class="shrink-0 text-sm font-semibold tabular-nums">{{ field.formattedValue }}</div>
      </div>
    </div>
  </div>
</template>
