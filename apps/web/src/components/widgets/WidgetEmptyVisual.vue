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

type TableRow = {
  id: string
  label: string
  value: string
  source: string
}

type FeedRow = {
  id: string
  title: string
  detail: string
  meta: string
  severity: SignalSeverity
}

type SignalSeverity = 'normal' | 'elevated' | 'critical'

type SignalRow = {
  id: string
  label: string
  value: string
  source: string
  severity: SignalSeverity
  width: string
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

const gaugeValue = computed(() => {
  if (!primaryField.value || primaryField.value.numericValue === null) return 0
  return clamp(normalizeGaugeValue(primaryField.value), 0, 100)
})

const gaugeSeverity = computed(() => severityFromPercent(gaugeValue.value))

const tableRows = computed<TableRow[]>(() => {
  return resolvedFields.value.flatMap(field => tableRowsForField(field))
})

const feedRows = computed<FeedRow[]>(() => {
  return resolvedFields.value.flatMap(field => feedRowsForField(field))
})

const signalRows = computed<SignalRow[]>(() => {
  return resolvedFields.value.flatMap(field => signalRowsForField(field))
})

const linePoints = computed(() => {
  const fields = numericFields.value
  if (fields.length === 0) return []
  const max = barMax.value
  return fields.map((field, index) => {
    const x = fields.length === 1 ? 50 : 10 + (index / (fields.length - 1)) * 80
    const normalized = clamp(((field.numericValue ?? 0) / max) * 100, 0, 100)
    const y = 86 - (normalized * 0.72)
    return {
      id: field.binding.fieldId,
      x,
      y,
      label: field.binding.label,
      value: field.formattedValue,
    }
  })
})

const linePath = computed(() => {
  if (linePoints.value.length === 0) return ''
  return linePoints.value
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(' ')
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
    if (binding.unit === 'seconds' || binding.type === 'duration' || binding.fieldId.toLowerCase().includes('uptime')) {
      return formatDurationSeconds(parsedNumber)
    }
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

function formatDurationSeconds(value: number) {
  const totalSeconds = Math.max(0, Math.floor(value))
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const parts: string[] = []

  if (days > 0) parts.push(`${days}d`)
  if (hours > 0 || parts.length > 0) parts.push(`${hours}h`)
  if (minutes > 0 || parts.length > 0) parts.push(`${minutes}m`)
  if (parts.length === 0) parts.push(`${seconds}s`)

  return parts.slice(0, 3).join(' ')
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function normalizeGaugeValue(field: ResolvedField) {
  const value = field.numericValue ?? 0
  if (field.binding.unit === 'percent') return value
  if (value >= 0 && value <= 1) return value * 100
  return value
}

function barWidth(field: ResolvedField) {
  if (field.numericValue === null) return '0%'
  const width = Math.max(0, Math.min(100, (field.numericValue / barMax.value) * 100))
  return `${Math.round(width)}%`
}

function barTestId(field: ResolvedField) {
  return `custom-bar-${field.binding.fieldId}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function titleize(value: string) {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, letter => letter.toUpperCase())
}

function formatCellValue(value: unknown, binding?: WidgetFieldBinding, keyHint = ''): string {
  if (value === undefined || value === null) return '--'
  if (Array.isArray(value)) return `${value.length} items`

  const parsedNumber = numericValue(value)
  if (parsedNumber !== null) {
    if (binding?.unit === 'percent') return `${Math.round(parsedNumber)}%`
    if (binding?.unit === 'bytes' || keyHint.toLowerCase().includes('bytes')) return formatBytes(parsedNumber)
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(parsedNumber)
  }

  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (isRecord(value)) {
    const preview: string[] = Object.entries(value)
      .filter(([, entryValue]) => !isRecord(entryValue) && !Array.isArray(entryValue))
      .slice(0, 2)
      .map(([key, entryValue]) => `${titleize(key)} ${formatCellValue(entryValue)}`)
    return preview.length ? preview.join(' / ') : '--'
  }
  return String(value)
}

function tableRowsForField(field: ResolvedField): TableRow[] {
  if (!Array.isArray(field.rawValue)) {
    return [{
      id: field.binding.fieldId,
      label: field.binding.label,
      value: field.formattedValue,
      source: field.binding.source,
    }]
  }

  if (field.rawValue.length === 0) {
    return [{
      id: `${field.binding.fieldId}-empty`,
      label: field.binding.label,
      value: '0 items',
      source: field.binding.source,
    }]
  }

  return field.rawValue.flatMap((item, index) => {
    const prefix = `${field.binding.label} ${index + 1}`
    if (!isRecord(item)) {
      return [{
        id: `${field.binding.fieldId}-${index}`,
        label: prefix,
        value: formatCellValue(item),
        source: field.binding.source,
      }]
    }

    return Object.entries(item).map(([key, value]) => ({
      id: `${field.binding.fieldId}-${index}-${key}`,
      label: `${prefix} ${titleize(key)}`,
      value: formatCellValue(value, undefined, key),
      source: field.binding.source,
    }))
  })
}

function feedRowsForField(field: ResolvedField): FeedRow[] {
  if (!Array.isArray(field.rawValue)) {
    return [{
      id: field.binding.fieldId,
      title: field.binding.label,
      detail: field.formattedValue,
      meta: field.binding.source,
      severity: severityForField(field),
    }]
  }

  if (field.rawValue.length === 0) {
    return [{
      id: `${field.binding.fieldId}-empty`,
      title: field.binding.label,
      detail: '0 items',
      meta: field.binding.source,
      severity: 'normal',
    }]
  }

  return field.rawValue.map((item, index) => {
    if (!isRecord(item)) {
      return {
        id: `${field.binding.fieldId}-${index}`,
        title: field.binding.label,
        detail: formatCellValue(item),
        meta: field.binding.source,
        severity: 'normal' as const,
      }
    }

    return {
      id: `${field.binding.fieldId}-${index}`,
      title: objectTitle(item, field.binding.label),
      detail: objectDetail(item),
      meta: objectMeta(item, field.binding.source),
      severity: severityFromUnknown(item.severity ?? item.level ?? item.status),
    }
  })
}

function signalRowsForField(field: ResolvedField): SignalRow[] {
  if (!Array.isArray(field.rawValue)) {
    return [{
      id: field.binding.fieldId,
      label: field.binding.label,
      value: field.formattedValue,
      source: field.binding.groupName ?? field.binding.source,
      severity: severityForField(field),
      width: field.numericValue === null ? '0%' : barWidth(field),
    }]
  }

  return feedRowsForField(field).map(row => ({
    id: row.id,
    label: row.title,
    value: row.detail,
    source: row.meta,
    severity: row.severity,
    width: row.severity === 'critical' ? '100%' : row.severity === 'elevated' ? '66%' : '33%',
  }))
}

function objectTitle(item: Record<string, unknown>, fallback: string) {
  for (const key of ['message', 'summary', 'name', 'hostname', 'event', 'type', 'status']) {
    if (item[key] !== undefined && item[key] !== null) return formatCellValue(item[key])
  }
  const [firstKey, firstValue] = Object.entries(item)[0] ?? []
  return firstKey ? `${titleize(firstKey)} ${formatCellValue(firstValue)}` : fallback
}

function objectDetail(item: Record<string, unknown>) {
  const detailKeys = ['sourceIp', 'destinationIp', 'action', 'interface', 'policy', 'status']
  const parts = detailKeys
    .filter(key => item[key] !== undefined && item[key] !== null)
    .map(key => `${titleize(key)} ${formatCellValue(item[key])}`)
  if (parts.length) return parts.slice(0, 3).join(' / ')

  return Object.entries(item)
    .filter(([key]) => !['message', 'summary', 'name', 'severity', 'level'].includes(key))
    .slice(0, 2)
    .map(([key, value]) => `${titleize(key)} ${formatCellValue(value, undefined, key)}`)
    .join(' / ')
}

function objectMeta(item: Record<string, unknown>, fallback: string) {
  const severity = item.severity ?? item.level
  return severity === undefined || severity === null ? fallback : String(severity)
}

function severityFromUnknown(value: unknown): SignalSeverity {
  if (typeof value !== 'string') return 'normal'
  const normalized = value.toLowerCase()
  if (['critical', 'high', 'error', 'down', 'blocked'].includes(normalized)) return 'critical'
  if (['warning', 'warn', 'medium', 'elevated', 'degraded'].includes(normalized)) return 'elevated'
  return 'normal'
}

function severityForField(field: ResolvedField): SignalSeverity {
  if (field.numericValue === null) return severityFromUnknown(field.rawValue)
  const label = `${field.binding.fieldId} ${field.binding.label}`.toLowerCase()
  const bounded = field.binding.unit === 'percent' || /score|risk|cpu|memory|usage|percent/.test(label)
  if (!bounded) return 'normal'
  return severityFromPercent(normalizeGaugeValue(field))
}

function severityFromPercent(value: number): SignalSeverity {
  if (value >= 80) return 'critical'
  if (value >= 60) return 'elevated'
  return 'normal'
}

function severityClass(severity: SignalSeverity) {
  if (severity === 'critical') return 'border-rose-400/45 bg-rose-500/10 text-rose-200'
  if (severity === 'elevated') return 'border-amber-400/45 bg-amber-500/10 text-amber-200'
  return 'border-theme-border bg-theme-bg/70 text-theme-text'
}

function severityDotClass(severity: SignalSeverity) {
  if (severity === 'critical') return 'bg-rose-400 shadow-[0_0_12px_rgba(251,113,133,0.55)]'
  if (severity === 'elevated') return 'bg-amber-300 shadow-[0_0_12px_rgba(252,211,77,0.4)]'
  return 'bg-theme-primary shadow-[0_0_12px_rgba(0,255,136,0.25)]'
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

  <div v-else-if="template?.kind === 'gauge'" class="flex h-full flex-col justify-between gap-4 text-theme-text">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ primaryField?.binding.label }}</h3>
        <p class="mt-1 truncate text-[11px] text-theme-text-muted">{{ primaryField?.binding.source }}</p>
      </div>
      <span class="shrink-0 rounded border px-2 py-1 text-[10px] font-semibold capitalize" :class="severityClass(gaugeSeverity)">
        {{ gaugeSeverity }}
      </span>
    </div>

    <div class="flex flex-1 flex-col justify-center gap-4">
      <div class="relative">
        <div class="h-4 overflow-hidden rounded-full border border-theme-border bg-theme-bg/80">
          <div
            data-test="custom-gauge-fill"
            class="h-full rounded-full bg-theme-primary shadow-[0_0_18px_rgba(0,255,136,0.2)]"
            :style="{ width: `${Math.round(gaugeValue)}%` }"
          />
        </div>
        <div class="mt-2 flex justify-between text-[10px] text-theme-text-muted">
          <span>0</span>
          <span>100</span>
        </div>
      </div>

      <div class="text-center">
        <div data-test="custom-gauge-value" class="text-5xl font-semibold leading-none tabular-nums">
          {{ primaryField?.formattedValue ?? '--' }}
        </div>
        <p class="mt-2 truncate text-xs text-theme-text-muted">{{ primaryField?.binding.unit ?? primaryField?.binding.type }}</p>
      </div>
    </div>

    <p v-if="sourceError" class="truncate text-xs text-amber-300">{{ sourceError }}</p>
  </div>

  <div v-else-if="template?.kind === 'table'" class="flex h-full min-h-0 flex-col gap-3 text-theme-text">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ template.title }}</h3>
        <p class="truncate text-[11px] text-theme-text-muted">{{ tableRows.length }} rows</p>
      </div>
      <div class="flex size-8 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="18" />
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-auto rounded border border-theme-border bg-theme-bg/50">
      <div class="grid grid-cols-[minmax(0,1fr)_minmax(4rem,0.8fr)_minmax(5rem,0.9fr)] gap-2 border-b border-theme-border px-3 py-2 text-[10px] font-semibold text-theme-text-muted">
        <span>Field</span>
        <span>Value</span>
        <span>Source</span>
      </div>
      <div
        v-for="row in tableRows"
        :key="row.id"
        data-test="custom-table-row"
        class="grid grid-cols-[minmax(0,1fr)_minmax(4rem,0.8fr)_minmax(5rem,0.9fr)] gap-2 border-b border-theme-border/60 px-3 py-2 text-xs last:border-b-0"
      >
        <span class="truncate font-medium">{{ row.label }}</span>
        <span class="truncate tabular-nums text-theme-text">{{ row.value }}</span>
        <span class="truncate text-theme-text-muted">{{ row.source }}</span>
      </div>
    </div>

    <p v-if="sourceError" class="truncate text-xs text-amber-300">{{ sourceError }}</p>
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

  <div v-else-if="template?.kind === 'line'" class="flex h-full min-h-0 flex-col gap-3 text-theme-text">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ template.title }}</h3>
        <p class="truncate text-[11px] text-theme-text-muted">Current snapshot</p>
      </div>
      <div class="flex size-8 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="18" />
      </div>
    </div>

    <div class="relative min-h-0 flex-1 rounded border border-theme-border bg-theme-bg/50 p-3">
      <svg viewBox="0 0 100 100" role="img" aria-label="Current value profile" class="h-full w-full">
        <line x1="8" y1="86" x2="92" y2="86" class="stroke-theme-border" stroke-width="1" />
        <line x1="8" y1="14" x2="8" y2="86" class="stroke-theme-border" stroke-width="1" />
        <path v-if="linePoints.length > 1" :d="linePath" fill="none" class="stroke-theme-primary" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
        <g v-for="point in linePoints" :key="point.id">
          <line :x1="point.x" y1="86" :x2="point.x" :y2="point.y" class="stroke-theme-primary/40" stroke-width="1" />
          <circle :cx="point.x" :cy="point.y" r="3.2" class="fill-theme-primary" />
        </g>
      </svg>
    </div>

    <div class="grid grid-cols-2 gap-2 text-xs">
      <div v-for="point in linePoints" :key="`${point.id}-label`" class="min-w-0 rounded border border-theme-border bg-theme-bg/70 px-2 py-1">
        <div class="truncate font-medium">{{ point.label }}</div>
        <div class="truncate text-theme-text-muted tabular-nums">{{ point.value }}</div>
      </div>
    </div>

    <p v-if="sourceError" class="truncate text-xs text-amber-300">{{ sourceError }}</p>
  </div>

  <div v-else-if="template?.kind === 'feed'" class="flex h-full min-h-0 flex-col gap-3 text-theme-text">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ template.title }}</h3>
        <p class="truncate text-[11px] text-theme-text-muted">{{ feedRows.length }} items</p>
      </div>
      <div class="flex size-8 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="18" />
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-auto">
      <div
        v-for="row in feedRows"
        :key="row.id"
        data-test="custom-feed-row"
        class="mb-2 flex gap-3 rounded border border-theme-border bg-theme-bg/70 px-3 py-2 last:mb-0"
      >
        <span class="mt-1 size-2.5 shrink-0 rounded-full" :class="severityDotClass(row.severity)" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between gap-3">
            <p class="truncate text-xs font-semibold">{{ row.title }}</p>
            <span class="shrink-0 text-[10px] capitalize text-theme-text-muted">{{ row.meta }}</span>
          </div>
          <p v-if="row.detail" class="mt-1 truncate text-[11px] text-theme-text-muted">{{ row.detail }}</p>
        </div>
      </div>
    </div>

    <p v-if="sourceError" class="truncate text-xs text-amber-300">{{ sourceError }}</p>
  </div>

  <div v-else-if="template?.kind === 'list'" class="flex h-full min-h-0 flex-col gap-3 text-theme-text">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ template.title }}</h3>
        <p class="truncate text-[11px] text-theme-text-muted">{{ signalRows.length }} signals</p>
      </div>
      <div class="flex size-8 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="18" />
      </div>
    </div>

    <div class="min-h-0 flex-1 space-y-2 overflow-auto">
      <div
        v-for="row in signalRows"
        :key="row.id"
        data-test="custom-signal-row"
        :data-severity="row.severity"
        class="rounded border px-3 py-2"
        :class="severityClass(row.severity)"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="truncate text-xs font-semibold">{{ row.label }}</p>
            <p class="mt-0.5 truncate text-[10px] opacity-70">{{ row.source }}</p>
          </div>
          <span class="shrink-0 text-sm font-semibold tabular-nums">{{ row.value }}</span>
        </div>
        <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-theme-bg/80">
          <div class="h-full rounded-full bg-current opacity-80" :style="{ width: row.width }" />
        </div>
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
