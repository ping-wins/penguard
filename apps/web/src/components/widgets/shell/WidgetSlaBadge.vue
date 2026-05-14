<script setup lang="ts">
import { computed } from 'vue'
import { Clock3 } from 'lucide-vue-next'
import { slaBucket, DEFAULT_SLA_THRESHOLDS, formatAge, ageMs, type SlaThresholds } from '../../../composables/useSocMetrics'

const props = defineProps<{
  createdAt?: string | null
  ageMs?: number | null
  thresholds?: SlaThresholds
}>()

const resolvedAge = computed(() => {
  if (props.ageMs !== undefined && props.ageMs !== null) return props.ageMs
  return ageMs(props.createdAt ?? null)
})

const bucket = computed(() => slaBucket(resolvedAge.value, props.thresholds ?? DEFAULT_SLA_THRESHOLDS))

const bucketClass = computed(() => {
  switch (bucket.value) {
    case 'red': return 'border-red-400/40 bg-red-500/10 text-red-300'
    case 'amber': return 'border-amber-400/40 bg-amber-500/10 text-amber-200'
    default: return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300'
  }
})

const label = computed(() => formatAge(resolvedAge.value))
</script>

<template>
  <span class="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-semibold tabular-nums" :class="bucketClass">
    <Clock3 :size="10" />
    {{ label }}
  </span>
</template>
