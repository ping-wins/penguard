<script setup lang="ts">
import { computed } from 'vue'
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@vue-flow/core'

const props = defineProps<EdgeProps>()
const path = computed(() => getBezierPath(props))
const condition = computed(() => {
  const data = props.data as { condition?: string } | undefined
  return data?.condition || 'success'
})
</script>

<script lang="ts">
export default {
  inheritAttrs: false,
}
</script>

<template>
  <BaseEdge :path="path[0]" :marker-end="props.markerEnd" />
  <EdgeLabelRenderer>
    <div
      class="nodrag nopan rounded border border-theme-border bg-theme-panel px-1.5 py-0.5 text-[10px] font-semibold text-theme-text-muted shadow"
      :style="{
        pointerEvents: 'all',
        position: 'absolute',
        transform: `translate(-50%, -50%) translate(${path[1]}px, ${path[2]}px)`,
      }"
    >
      {{ condition }}
    </div>
  </EdgeLabelRenderer>
</template>
