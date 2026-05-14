<script setup lang="ts">
import { computed, ref } from 'vue'
import { ListChecks } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetSlaBadge from '../shell/WidgetSlaBadge.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import { useWidgetSeries } from '../../../composables/useWidgetSeries'
import { severityTokens, normalizeSeverity, severityRank } from '../../../lib/severityTokens'
import { ageMs, formatAge, mttdEstimate, mttrEstimate, slaBucket } from '../../../composables/useSocMetrics'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const incidents = computed<any[]>(() => Array.isArray(props.data?.incidents) ? props.data.incidents : [])
const count = computed(() => Number(props.data?.count) || incidents.value.length)
const countSeries = useWidgetSeries(props.instanceId, 'count')

const sortedIncidents = computed(() => [...incidents.value].sort((a: any, b: any) => {
  const rankDiff = severityRank(b?.severity) - severityRank(a?.severity)
  if (rankDiff !== 0) return rankDiff
  const ageA = ageMs(a?.createdAt) ?? Number.POSITIVE_INFINITY
  const ageB = ageMs(b?.createdAt) ?? Number.POSITIVE_INFINITY
  return ageA - ageB
}))

const triageOpenIncidents = computed(() =>
  sortedIncidents.value.filter((inc: any) => {
    const status = String(inc?.ticketStatus ?? inc?.ticket_status ?? '').toLowerCase()
    return status !== 'closed' && status !== 'contained'
  })
)

const archivedIncidents = computed(() =>
  sortedIncidents.value.filter((inc: any) => {
    const status = String(inc?.ticketStatus ?? inc?.ticket_status ?? '').toLowerCase()
    return status === 'closed' || status === 'contained'
  })
)

const showArchived = ref(false)
const visibleIncidents = computed(() =>
  showArchived.value ? sortedIncidents.value : triageOpenIncidents.value
)

const selectedId = ref<string | null>(null)

function selectIncident(id: string | null) {
  selectedId.value = selectedId.value === id ? null : id
}

const selectedIncident = computed(() => incidents.value.find((inc: any) => inc?.id === selectedId.value) ?? null)

const slaBreaches = computed(() => incidents.value.filter((inc: any) => slaBucket(ageMs(inc?.createdAt)) !== 'green').length)

const mttdAvg = computed(() => {
  const values = incidents.value
    .map((inc: any) => mttdEstimate(inc))
    .filter((value: number | null) => value !== null) as number[]
  if (values.length === 0) return null
  return values.reduce((sum, v) => sum + v, 0) / values.length
})

