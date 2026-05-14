<script setup lang="ts">
import { computed } from 'vue'
import { Activity } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetEmptyState from './shell/WidgetEmptyState.vue'

const props = defineProps<{ data: any, catalogId?: string }>()

const anomalies = computed(() => Array.isArray(props.data?.anomalies) ? props.data.anomalies : [])
const summary = computed(() => ({
  count: Number(props.data?.summary?.count ?? anomalies.value.length),
  highestSeverity: String(props.data?.summary?.highestSeverity || 'none').toLowerCase(),
}))

function anomalyKey(anomaly: any, index: string | number) {
  return String(anomaly?.id || anomaly?.metric || anomaly?.title || index)
}

function severityClass(severity: string | undefined) {
  switch (String(severity || '').toLowerCase()) {
    case 'critical':
      return 'border-red-400/40 bg-red-950/30 text-red-200'
    case 'warning':
      return 'border-amber-400/40 bg-amber-950/30 text-amber-100'
    case 'healthy':
      return 'border-emerald-400/35 bg-emerald-950/25 text-emerald-100'
    default:
      return 'border-theme-border bg-theme-text/5 text-theme-text'
  }
}

function severityDotClass(severity: string | undefined) {
  switch (String(severity || '').toLowerCase()) {
    case 'critical':
      return 'bg-red-400'
    case 'warning':
      return 'bg-amber-400'
    case 'healthy':
      return 'bg-emerald-400'
    default:
      return 'bg-theme-text-muted'
  }
}

function highestSeverityClass() {
  switch (summary.value.highestSeverity) {
    case 'critical':
      return 'text-red-300 bg-red-500/10 border-red-400/30'
    case 'warning':
      return 'text-amber-200 bg-amber-500/10 border-amber-400/30'
    case 'healthy':
      return 'text-emerald-200 bg-emerald-500/10 border-emerald-400/30'
    default:
      return 'text-theme-text-muted bg-theme-text/5 border-theme-border'
  }
}

function formatValue(anomaly: any) {
  if (anomaly?.value === null || anomaly?.value === undefined || anomaly?.value === '') return 'No value'
  if (anomaly?.unit === 'percent') return `${anomaly.value}%`
  return anomaly?.unit ? `${anomaly.value} ${anomaly.unit}` : String(anomaly.value)
}
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-anomaly-highlights'"
    title="Anomaly Highlights"
    subtitle="Derived anomalies from system and interface signals"
    :icon="Activity"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
      <div class="flex items-center justify-end">
        <span class="rounded border px-2 py-1 text-xs font-semibold uppercase" :class="highestSeverityClass()">
          {{ summary.highestSeverity }}
        </span>
      </div>

      <div class="grid grid-cols-2 gap-2 text-xs">
        <div class="rounded-md bg-theme-text/5 p-2">
          <div class="text-theme-text-muted">Active anomalies</div>
          <div class="text-lg font-bold text-theme-text">{{ summary.count }}</div>
        </div>
        <div class="rounded-md bg-theme-text/5 p-2">
          <div class="text-theme-text-muted">Highest severity</div>
          <div class="text-lg font-bold uppercase text-theme-text">{{ summary.highestSeverity }}</div>
        </div>
      </div>

      <div class="flex-1 space-y-2 overflow-y-auto pr-1 no-scrollbar">
        <div
          v-for="(anomaly, index) in anomalies"
          :key="anomalyKey(anomaly, index)"
          class="rounded-md border p-2 text-sm"
          :class="severityClass(anomaly.severity)"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 font-semibold text-theme-text">
                <span class="h-2 w-2 rounded-full" :class="severityDotClass(anomaly.severity)" />
                <span class="truncate">{{ anomaly.title || 'Anomaly' }}</span>
              </div>
              <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-theme-text-muted">
                <span v-if="anomaly.metric" class="font-mono">{{ anomaly.metric }}</span>
                <span>{{ formatValue(anomaly) }}</span>
                <span class="uppercase">{{ anomaly.severity || 'unknown' }}</span>
              </div>
              <div v-if="anomaly.description" class="mt-1 text-xs text-theme-text-muted">
                {{ anomaly.description }}
              </div>
            </div>
          </div>
        </div>

        <WidgetEmptyState
          v-if="anomalies.length === 0"
          title="No active anomalies"
          hint="FortiGate telemetry is not crossing SOC anomaly thresholds."
        />
      </div>
    </template>
  </WidgetShell>
</template>
