<script setup lang="ts">
import { computed } from 'vue'
import { Globe, Monitor, User, Network, Hash } from 'lucide-vue-next'

const props = defineProps<{
  field?: string | null
  value: string | number | null | undefined
  count?: number | null
  selected?: boolean
}>()

const emit = defineEmits<{
  (e: 'click', payload: { field: string | null, value: string }): void
}>()

const fieldKey = computed(() => String(props.field ?? '').toLowerCase())

const icon = computed(() => {
  if (fieldKey.value.includes('ip')) return Globe
  if (fieldKey.value.includes('host') || fieldKey.value.includes('endpoint')) return Monitor
  if (fieldKey.value.includes('user') || fieldKey.value.includes('account')) return User
  if (fieldKey.value.includes('interface') || fieldKey.value.includes('port')) return Network
  return Hash
})

const valueLabel = computed(() => String(props.value ?? ''))
const countLabel = computed(() => (props.count === null || props.count === undefined ? null : String(props.count)))
const interactive = computed(() => Boolean(props.field) || valueLabel.value.length > 0)

function handleClick() {
  if (!interactive.value) return
  emit('click', { field: props.field ?? null, value: valueLabel.value })
}
</script>

<template>
  <button
    type="button"
    :disabled="!interactive"
    class="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium transition-colors"
    :class="[
      selected
        ? 'border-theme-primary/60 bg-theme-primary/15 text-theme-text'
        : 'border-theme-border bg-theme-text/5 text-theme-text hover:border-theme-primary/40 hover:bg-theme-text/10',
      interactive ? 'cursor-pointer' : 'cursor-default opacity-70',
    ]"
    @click="handleClick"
  >
    <component :is="icon" :size="12" class="text-theme-text-muted" />
    <span class="max-w-[12rem] truncate font-mono">{{ valueLabel || '--' }}</span>
    <span v-if="countLabel" class="ml-1 rounded bg-theme-bg/80 px-1.5 py-0.5 text-[10px] tabular-nums text-theme-text-muted">
      {{ countLabel }}
    </span>
  </button>
</template>
