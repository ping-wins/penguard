<script setup lang="ts">
import { computed } from 'vue'
import { Timer } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import WidgetSparkline from '../shell/WidgetSparkline.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'
import { useWidgetSeriesStore } from '../../../stores/useWidgetSeriesStore'
import { useWidgetSeries } from '../../../composables/useWidgetSeries'
import { ageMs, formatAge, mttdEstimate, mttrEstimate } from '../../../composables/useSocMetrics'
import { normalizeSeverity, severityRank } from '../../../lib/severityTokens'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const incidents = computed<any[]>(() => Array.isArray(props.data?.incidents) ? props.data.incidents : [])

const seriesStore = useWidgetSeriesStore()

const mttdValues = computed(() => incidents.value.map(mttdEstimate).filter((v): v is number => v !== null))
const mttrValues = computed(() => incidents.value.map(mttrEstimate).filter((v): v is number => v !== null))

const mttdAvg = computed(() => avg(mttdValues.value))
const mttrAvg = computed(() => avg(mttrValues.value))
const mttdMedian = computed(() => median(mttdValues.value))
const mttrMedian = computed(() => median(mttrValues.value))

function avg(values: number[]): number | null {
  if (values.length === 0) return null
  return values.reduce((sum, v) => sum + v, 0) / values.length
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

const countSeries = useWidgetSeries(props.instanceId, 'count')

const rankedIncidents = computed(() => {
  return [...incidents.value]
    .map((inc: any) => ({
      id: String(inc?.id ?? ''),
      title: String(inc?.title ?? inc?.summary ?? inc?.id ?? 'Incident'),
      severity: normalizeSeverity(inc?.severity),
      mttd: mttdEstimate(inc),
      mttr: mttrEstimate(inc),
      age: ageMs(inc?.createdAt),
    }))
    .sort((a, b) => severityRank(b.severity) - severityRank(a.severity))
})

const noData = computed(() => incidents.value.length === 0)

void seriesStore
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="MTTD / MTTR"
    subtitle="Mean detect + respond times from active incident set"
    :icon="Timer"
    source="siem_kowalski"
  >
    <template #glance>
      <div class="grid grid-cols-2 gap-2">
        <WidgetKpiTile
          label="MTTD avg"
          :value="mttdAvg !== null ? formatAge(mttdAvg) : '--'"
          :series="countSeries.points.value"
        />
        <WidgetKpiTile
          label="MTTR avg"
          :value="mttrAvg !== null ? formatAge(mttrAvg) : '--'"
        />
        <WidgetKpiTile label="MTTD p50" :value="mttdMedian !== null ? formatAge(mttdMedian) : '--'" />
        <WidgetKpiTile label="MTTR p50" :value="mttrMedian !== null ? formatAge(mttrMedian) : '--'" />
      </div>
      <WidgetEmptyState
        v-if="noData"
        title="No incidents to score"
        hint="Add the Recent Incidents widget or seed demo data to populate this metric."
      />
    </template>

    <template #drill>
      <div v-if="noData" class="text-xs text-theme-text-muted">
        Need at least one incident to derive MTTD/MTTR.
      </div>
      <div v-else class="flex max-h-48 flex-col gap-1 overflow-y-auto no-scrollbar">
        <div
          v-for="row in rankedIncidents.slice(0, 10)"
          :key="row.id"
          class="flex items-center justify-between gap-2 rounded bg-theme-text/5 px-2 py-1 text-xs"
        >
          <span class="truncate text-theme-text">{{ row.title }}</span>
          <div class="flex shrink-0 items-center gap-3 text-[10px] tabular-nums text-theme-text-muted">
            <span>MTTD <span class="text-theme-text">{{ row.mttd !== null ? formatAge(row.mttd) : '--' }}</span></span>
            <span>MTTR <span class="text-theme-text">{{ row.mttr !== null ? formatAge(row.mttr) : '--' }}</span></span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section class="grid grid-cols-2 gap-2">
          <WidgetKpiTile label="MTTD avg" :value="mttdAvg !== null ? formatAge(mttdAvg) : '--'" />
          <WidgetKpiTile label="MTTR avg" :value="mttrAvg !== null ? formatAge(mttrAvg) : '--'" />
          <WidgetKpiTile label="MTTD p50" :value="mttdMedian !== null ? formatAge(mttdMedian) : '--'" />
          <WidgetKpiTile label="MTTR p50" :value="mttrMedian !== null ? formatAge(mttrMedian) : '--'" />
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Incident count trend</h3>
          <WidgetSparkline :points="countSeries.points.value" :width="320" :height="56" />
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Per-incident metrics</h3>
          <table class="w-full text-xs">
            <thead class="text-[10px] uppercase tracking-wide text-theme-text-muted">
              <tr>
                <th class="text-left font-semibold">Incident</th>
                <th class="text-left font-semibold">Severity</th>
                <th class="text-right font-semibold">Age</th>
                <th class="text-right font-semibold">MTTD</th>
                <th class="text-right font-semibold">MTTR</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rankedIncidents" :key="row.id" class="border-t border-theme-border/40">
                <td class="py-1 pr-2 text-theme-text"><span class="truncate">{{ row.title }}</span></td>
                <td class="py-1 pr-2 capitalize">{{ row.severity }}</td>
                <td class="py-1 pr-2 text-right tabular-nums">{{ row.age !== null ? formatAge(row.age) : '--' }}</td>
                <td class="py-1 pr-2 text-right tabular-nums">{{ row.mttd !== null ? formatAge(row.mttd) : '--' }}</td>
                <td class="py-1 text-right tabular-nums">{{ row.mttr !== null ? formatAge(row.mttr) : '--' }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
