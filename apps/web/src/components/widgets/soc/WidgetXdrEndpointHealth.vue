<script setup lang="ts">
import { computed, ref } from 'vue'
import { Monitor } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import WidgetSparkline from '../shell/WidgetSparkline.vue'
import { useWidgetSeries } from '../../../composables/useWidgetSeries'
import { ageMs, formatAge } from '../../../composables/useSocMetrics'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const endpoints = computed<any[]>(() => Array.isArray(props.data?.endpoints) ? props.data.endpoints : [])
const total = computed(() => Number(props.data?.total) || endpoints.value.length)
const summary = computed<Record<string, number>>(() => {
  const raw = props.data?.summary
  if (!raw || typeof raw !== 'object') return {}
  return Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, Number(v) || 0]))
})
const unhealthyCount = computed(() => (summary.value.unhealthy ?? 0) + (summary.value.offline ?? 0) + (summary.value.degraded ?? 0))
const healthyCount = computed(() => (summary.value.healthy ?? 0) + (summary.value.online ?? 0))

const totalSeries = useWidgetSeries(props.instanceId, 'total')
const unhealthySeries = useWidgetSeries(props.instanceId, 'unhealthy')

const filterHealth = ref<string | null>(null)

function selectHealth(health: string) {
  filterHealth.value = filterHealth.value === health ? null : health
}

const filteredEndpoints = computed(() => {
  if (!filterHealth.value) return endpoints.value
  return endpoints.value.filter((ep: any) => String(ep?.health ?? '').toLowerCase() === filterHealth.value)
})

function healthClass(health: unknown) {
  switch (String(health ?? '').toLowerCase()) {
    case 'healthy':
    case 'online': return 'bg-emerald-400'
    case 'degraded':
    case 'warning': return 'bg-amber-400'
    case 'unhealthy':
    case 'offline': return 'bg-red-400'
    default: return 'bg-theme-text-muted'
  }
}

const healthBuckets = computed(() => {
  const order = ['unhealthy', 'offline', 'degraded', 'healthy', 'online', 'unknown']
  return Object.entries(summary.value)
    .sort(([a], [b]) => {
      const ai = order.indexOf(a.toLowerCase())
      const bi = order.indexOf(b.toLowerCase())
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
    })
})
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="Endpoint Health"
    subtitle="XDR endpoint inventory"
    :icon="Monitor"
    source="xdr_rico"
  >
    <template #glance>
      <div class="grid grid-cols-3 gap-2">
        <WidgetKpiTile label="Total" :value="total" :series="totalSeries.points.value" />
        <WidgetKpiTile label="Unhealthy" :value="unhealthyCount" :series="unhealthySeries.points.value" :tone="unhealthyCount > 0 ? 'critical' : 'default'" />
        <WidgetKpiTile label="Healthy" :value="healthyCount" tone="healthy" />
      </div>
      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar">
        <button
          v-for="[bucket, count] in healthBuckets"
          :key="bucket"
          type="button"
          class="flex items-center justify-between gap-2 rounded border border-theme-border/40 bg-theme-text/5 px-2 py-1 text-xs transition-colors hover:border-theme-primary/40"
          :class="filterHealth === bucket ? 'border-theme-primary/60 bg-theme-primary/10' : ''"
          @click.stop="selectHealth(bucket)"
        >
          <span class="flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full" :class="healthClass(bucket)" />
            <span class="capitalize text-theme-text">{{ bucket }}</span>
          </span>
          <span class="tabular-nums text-theme-text-muted">{{ count }}</span>
        </button>
        <div v-if="healthBuckets.length === 0" class="flex flex-1 items-center justify-center text-xs italic text-theme-text-muted">
          No endpoints.
        </div>
      </div>
    </template>

    <template #drill>
      <div v-if="!filterHealth" class="text-xs text-theme-text-muted">
        Select a health bucket above to see matching endpoints.
      </div>
      <div v-else class="flex flex-col gap-1">
        <div class="text-[10px] uppercase tracking-wide text-theme-text-muted">
          {{ filterHealth }} — {{ filteredEndpoints.length }} endpoints
        </div>
        <div class="flex max-h-40 flex-col gap-1 overflow-y-auto no-scrollbar">
          <div
            v-for="endpoint in filteredEndpoints.slice(0, 10)"
            :key="endpoint.id"
            class="flex items-center justify-between gap-2 rounded bg-theme-text/5 px-2 py-1 text-xs"
          >
            <span class="truncate text-theme-text">{{ endpoint.hostname || endpoint.id }}</span>
            <span class="shrink-0 text-[10px] text-theme-text-muted">{{ endpoint.os || endpoint.ip || '--' }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section>
          <h3 class="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-theme-text-muted">
            <span>Unhealthy trend</span>
            <span class="text-[10px] normal-case">Samples {{ unhealthySeries.sampleCount.value }}/{{ unhealthySeries.capacity }}</span>
          </h3>
          <WidgetSparkline :points="unhealthySeries.points.value" :width="320" :height="56" />
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Endpoint inventory</h3>
          <table class="w-full text-xs">
            <thead class="text-[10px] uppercase tracking-wide text-theme-text-muted">
              <tr>
                <th class="text-left font-semibold">Host</th>
                <th class="text-left font-semibold">OS</th>
                <th class="text-left font-semibold">Health</th>
                <th class="text-right font-semibold">Last seen</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="endpoint in endpoints" :key="endpoint.id" class="border-t border-theme-border/40">
                <td class="py-1 pr-2 font-mono text-theme-text">{{ endpoint.hostname || endpoint.id }}</td>
                <td class="py-1 pr-2 text-theme-text-muted">{{ endpoint.os || '--' }}</td>
                <td class="py-1 pr-2 capitalize">{{ endpoint.health || '--' }}</td>
                <td class="py-1 text-right tabular-nums text-theme-text-muted">{{ formatAge(ageMs(endpoint.lastSeenAt)) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
