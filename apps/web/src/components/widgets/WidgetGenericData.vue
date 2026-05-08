<script setup lang="ts">
import { computed } from 'vue'
import { Activity, BarChart2, ListChecks, Table } from 'lucide-vue-next'

const props = defineProps<{
  catalogId: string
  data?: Record<string, unknown> | null
}>()

type GenericKind = 'bar' | 'feed' | 'table' | 'status-list'

type GenericWidgetMeta = {
  title: string
  kind: GenericKind
  itemsKey: string
  labelKeys: string[]
  valueKeys: string[]
  metaKeys: string[]
}

const metadataByCatalogId: Record<string, GenericWidgetMeta> = {
  'soc-incidents-by-severity': {
    title: 'Incidents by Severity',
    kind: 'bar',
    itemsKey: 'items',
    labelKeys: ['severity', 'status', 'label'],
    valueKeys: ['count', 'value', 'total'],
    metaKeys: ['severity'],
  },
  'soc-recent-incidents': {
    title: 'Recent Incidents',
    kind: 'feed',
    itemsKey: 'incidents',
    labelKeys: ['title', 'summary', 'id'],
    valueKeys: ['summary', 'status', 'severity'],
    metaKeys: ['status', 'severity', 'source'],
  },
  'soc-top-entities': {
    title: 'Top Entities',
    kind: 'table',
    itemsKey: 'entities',
    labelKeys: ['value', 'field', 'hostname', 'sourceIp'],
    valueKeys: ['count', 'status', 'health'],
    metaKeys: ['field', 'type'],
  },
  'xdr-endpoint-health': {
    title: 'Endpoint Health',
    kind: 'status-list',
    itemsKey: 'endpoints',
    labelKeys: ['hostname', 'name', 'id'],
    valueKeys: ['health', 'status', 'os'],
    metaKeys: ['os', 'currentUser', 'lastSeenAt'],
  },
  'soar-active-playbook-runs': {
    title: 'Active Playbook Runs',
    kind: 'table',
    itemsKey: 'runs',
    labelKeys: ['name', 'playbookId', 'id'],
    valueKeys: ['status', 'currentStep', 'count'],
    metaKeys: ['status', 'incidentId'],
  },
}

const meta = computed(() => metadataByCatalogId[props.catalogId] ?? {
  title: props.catalogId,
  kind: 'table' as const,
  itemsKey: 'items',
  labelKeys: ['label', 'name', 'id'],
  valueKeys: ['value', 'count', 'status'],
  metaKeys: ['source'],
})

const rows = computed(() => {
  const payload = props.data ?? {}
  const rawRows: unknown[] = Array.isArray(payload[meta.value.itemsKey])
    ? payload[meta.value.itemsKey] as unknown[]
    : []
  return rawRows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object' && !Array.isArray(row))
    .map((row: Record<string, unknown>, index: number) => ({
      id: String(row.id ?? `${meta.value.itemsKey}-${index}`),
      label: firstValue(row, meta.value.labelKeys) || `Item ${index + 1}`,
      value: firstValue(row, meta.value.valueKeys) || '--',
      meta: firstValue(row, meta.value.metaKeys) || '',
      severity: severityFromRow(row),
    }))
})

const icon = computed(() => {
  if (meta.value.kind === 'bar') return BarChart2
  if (meta.value.kind === 'status-list') return Activity
  if (meta.value.kind === 'feed') return ListChecks
  return Table
})

const maxValue = computed(() => {
  const values = rows.value
    .map((row) => numericValue(row.value))
    .filter((value): value is number => value !== null)
  return Math.max(1, ...values)
})

function firstValue(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key]
    if (value !== undefined && value !== null && value !== '') return formatValue(value)
  }
  return ''
}

