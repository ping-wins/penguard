<script setup lang="ts">
import { computed, ref } from 'vue'
import { AlarmClock } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import WidgetSlaBadge from '../shell/WidgetSlaBadge.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'
import { ageMs, formatAge, slaBucket, topByCount } from '../../../composables/useSocMetrics'
import { severityTokens, normalizeSeverity } from '../../../lib/severityTokens'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const incidents = computed<any[]>(() => Array.isArray(props.data?.incidents) ? props.data.incidents : [])

type Breach = {
  id: string
  title: string
  severity: string
  ticketStatus: string
  triageLevel: string
  ageMs: number
  bucket: 'amber' | 'red'
  ruleId: string | null
}

function numericField(key: string): number | null {
  const value = Number(props.data?.[key])
  return Number.isFinite(value) ? value : null
}

const calculatedBreaches = computed<Breach[]>(() => {
  const raw = Array.isArray(props.data?.breaches) ? props.data.breaches : []
  return raw
    .filter((row: any) => row && typeof row === 'object')
    .map((row: any) => ({
      id: String(row.id ?? ''),
      title: String(row.title ?? row.summary ?? row.id ?? 'Incident'),
      severity: normalizeSeverity(row.severity),
      ticketStatus: String(row.ticketStatus || row.status || '--'),
      triageLevel: String(row.triageLevel || '--'),
      ageMs: Number(row.ageMs) || 0,
      bucket: row.bucket === 'red' ? 'red' : 'amber',
      ruleId: row.ruleId ?? row.rule_id ?? null,
    }))
    .sort((a: Breach, b: Breach) => b.ageMs - a.ageMs)
})

const hasCalculatedSla = computed(() =>
  Array.isArray(props.data?.breaches)
  || numericField('red') !== null
  || numericField('amber') !== null
  || numericField('open') !== null
)

const incidentBreaches = computed<Breach[]>(() => {
  const out: Breach[] = []
  for (const inc of incidents.value) {
    if (!inc || typeof inc !== 'object') continue
    const age = ageMs(inc.createdAt)
    if (age === null) continue
    const bucket = slaBucket(age)
    if (bucket === 'green') continue
    const closed = String(inc.ticketStatus || '').toLowerCase()
    if (closed === 'closed' || closed === 'contained') continue
    out.push({
      id: String(inc.id ?? ''),
      title: String(inc.title ?? inc.summary ?? inc.id ?? 'Incident'),
      severity: normalizeSeverity(inc.severity),
      ticketStatus: String(inc.ticketStatus || inc.status || '--'),
      triageLevel: String(inc.triageLevel || '--'),
      ageMs: age,
      bucket: bucket as 'amber' | 'red',
      ruleId: inc.ruleId ?? inc.rule_id ?? null,
    })
  }
  return out.sort((a, b) => b.ageMs - a.ageMs)
})

const breaches = computed<Breach[]>(() =>
  hasCalculatedSla.value ? calculatedBreaches.value : incidentBreaches.value
)

const redCount = computed(() =>
  numericField('red') ?? breaches.value.filter((b) => b.bucket === 'red').length
)
const amberCount = computed(() =>
  numericField('amber') ?? breaches.value.filter((b) => b.bucket === 'amber').length
)

const triageDistribution = computed(() => topByCount(breaches.value, (b) => b.triageLevel, 4))
const ruleDistribution = computed(() => topByCount(breaches.value, (b) => b.ruleId, 5))

const selectedId = ref<string | null>(null)

const selectedBreach = computed(() => breaches.value.find((b) => b.id === selectedId.value) ?? null)
const selectedIncident = computed(() => incidents.value.find((i: any) => i?.id === selectedId.value) ?? null)

