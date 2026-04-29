<script setup lang="ts">
import { computed } from 'vue'
import { Activity, BarChart2, Database, Network, Table } from 'lucide-vue-next'
import { visualTemplatesById } from '../../constants/visualTemplates'
import type { WidgetFieldBinding } from '../../types/dashboard'

const props = defineProps<{
  catalogId: string
  fieldBindings?: WidgetFieldBinding[]
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
      <p v-if="!fieldBindings?.length" class="mt-1 max-w-[14rem] text-xs leading-relaxed">Drop a live data field here</p>
      <div v-else class="mt-2 flex max-w-[15rem] flex-col gap-1 text-left">
        <div
          v-for="field in fieldBindings"
          :key="field.fieldId"
          class="rounded border border-theme-border bg-theme-bg/70 px-2 py-1.5"
        >
          <div class="truncate text-xs font-semibold text-theme-text">{{ field.label }}</div>
          <div class="mt-0.5 flex items-center gap-2 text-[10px] text-theme-text-muted">
            <span>{{ field.type }}<template v-if="field.unit"> / {{ field.unit }}</template></span>
            <span class="truncate">{{ field.source }}</span>
          </div>
        </div>
      </div>
    </div>
    <span class="rounded border border-theme-border px-2 py-1 text-[10px] uppercase tracking-wider">
      {{ template?.kind ?? 'visual' }}
    </span>
  </div>
</template>
