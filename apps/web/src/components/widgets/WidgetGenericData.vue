<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Activity, BarChart2, ListChecks, Table } from 'lucide-vue-next'
import { sourceBadgeFor, type SourceBadge } from '../../utils/sourceBadges'

const props = defineProps<{
  catalogId: string
  data?: Record<string, unknown> | null
}>()

const { t, locale } = useI18n()

type GenericKind = 'bar' | 'feed' | 'table' | 'status-list'

type GenericWidgetMeta = {
  titleKey: string
  kind: GenericKind
  itemsKey: string
  labelKeys: string[]
  valueKeys: string[]
  metaKeys: string[]
  emptyTitleKey: string
  emptyHintKey: string
}

const metadataByCatalogId: Record<string, GenericWidgetMeta> = {
  'soc-incidents-by-severity': {
    titleKey: 'widgets.generic.presets.socIncidentsBySeverity.title',
    kind: 'bar',
    itemsKey: 'items',
    labelKeys: ['severity', 'status', 'label'],
    valueKeys: ['count', 'value', 'total'],
    metaKeys: ['severity'],
    emptyTitleKey: 'widgets.generic.presets.socIncidentsBySeverity.emptyTitle',
    emptyHintKey: 'widgets.generic.presets.socIncidentsBySeverity.emptyHint',
  },
  'soc-recent-incidents': {
    titleKey: 'widgets.generic.presets.socRecentIncidents.title',
    kind: 'feed',
    itemsKey: 'incidents',
    labelKeys: ['title', 'summary', 'id'],
    valueKeys: ['summary', 'status', 'severity'],
    metaKeys: ['status', 'severity', 'source'],
    emptyTitleKey: 'widgets.generic.presets.socRecentIncidents.emptyTitle',
    emptyHintKey: 'widgets.generic.presets.socRecentIncidents.emptyHint',
  },
  'soc-top-entities': {
    titleKey: 'widgets.generic.presets.socTopEntities.title',
    kind: 'table',
    itemsKey: 'entities',
    labelKeys: ['value', 'field', 'hostname', 'sourceIp'],
    valueKeys: ['count', 'status', 'health'],
    metaKeys: ['field', 'type'],
    emptyTitleKey: 'widgets.generic.presets.socTopEntities.emptyTitle',
    emptyHintKey: 'widgets.generic.presets.socTopEntities.emptyHint',
  },
  'xdr-endpoint-health': {
    titleKey: 'widgets.generic.presets.xdrEndpointHealth.title',
    kind: 'status-list',
    itemsKey: 'endpoints',
    labelKeys: ['hostname', 'name', 'id'],
    valueKeys: ['health', 'status', 'os'],
    metaKeys: ['os', 'currentUser', 'lastSeenAt'],
    emptyTitleKey: 'widgets.generic.presets.xdrEndpointHealth.emptyTitle',
    emptyHintKey: 'widgets.generic.presets.xdrEndpointHealth.emptyHint',
  },
  'soar-active-playbook-runs': {
    titleKey: 'widgets.generic.presets.soarActivePlaybookRuns.title',
    kind: 'table',
    itemsKey: 'runs',
    labelKeys: ['name', 'playbookId', 'id'],
    valueKeys: ['status', 'currentStep', 'count'],
    metaKeys: ['status', 'incidentId'],
    emptyTitleKey: 'widgets.generic.presets.soarActivePlaybookRuns.emptyTitle',
    emptyHintKey: 'widgets.generic.presets.soarActivePlaybookRuns.emptyHint',
  },
}

const meta = computed(() => metadataByCatalogId[props.catalogId] ?? {
  titleKey: '',
  kind: 'table' as const,
  itemsKey: 'items',
  labelKeys: ['label', 'name', 'id'],
  valueKeys: ['value', 'count', 'status'],
  metaKeys: ['source'],
  emptyTitleKey: 'widgets.generic.fallback.emptyTitle',
  emptyHintKey: 'widgets.generic.fallback.emptyHint',
})

const rows = computed(() => {
  const payload = props.data ?? {}
  const rawRows: unknown[] = Array.isArray(payload[meta.value.itemsKey])
    ? payload[meta.value.itemsKey] as unknown[]
    : []
  return rawRows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object' && !Array.isArray(row))
    .map((row: Record<string, unknown>, index: number) => {
      const rawValue = firstRawValue(row, meta.value.valueKeys)
      return {
        id: String(row.id ?? `${meta.value.itemsKey}-${index}`),
        label: firstValue(row, meta.value.labelKeys) || t('widgets.generic.item', { number: index + 1 }),
        value: rawValue === undefined ? '--' : formatValue(rawValue),
        numericValue: numericRawValue(rawValue),
        meta: firstValue(row, meta.value.metaKeys) || '',
        severity: severityFromRow(row),
        sourceBadge: sourceBadgeFor(row),
      }
    })
})

const displayTitle = computed(() => meta.value.titleKey ? t(meta.value.titleKey) : props.catalogId)
const emptyTitle = computed(() => t(meta.value.emptyTitleKey))
const emptyHint = computed(() => t(meta.value.emptyHintKey))

