<script setup lang="ts">
import { computed, ref } from 'vue'
import { BarChart3 } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetSparkline from '../shell/WidgetSparkline.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import { useWidgetSeriesStore } from '../../../stores/useWidgetSeriesStore'
import { useWidgetSeries } from '../../../composables/useWidgetSeries'
import { severityTokens, severityRank, normalizeSeverity } from '../../../lib/severityTokens'
import { topByCount } from '../../../composables/useSocMetrics'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const seriesStore = useWidgetSeriesStore()
const totalSeries = useWidgetSeries(props.instanceId, 'total')
const criticalSeries = useWidgetSeries(props.instanceId, 'critical')
const highSeries = useWidgetSeries(props.instanceId, 'high')

const items = computed<Array<{ severity: string, count: number }>>(() => {
  const raw = Array.isArray(props.data?.items) ? props.data.items : []
  return raw
    .filter((row: any) => row && typeof row === 'object')
    .map((row: any) => ({ severity: normalizeSeverity(row.severity), count: Number(row.count) || 0 }))
    .sort((a: any, b: any) => severityRank(b.severity) - severityRank(a.severity))
})

const total = computed(() => Number(props.data?.total) || items.value.reduce((sum, r) => sum + r.count, 0))
const maxCount = computed(() => items.value.reduce((max, r) => Math.max(max, r.count), 0))

const selectedSeverity = ref<string | null>(null)

function selectSeverity(severity: string) {
  selectedSeverity.value = selectedSeverity.value === severity ? null : severity
}

const siblingIncidents = computed<any[]>(() => {
  const snapshot: any = seriesStore.getSiblingData('soc-recent-incidents', props.integrationId)
  if (!snapshot || !Array.isArray(snapshot.incidents)) return []
  return snapshot.incidents
})

const filteredIncidents = computed(() => {
  if (!selectedSeverity.value) return [] as any[]
  return siblingIncidents.value.filter((inc: any) => normalizeSeverity(inc?.severity) === selectedSeverity.value)
})

const topRules = computed(() => topByCount<any>(siblingIncidents.value, (i) => i?.ruleId || i?.rule_id || null, 5))

const sampleCountLabel = computed(() => `${totalSeries.sampleCount.value}/${totalSeries.capacity}`)
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="Incidents by Severity"
    subtitle="Live SIEM severity mix"
    :icon="BarChart3"
    source="siem_kowalski"
  >
    <template #glance>
      <div class="grid grid-cols-2 gap-2">
        <WidgetKpiTile label="Total" :value="total" :series="totalSeries.points.value" />
        <WidgetKpiTile
          label="Critical + High"
          :value="(items.find(r => r.severity === 'critical')?.count ?? 0) + (items.find(r => r.severity === 'high')?.count ?? 0)"
          :series="criticalSeries.points.value.length ? criticalSeries.points.value : highSeries.points.value"
          tone="critical"
        />
      </div>
      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto no-scrollbar">
        <button
          v-for="row in items"
          :key="row.severity"
          type="button"
          class="w-full text-left transition-colors"
          :class="selectedSeverity === row.severity ? 'bg-theme-primary/10 rounded px-1' : ''"
          @click.stop="selectSeverity(row.severity)"
        >
          <div class="mb-1 flex items-center justify-between gap-2 text-xs">
            <span class="flex items-center gap-1.5 capitalize">
              <span class="h-2 w-2 rounded-full" :class="severityTokens(row.severity).dot" />
              <span class="font-medium text-theme-text">{{ row.severity }}</span>
            </span>
            <span class="tabular-nums text-theme-text-muted">{{ row.count }}</span>
          </div>
          <div class="h-2 overflow-hidden rounded-sm bg-theme-text/5">
            <div
              class="h-full rounded-sm"
              :class="severityTokens(row.severity).dot"
              :style="{ width: maxCount > 0 ? `${Math.max(4, (row.count / maxCount) * 100)}%` : '0%' }"
            />
          </div>
        </button>
        <div v-if="items.length === 0" class="flex flex-1 items-center justify-center text-xs italic text-theme-text-muted">
          No incidents in window.
        </div>
      </div>
    </template>

    <template #drill>
      <div v-if="!selectedSeverity" class="text-xs text-theme-text-muted">
        Click a severity bar above to drill down.
      </div>
      <div v-else class="flex flex-col gap-1.5">
        <div class="text-[10px] uppercase tracking-wide text-theme-text-muted">
          {{ selectedSeverity }} — {{ filteredIncidents.length }} incidents
        </div>
        <div v-if="filteredIncidents.length === 0" class="rounded border border-dashed border-theme-border bg-theme-bg/50 p-2 text-xs text-theme-text-muted">
          Add the <span class="font-semibold text-theme-text">Recent Incidents</span> widget to see incident details for this severity.
        </div>
        <div v-else class="flex max-h-40 flex-col gap-1 overflow-y-auto no-scrollbar">
          <div
            v-for="incident in filteredIncidents.slice(0, 10)"
            :key="incident.id"
            class="flex items-center justify-between gap-2 rounded bg-theme-text/5 px-2 py-1 text-xs"
          >
            <span class="truncate text-theme-text">{{ incident.title || incident.summary || incident.id }}</span>
            <span class="shrink-0 text-[10px] text-theme-text-muted">{{ incident.ticketStatus || incident.status }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Severity mix</h3>
          <div class="space-y-2">
            <div v-for="row in items" :key="row.severity">
              <div class="mb-1 flex items-center justify-between text-xs">
                <span class="flex items-center gap-2 capitalize">
                  <span class="h-2 w-2 rounded-full" :class="severityTokens(row.severity).dot" />
                  {{ row.severity }}
                </span>
                <span class="tabular-nums">{{ row.count }}</span>
              </div>
              <div class="h-2 overflow-hidden rounded-sm bg-theme-text/5">
                <div class="h-full" :class="severityTokens(row.severity).dot" :style="{ width: maxCount > 0 ? `${(row.count / maxCount) * 100}%` : '0%' }" />
              </div>
            </div>
          </div>
        </section>

        <section>
          <h3 class="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-theme-text-muted">
            <span>Total trend</span>
            <span class="text-[10px] normal-case text-theme-text-muted">Samples {{ sampleCountLabel }}</span>
          </h3>
          <WidgetSparkline :points="totalSeries.points.value" :width="320" :height="56" />
        </section>

        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Top contributing rules</h3>
          <div v-if="topRules.length === 0" class="text-xs text-theme-text-muted">
            Add the Recent Incidents widget to see contributing rule IDs.
          </div>
          <ul v-else class="space-y-1 text-xs">
            <li v-for="rule in topRules" :key="rule.key" class="flex justify-between gap-2 rounded bg-theme-text/5 px-2 py-1">
              <span class="truncate font-mono text-theme-text">{{ rule.key }}</span>
              <span class="tabular-nums text-theme-text-muted">{{ rule.count }}</span>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
