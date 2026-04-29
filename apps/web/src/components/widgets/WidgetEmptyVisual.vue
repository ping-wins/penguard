<script setup lang="ts">
import { computed } from 'vue'
import { Activity, BarChart2, Database, Network, Table } from 'lucide-vue-next'
import { visualTemplatesById } from '../../constants/visualTemplates'

const props = defineProps<{
  catalogId: string
}>()

const template = computed(() => visualTemplatesById[props.catalogId])

const icon = computed(() => {
  switch (template.value?.kind) {
    case 'card':
    case 'gauge':
      return Activity
    case 'table':
      return Table
    case 'bar':
    case 'line':
      return BarChart2
    case 'feed':
      return Database
    case 'list':
      return Network
    default:
      return BarChart2
  }
})
</script>

<template>
  <div class="flex h-full flex-col items-center justify-center gap-3 text-center text-theme-text-muted">
    <div class="flex size-12 items-center justify-center rounded-md border border-dashed border-theme-border bg-theme-bg/60 text-theme-primary">
      <component :is="icon" :size="24" />
    </div>
    <div class="min-w-0">
      <h3 class="text-sm font-semibold text-theme-text">{{ template?.title ?? 'Empty visual' }}</h3>
      <p class="mt-1 max-w-[14rem] text-xs leading-relaxed">No data fields assigned</p>
    </div>
    <span class="rounded border border-theme-border px-2 py-1 text-[10px] uppercase tracking-wider">
      {{ template?.kind ?? 'visual' }}
    </span>
  </div>
</template>