const icon = computed(() => {
  if (meta.value.kind === 'bar') return BarChart2
  if (meta.value.kind === 'status-list') return Activity
  if (meta.value.kind === 'feed') return ListChecks
  return Table
})

const maxValue = computed(() => {
  const values = rows.value
    .map((row) => row.numericValue)
    .filter((value): value is number => value !== null)
  return Math.max(1, ...values)
})

function firstValue(row: Record<string, unknown>, keys: string[]) {
  const value = firstRawValue(row, keys)
  return value === undefined ? '' : formatValue(value)
}

function firstRawValue(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return undefined
}

function formatValue(value: unknown) {
  if (typeof value === 'number') {
    return new Intl.NumberFormat(locale.value, { maximumFractionDigits: 1 }).format(value)
  }
  if (typeof value === 'boolean') return t(value ? 'common.yes' : 'common.no')
  return String(value)
}

function numericRawValue(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return null
  const parsed = Number(value.replace(/,/g, ''))
  return Number.isFinite(parsed) ? parsed : null
}

function barWidth(value: number | null) {
  const parsed = value
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

function sourceBadgeClass(badge: SourceBadge) {
  if (badge.tone === 'demo') return 'border-amber-500/40 bg-amber-500/10 text-amber-200'
  if (badge.tone === 'simulator') return 'border-sky-500/40 bg-sky-500/10 text-sky-200'
  if (badge.tone === 'ai') return 'border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200'
  return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3 text-theme-text">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ displayTitle }}</h3>
        <p class="truncate text-[11px] text-theme-text-muted">{{ t('widgets.generic.rows', { count: rows.length }) }}</p>
      </div>
      <div class="flex size-8 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-bg/70 text-theme-primary">
        <component :is="icon" :size="18" />
      </div>
    </div>

    <div v-if="rows.length === 0" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 rounded border border-theme-border bg-theme-bg/50 p-4 text-center text-xs text-theme-text-muted">
      <span class="font-semibold text-theme-text">{{ emptyTitle }}</span>
      <span>{{ emptyHint }}</span>
    </div>

    <div v-else-if="meta.kind === 'bar'" class="flex min-h-0 flex-1 flex-col justify-center gap-3">
      <div v-for="row in rows" :key="row.id" data-test="generic-bar-row" class="min-w-0">
        <div class="mb-1 flex items-center justify-between gap-2 text-xs">
          <span class="truncate font-medium capitalize">{{ row.label }}</span>
          <span class="shrink-0 tabular-nums text-theme-text-muted">{{ row.value }}</span>
        </div>
        <div class="h-3 overflow-hidden rounded-sm bg-theme-bg/80">
          <div class="h-full rounded-sm bg-theme-primary shadow-[0_0_16px_rgba(0,255,136,0.18)]" :style="{ width: barWidth(row.numericValue) }" />
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
            <div class="flex shrink-0 items-center gap-1">
              <span v-if="row.sourceBadge" class="rounded border px-1.5 py-0.5 text-[10px]" :class="sourceBadgeClass(row.sourceBadge)">
                {{ t(row.sourceBadge.labelKey) }}
              </span>
              <span class="text-[10px] capitalize text-theme-text-muted">{{ row.meta }}</span>
            </div>
          </div>
          <p class="mt-1 truncate text-[11px] text-theme-text-muted">{{ row.value }}</p>
        </div>
      </div>
    </div>

    <div v-else class="min-h-0 flex-1 overflow-auto rounded border border-theme-border bg-theme-bg/50">
      <div class="grid grid-cols-[minmax(0,1fr)_minmax(4rem,0.7fr)_minmax(4rem,0.7fr)] gap-2 border-b border-theme-border px-3 py-2 text-[10px] font-semibold uppercase text-theme-text-muted">
        <span>{{ t('widgets.generic.columns.name') }}</span>
        <span>{{ t('widgets.generic.columns.value') }}</span>
        <span>{{ t('widgets.generic.columns.context') }}</span>
      </div>
      <div
        v-for="row in rows"
        :key="row.id"
        data-test="generic-table-row"
        class="grid grid-cols-[minmax(0,1fr)_minmax(4rem,0.7fr)_minmax(4rem,0.7fr)] gap-2 border-b border-theme-border/60 px-3 py-2 text-xs last:border-b-0"
      >
        <span class="truncate font-medium">{{ row.label }}</span>
        <span class="truncate tabular-nums">{{ row.value }}</span>
        <span class="flex min-w-0 items-center gap-1">
          <span v-if="row.sourceBadge" class="shrink-0 rounded border px-1.5 py-0.5 text-[10px]" :class="sourceBadgeClass(row.sourceBadge)">
            {{ t(row.sourceBadge.labelKey) }}
          </span>
          <span class="truncate text-theme-text-muted">{{ row.meta }}</span>
        </span>
      </div>
    </div>
  </div>
</template>