function selectBreach(id: string) {
  selectedId.value = selectedId.value === id ? null : id
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="SLA Breach"
    subtitle="Overdue incidents past SLA threshold"
    :icon="AlarmClock"
    source="siem_kowalski"
  >
    <template #glance>
      <div class="grid grid-cols-2 gap-2">
        <WidgetKpiTile label="Red SLA" :value="redCount" :tone="redCount > 0 ? 'critical' : 'healthy'" />
        <WidgetKpiTile label="Amber SLA" :value="amberCount" :tone="amberCount > 0 ? 'warning' : 'healthy'" />
      </div>
      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar">
        <button
          v-for="breach in breaches.slice(0, 10)"
          :key="breach.id"
          type="button"
          class="flex flex-col gap-1 rounded border p-2 text-left text-xs transition-colors hover:border-theme-primary/40"
          :class="[
            breach.bucket === 'red' ? 'border-red-400/40 bg-red-950/20' : 'border-amber-400/30 bg-amber-950/15',
            selectedId === breach.id ? 'ring-1 ring-theme-primary/60' : '',
          ]"
          @click.stop="selectBreach(breach.id)"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="flex min-w-0 items-center gap-1.5">
              <span class="h-2 w-2 shrink-0 rounded-full" :class="severityTokens(breach.severity).dot" />
              <span class="truncate font-semibold text-theme-text">{{ breach.title }}</span>
            </div>
            <WidgetSlaBadge :age-ms="breach.ageMs" />
          </div>
          <div class="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-theme-text-muted">
            <span>{{ breach.triageLevel }} · {{ breach.ticketStatus }}</span>
            <span v-if="breach.ruleId" class="font-mono normal-case">{{ breach.ruleId }}</span>
          </div>
        </button>
        <WidgetEmptyState
          v-if="breaches.length === 0"
          title="No SLA breaches"
          hint="All open incidents are within the SLA window. Add Recent Incidents widget if this looks empty unexpectedly."
        />
      </div>
    </template>

    <template #drill>
      <div v-if="!selectedBreach" class="text-xs text-theme-text-muted">
        Click an incident to inspect its entities and timeline.
      </div>
      <div v-else class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-xs font-semibold text-theme-text">{{ selectedBreach.title }}</span>
          <span class="shrink-0 text-[10px] uppercase tracking-wide text-theme-text-muted">{{ selectedBreach.triageLevel }}</span>
        </div>
        <div v-if="selectedIncident?.summary" class="text-xs text-theme-text-muted">{{ selectedIncident.summary }}</div>
        <div v-if="selectedIncident?.entities && Object.keys(selectedIncident.entities).length" class="flex flex-wrap gap-1.5">
          <span
            v-for="(value, key) in selectedIncident.entities"
            :key="key"
            class="inline-flex items-center gap-1 rounded border border-theme-border bg-theme-text/5 px-1.5 py-0.5 text-[10px]"
          >
            <span class="text-theme-text-muted">{{ key }}:</span>
            <span class="font-mono text-theme-text">{{ value }}</span>
          </span>
        </div>
        <div class="text-[11px] text-theme-text-muted">
          Open for <span class="font-semibold text-theme-text">{{ formatAge(selectedBreach.ageMs) }}</span> · ticket status <span class="font-semibold text-theme-text">{{ selectedBreach.ticketStatus }}</span>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section class="grid grid-cols-2 gap-2">
          <WidgetKpiTile label="Red SLA" :value="redCount" :tone="redCount > 0 ? 'critical' : 'healthy'" />
          <WidgetKpiTile label="Amber SLA" :value="amberCount" :tone="amberCount > 0 ? 'warning' : 'healthy'" />
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Breaches by triage</h3>
          <ul class="space-y-1 text-xs">
            <li
              v-for="row in triageDistribution"
              :key="row.key"
              class="flex justify-between gap-2 rounded bg-theme-text/5 px-2 py-1"
            >
              <span class="font-mono">{{ row.key }}</span>
              <span class="tabular-nums">{{ row.count }}</span>
            </li>
            <li v-if="triageDistribution.length === 0" class="text-theme-text-muted">No data.</li>
          </ul>
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Top contributing rules</h3>
          <ul class="space-y-1 text-xs">
            <li
              v-for="row in ruleDistribution"
              :key="row.key"
              class="flex justify-between gap-2 rounded bg-theme-text/5 px-2 py-1"
            >
              <span class="truncate font-mono">{{ row.key }}</span>
              <span class="tabular-nums text-theme-text-muted">{{ row.count }}</span>
            </li>
            <li v-if="ruleDistribution.length === 0" class="text-theme-text-muted">No data.</li>
          </ul>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
