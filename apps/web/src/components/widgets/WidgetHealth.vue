<script setup lang="ts">
import { computed } from 'vue'
import { Server } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetKpiTile from './shell/WidgetKpiTile.vue'
import { useWidgetSeries } from '../../composables/useWidgetSeries'

const props = defineProps<{ data: any, catalogId?: string, instanceId?: string }>()

const deviceTitle = computed(() => props.data?.hostname || props.data?.model || 'FortiGate')
const deviceMeta = computed(() => {
  return [props.data?.model, props.data?.version].filter(Boolean).join(' / ')
})
const subtitleText = computed(() => deviceMeta.value ? `${deviceTitle.value} · ${deviceMeta.value}` : deviceTitle.value)

const uptimeLabel = computed(() => {
  const rawUptime = props.data?.uptimeSeconds
  if (rawUptime === null || rawUptime === undefined || rawUptime === '') return '--'
  const uptime = Number(rawUptime)
  if (!Number.isFinite(uptime) || uptime < 0) return '--'
  return formatDurationSeconds(uptime)
})

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

const instance = computed(() => props.instanceId || `fortigate-system-status::${props.catalogId ?? ''}`)
const cpuSeries = useWidgetSeries(instance.value, 'cpu')
const memorySeries = useWidgetSeries(instance.value, 'memory')
const sessionsSeries = useWidgetSeries(instance.value, 'sessions')

function tone(pct: number): 'default' | 'warning' | 'critical' | 'healthy' {
  if (!Number.isFinite(pct)) return 'default'
  if (pct >= 85) return 'critical'
  if (pct >= 70) return 'warning'
  return 'healthy'
}
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-system-status'"
    title="System Status"
    :subtitle="subtitleText"
    :icon="Server"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
      <div class="grid grid-cols-2 gap-2 flex-1">
        <WidgetKpiTile label="CPU" :value="`${data?.cpu ?? 0}%`" :series="cpuSeries.points.value" :tone="tone(Number(data?.cpu))" />
        <WidgetKpiTile label="Memory" :value="`${data?.memory ?? 0}%`" :series="memorySeries.points.value" :tone="tone(Number(data?.memory))" />
        <div class="col-span-2">
          <WidgetKpiTile
            label="Active Sessions"
            :value="data?.sessions?.toLocaleString() || 0"
            :series="sessionsSeries.points.value"
          />
        </div>
        <div class="col-span-2 bg-theme-text/5 rounded-md p-3 flex flex-col justify-center border-l-4 border-cyan-500">
          <span class="text-[10px] text-theme-text-muted uppercase font-semibold tracking-wide">Uptime</span>
          <span class="text-xl font-bold text-theme-text tracking-tight">{{ uptimeLabel }}</span>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
