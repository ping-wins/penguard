<script setup lang="ts">
import { computed } from 'vue'
import WidgetSparkline from './WidgetSparkline.vue'

const props = defineProps<{
  label: string
  value: number | string
  series?: number[]
  delta?: number | null
  unit?: string
  tone?: 'default' | 'critical' | 'warning' | 'healthy'
}>()

const toneClass = computed(() => {
  switch (props.tone) {
    case 'critical': return 'border-l-4 border-red-500'
    case 'warning': return 'border-l-4 border-amber-500'
    case 'healthy': return 'border-l-4 border-emerald-500'
    default: return 'border-l-4 border-theme-primary/60'
  }
})

const deltaLabel = computed(() => {
  if (props.delta === null || props.delta === undefined || !Number.isFinite(props.delta)) return null
  const sign = props.delta > 0 ? '+' : ''
  return `${sign}${props.delta}`
})

const deltaClass = computed(() => {
  if (props.delta === null || props.delta === undefined) return 'text-theme-text-muted'
  if (props.delta > 0) return 'text-red-300'
  if (props.delta < 0) return 'text-emerald-300'
  return 'text-theme-text-muted'
})
</script>

<template>
  <div class="flex flex-col justify-between rounded-md bg-theme-text/5 p-3" :class="toneClass">
    <div class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
      {{ label }}
    </div>
    <div class="mt-1 flex items-end justify-between gap-2">
      <div class="flex items-baseline gap-1">
        <span class="text-2xl font-bold leading-none text-theme-text tabular-nums">{{ value }}</span>
        <span v-if="unit" class="text-xs text-theme-text-muted">{{ unit }}</span>
      </div>
      <div class="flex flex-col items-end gap-0.5">
        <WidgetSparkline v-if="series && series.length > 0" :points="series" :width="64" :height="20" />
        <span v-if="deltaLabel" class="text-[10px] font-semibold tabular-nums" :class="deltaClass">
          {{ deltaLabel }}
        </span>
      </div>
    </div>
  </div>
</template>
