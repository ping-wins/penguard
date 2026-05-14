<script setup lang="ts">
import { computed } from 'vue'
import { Activity } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetSparkline from './shell/WidgetSparkline.vue'
import { useWidgetSeries } from '../../composables/useWidgetSeries'

const props = defineProps<{ data: any, catalogId?: string, instanceId?: string }>()

const instance = computed(() => props.instanceId || `fortigate-kpi-sessions::${props.catalogId ?? ''}`)
const sessionsSeries = useWidgetSeries(instance.value, 'sessions')

const delta = computed(() => {
  const points = sessionsSeries.points.value
  if (points.length < 2) return null
  return points[points.length - 1] - points[points.length - 2]
})
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-kpi-sessions'"
    title="Active Sessions"
    subtitle="FortiGate concurrent sessions"
    :icon="Activity"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
      <div class="h-full w-full flex flex-col items-center justify-center relative gap-2 p-2">
        <div class="text-5xl font-bold text-theme-text tracking-tight tabular-nums">
          {{ data?.sessions?.toLocaleString() || 0 }}
        </div>
        <WidgetSparkline :points="sessionsSeries.points.value" :width="160" :height="32" />
        <div
          v-if="delta !== null"
          class="mt-1 text-xs flex items-center gap-1 px-2 py-1 rounded-full"
          :class="delta > 0 ? 'text-amber-300 bg-amber-400/10' : delta < 0 ? 'text-emerald-300 bg-emerald-400/10' : 'text-theme-text-muted bg-theme-text/5'"
        >
          <span class="tabular-nums">{{ delta > 0 ? '+' : '' }}{{ delta }}</span>
          <span>vs last poll</span>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