const mttrAvg = computed(() => {
  const values = incidents.value
    .map((inc: any) => mttrEstimate(inc))
    .filter((value: number | null) => value !== null) as number[]
  if (values.length === 0) return null
  return values.reduce((sum, v) => sum + v, 0) / values.length
})
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="Recent Incidents"
    subtitle="Live SIEM feed"
    :icon="ListChecks"
    source="siem_kowalski"
  >
    <template #glance>
      <div class="grid grid-cols-3 gap-2">
        <WidgetKpiTile label="Incidents" :value="count" :series="countSeries.points.value" />
        <WidgetKpiTile label="SLA breach" :value="slaBreaches" :tone="slaBreaches > 0 ? 'warning' : 'default'" />
        <WidgetKpiTile label="MTTD avg" :value="mttdAvg !== null ? formatAge(mttdAvg) : '--'" />
      </div>
      <div class="mt-1 flex items-center justify-between gap-2 text-[10px] text-theme-text-muted">
        <span>{{ visibleIncidents.length }} shown · {{ archivedIncidents.length }} archived</span>
        <button
          v-if="archivedIncidents.length > 0"
          type="button"
          class="rounded border border-theme-border/60 bg-theme-text/5 px-2 py-0.5 text-[10px] uppercase tracking-wide hover:border-theme-primary/40"
          @click.stop="showArchived = !showArchived"
        >{{ showArchived ? 'Hide archived' : 'Show archived' }}</button>
      </div>
      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pr-1 incident-list">
        <button
          v-for="incident in visibleIncidents"
          :key="incident.id"
          type="button"
          class="flex flex-col gap-1 rounded border border-theme-border/40 bg-theme-text/5 p-2 text-left text-xs transition-colors hover:border-theme-primary/40"
          :class="selectedId === incident.id ? 'border-theme-primary/60 bg-theme-primary/10' : ''"
          @click.stop="selectIncident(incident.id)"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="flex min-w-0 items-center gap-1.5">
              <span class="h-2 w-2 shrink-0 rounded-full" :class="severityTokens(incident.severity).dot" />
              <span class="truncate font-semibold text-theme-text">{{ incident.title || incident.summary || incident.id }}</span>
            </div>
            <span
              v-if="incident.triageLevel"
              class="shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase"
              :class="severityTokens(incident.severity).badge"
            >{{ incident.triageLevel }}</span>
          </div>
          <div class="flex items-center justify-between gap-2 text-[10px] text-theme-text-muted">
            <span class="truncate">{{ incident.ticketStatus || incident.status || '--' }}</span>
            <WidgetSlaBadge :created-at="incident.createdAt" />
          </div>
        </button>
        <div v-if="visibleIncidents.length === 0" class="flex flex-1 items-center justify-center text-xs italic text-theme-text-muted">
          {{ incidents.length === 0 ? 'No incidents.' : 'No open incidents. Toggle archived to view closed.' }}
        </div>
      </div>
    </template>

    <template #drill>
      <div v-if="!selectedIncident" class="text-xs text-theme-text-muted">
        Select an incident above to inspect its entities and timeline.
      </div>
      <div v-else class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-xs font-semibold text-theme-text">{{ selectedIncident.title || selectedIncident.id }}</span>
          <span class="shrink-0 text-[10px] text-theme-text-muted">{{ selectedIncident.ruleId || selectedIncident.rule_id || '--' }}</span>
        </div>
        <div v-if="selectedIncident.summary" class="text-xs text-theme-text-muted">{{ selectedIncident.summary }}</div>
        <div v-if="selectedIncident.entities && Object.keys(selectedIncident.entities).length" class="flex flex-wrap gap-1.5">
          <span
            v-for="(value, key) in selectedIncident.entities"
            :key="key"
            class="inline-flex items-center gap-1 rounded border border-theme-border bg-theme-text/5 px-1.5 py-0.5 text-[10px]"
          >
            <span class="text-theme-text-muted">{{ key }}:</span>
            <span class="font-mono text-theme-text">{{ value }}</span>
          </span>
        </div>
        <div v-if="selectedIncident.timeline?.length" class="max-h-40 overflow-y-auto rounded border border-theme-border/50 bg-theme-bg/50 p-2 text-[11px]">
          <div v-for="(entry, idx) in selectedIncident.timeline" :key="idx" class="flex gap-2 border-b border-theme-border/30 py-1 last:border-0">
            <span class="shrink-0 font-mono text-theme-text-muted">{{ entry.at ? new Date(entry.at).toISOString().slice(11, 19) : '--' }}</span>
            <span class="truncate text-theme-text">{{ entry.type || entry.note || '--' }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section class="grid grid-cols-3 gap-2">
          <WidgetKpiTile label="MTTD avg" :value="mttdAvg !== null ? formatAge(mttdAvg) : '--'" />
          <WidgetKpiTile label="MTTR avg" :value="mttrAvg !== null ? formatAge(mttrAvg) : '--'" />
          <WidgetKpiTile label="SLA breach" :value="slaBreaches" :tone="slaBreaches > 0 ? 'warning' : 'default'" />
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Per-incident metrics</h3>
          <table class="w-full text-xs">
            <thead class="text-[10px] uppercase tracking-wide text-theme-text-muted">
              <tr>
                <th class="text-left font-semibold">Title</th>
                <th class="text-left font-semibold">Severity</th>
                <th class="text-left font-semibold">Status</th>
                <th class="text-right font-semibold">Age</th>
                <th class="text-right font-semibold">MTTD est.</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="incident in sortedIncidents" :key="incident.id" class="border-t border-theme-border/40">
                <td class="py-1 pr-2"><span class="truncate text-theme-text">{{ incident.title || incident.id }}</span></td>
                <td class="py-1 pr-2 capitalize">{{ normalizeSeverity(incident.severity) }}</td>
                <td class="py-1 pr-2">{{ incident.ticketStatus || incident.status || '--' }}</td>
                <td class="py-1 pr-2 text-right tabular-nums">{{ formatAge(ageMs(incident.createdAt)) }}</td>
                <td class="py-1 text-right tabular-nums">{{ mttdEstimate(incident) !== null ? formatAge(mttdEstimate(incident)) : '--' }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
