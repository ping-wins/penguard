<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  points: number[]
  width?: number
  height?: number
  strokeClass?: string
  fillClass?: string
  showArea?: boolean
  ariaLabel?: string
}>(), {
  width: 96,
  height: 24,
  strokeClass: 'stroke-theme-primary',
  fillClass: 'fill-theme-primary/20',
  showArea: true,
  ariaLabel: 'Trend',
})

const hasPoints = computed(() => Array.isArray(props.points) && props.points.length > 0)

const normalized = computed(() => {
  if (!hasPoints.value) return [] as Array<{ x: number, y: number }>
  const values = props.points.filter((v) => typeof v === 'number' && Number.isFinite(v))
  if (values.length === 0) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const stepX = values.length === 1 ? 0 : props.width / (values.length - 1)
  return values.map((value, index) => ({
    x: values.length === 1 ? props.width / 2 : index * stepX,
    y: props.height - ((value - min) / range) * props.height,
  }))
})

const polylinePoints = computed(() => normalized.value.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '))
const areaPath = computed(() => {
  if (normalized.value.length === 0) return ''
  const first = normalized.value[0]
  const last = normalized.value[normalized.value.length - 1]
  const lineTo = normalized.value.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  return `M ${first.x.toFixed(1)} ${props.height} ${lineTo} L ${last.x.toFixed(1)} ${props.height} Z`
})
</script>

<template>
  <svg
    :width="width"
    :height="height"
    :viewBox="`0 0 ${width} ${height}`"
    role="img"
    :aria-label="ariaLabel"
    class="shrink-0"
  >
    <template v-if="normalized.length > 1">
      <path v-if="showArea" :d="areaPath" :class="fillClass" stroke="none" />
      <polyline
        :points="polylinePoints"
        fill="none"
        :class="strokeClass"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </template>
    <template v-else-if="normalized.length === 1">
      <circle :cx="normalized[0].x" :cy="normalized[0].y" r="2" :class="strokeClass" stroke="none" />
    </template>
    <template v-else>
      <line
        :x1="0"
        :y1="height / 2"
        :x2="width"
        :y2="height / 2"
        class="stroke-theme-text-muted/30"
        stroke-width="1"
        stroke-dasharray="2 3"
      />
    </template>
  </svg>
</template>
