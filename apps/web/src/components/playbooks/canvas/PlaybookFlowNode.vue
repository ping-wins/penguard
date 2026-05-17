<script setup lang="ts">
import { Handle, Position, type NodeProps } from '@vue-flow/core'
import type { PlaybookCanvasNodeData } from '../../../utils/playbookGraph'

const props = defineProps<NodeProps<PlaybookCanvasNodeData>>()
</script>

<template>
  <div
    class="min-w-[210px] rounded border bg-theme-panel px-3 py-2 text-xs shadow-lg"
    :class="props.data.sensitive ? 'border-red-400/40' : 'border-theme-border'"
    :data-test="`playbook-canvas-node-${props.id}`"
  >
    <Handle type="target" :position="Position.Left" />
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <div class="truncate font-semibold text-theme-text">{{ props.data.label }}</div>
        <div class="mt-0.5 truncate font-mono text-[10px] text-theme-text-muted">
          {{ props.data.nodeType }}
        </div>
      </div>
      <span
        class="shrink-0 rounded border px-1.5 py-0.5 text-[10px]"
        :class="props.data.liveAvailable ? 'border-amber-400/40 text-amber-100' : 'border-sky-400/30 text-sky-100'"
      >
        {{ props.data.liveAvailable ? 'approval' : 'dry-run' }}
      </span>
    </div>
    <div class="mt-2 flex flex-wrap gap-1">
      <span class="rounded border border-theme-border bg-theme-bg/70 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
        {{ props.data.category }}
      </span>
      <span class="rounded border border-theme-border bg-theme-bg/70 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
        {{ props.data.boundary }}
      </span>
    </div>
    <Handle type="source" :position="Position.Right" />
  </div>
</template>