function formatValue(value: unknown) {
  if (typeof value === 'number') return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function numericValue(value: string) {
  const parsed = Number(value.replace(/,/g, ''))
  return Number.isFinite(parsed) ? parsed : null
}

function barWidth(value: string) {
  const parsed = numericValue(value)
  if (parsed === null) return '0%'
  return `${Math.max(4, Math.round((parsed / maxValue.value) * 100))}%`
}

function severityFromRow(row: Record<string, unknown>) {
  const value = String(row.severity ?? row.health ?? row.status ?? '').toLowerCase()
  if (['critical', 'high', 'down', 'failed', 'error'].includes(value)) return 'critical'
  if (['medium', 'warning', 'warn', 'degraded', 'waiting_approval'].includes(value)) return 'warning'
  return 'normal'
}

function dotClass(severity: string) {
  if (severity === 'critical') return 'bg-rose-400'
  if (severity === 'warning') return 'bg-amber-300'
  return 'bg-theme-primary'
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3 text-theme-text">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ meta.title }}</h3>
        <p class="truncate text-[11px] text-theme-text-muted">{{ rows.length }} rows</p>
      </div>
      <div class="flex size-8 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="18" />
      </div>
    </div>

    <div v-if="rows.length === 0" class="flex min-h-0 flex-1 items-center justify-center rounded border border-theme-border bg-theme-bg/50 p-4 text-center text-xs text-theme-text-muted">
      No data returned for this SOC preset.
    </div>

    <div v-else-if="meta.kind === 'bar'" class="flex min-h-0 flex-1 flex-col justify-center gap-3">
      <div v-for="row in rows" :key="row.id" data-test="generic-bar-row" class="min-w-0">
        <div class="mb-1 flex items-center justify-between gap-2 text-xs">
          <span class="truncate font-medium capitalize">{{ row.label }}</span>
          <span class="shrink-0 tabular-nums text-theme-text-muted">{{ row.value }}</span>
        </div>
        <div class="h-3 overflow-hidden rounded-sm bg-theme-bg/80">
          <div class="h-full rounded-sm bg-theme-primary shadow-[0_0_16px_rgba(0,255,136,0.18)]" :style="{ width: barWidth(row.value) }" />
        </div>
      </div>
    </div>

    <div v-else-if="meta.kind === 'feed'" class="min-h-0 flex-1 overflow-auto">
      <div
        v-for="row in rows"
        :key="row.id"
        data-test="generic-feed-row"
        class="mb-2 flex gap-3 rounded border border-theme-border bg-theme-bg/70 px-3 py-2 last:mb-0"
      >
        <span class="mt-1 size-2.5 shrink-0 rounded-full" :class="dotClass(row.severity)" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between gap-3">
            <p class="truncate text-xs font-semibold">{{ row.label }}</p>
            <span class="shrink-0 text-[10px] capitalize text-theme-text-muted">{{ row.meta }}</span>
          </div>
          <p class="mt-1 truncate text-[11px] text-theme-text-muted">{{ row.value }}</p>
        </div>
      </div>
    </div>

    <div v-else class="min-h-0 flex-1 overflow-auto rounded border border-theme-border bg-theme-bg/50">
      <div class="grid grid-cols-[minmax(0,1fr)_minmax(4rem,0.7fr)_minmax(4rem,0.7fr)] gap-2 border-b border-theme-border px-3 py-2 text-[10px] font-semibold uppercase text-theme-text-muted">
        <span>Name</span>
        <span>Value</span>
        <span>Context</span>
      </div>
      <div
        v-for="row in rows"
        :key="row.id"
        data-test="generic-table-row"
        class="grid grid-cols-[minmax(0,1fr)_minmax(4rem,0.7fr)_minmax(4rem,0.7fr)] gap-2 border-b border-theme-border/60 px-3 py-2 text-xs last:border-b-0"
      >
        <span class="truncate font-medium">{{ row.label }}</span>
        <span class="truncate tabular-nums">{{ row.value }}</span>
        <span class="truncate text-theme-text-muted">{{ row.meta }}</span>
      </div>
    </div>
  </div>
</template>
