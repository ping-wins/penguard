<script setup lang="ts">
import { computed, type Component } from 'vue'
import { ChevronRight, Maximize2, Minimize2, Activity } from 'lucide-vue-next'
import { useWidgetDrill } from '../../../composables/useWidgetDrill'
import { ageMs, formatAge } from '../../../composables/useSocMetrics'
import { useWidgetCompactStore } from '../../../stores/useWidgetCompactStore'
import WidgetDrillModal from './WidgetDrillModal.vue'

const props = withDefaults(defineProps<{
  widgetId: string
  title: string
  subtitle?: string
  icon?: Component
  source?: string
  lastUpdated?: string | null
  emptyMessage?: string
  disableDrill?: boolean
  disableDetail?: boolean
}>(), {
  disableDrill: false,
  disableDetail: false,
})

const drill = useWidgetDrill()
const compactStore = useWidgetCompactStore()
const isCompact = computed(() => compactStore.isCompact)

const updatedAgeLabel = computed(() => {
  const ms = ageMs(props.lastUpdated ?? null)
  if (ms === null) return null
  return `${formatAge(ms)} ago`
})

const sourcePill = computed(() => {
  if (!props.source) return null
  switch (props.source) {
    case 'siem_kowalski': return { label: 'SIEM', tone: 'bg-blue-500/10 text-blue-200 border-blue-400/30' }
    case 'xdr_rico': return { label: 'XDR', tone: 'bg-fuchsia-500/10 text-fuchsia-200 border-fuchsia-400/30' }
    case 'soar_skipper': return { label: 'SOAR', tone: 'bg-amber-500/10 text-amber-200 border-amber-400/30' }
    case 'fortigate': return { label: 'FortiGate', tone: 'bg-emerald-500/10 text-emerald-200 border-emerald-400/30' }
    case 'fortiweb': return { label: 'FortiWeb', tone: 'bg-orange-500/10 text-orange-200 border-orange-400/30' }
    default: return { label: props.source, tone: 'bg-theme-text/10 text-theme-text-muted border-theme-border' }
  }
})

function handleBodyClick() {
  if (props.disableDrill || drill.isDetail.value) return
  if (drill.isDrill.value) drill.close()
  else drill.openDrill()
}

function handleDetailToggle(event: MouseEvent) {
  event.stopPropagation()
  if (drill.isDetail.value) drill.close()
  else drill.openDetail()
}
</script>

<template>
  <div
    class="flex h-full w-full flex-col"
    :class="isCompact ? 'gap-1.5' : 'gap-3'"
    :data-widget-id="props.widgetId"
    :data-mode="drill.mode.value"
    :data-compact="isCompact ? 'true' : 'false'"
  >
    <header class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2 text-theme-text">
        <component v-if="props.icon" :is="props.icon" :size="isCompact ? 16 : 20" class="shrink-0 text-theme-primary" />
        <component v-else :is="Activity" :size="isCompact ? 16 : 20" class="shrink-0 text-theme-primary" />
        <div class="min-w-0">
          <div class="truncate font-bold leading-tight" :class="isCompact ? 'text-sm' : 'text-base'">{{ props.title }}</div>
          <div v-if="props.subtitle && !isCompact" class="truncate text-[11px] text-theme-text-muted">{{ props.subtitle }}</div>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-1.5">
        <span
          v-if="sourcePill"
          class="rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
          :class="sourcePill.tone"
        >{{ sourcePill.label }}</span>
        <span v-if="updatedAgeLabel" class="text-[10px] text-theme-text-muted tabular-nums">{{ updatedAgeLabel }}</span>
        <button
          v-if="!props.disableDetail"
          type="button"
          class="rounded p-1 text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text"
          :aria-label="drill.isDetail.value ? 'Close detail view' : 'Open detail view'"
          @click="handleDetailToggle"
        >
          <component :is="drill.isDetail.value ? Minimize2 : Maximize2" :size="14" />
        </button>
      </div>
    </header>

    <div
      class="flex min-h-0 flex-1 flex-col gap-2"
      :class="{ 'cursor-pointer': !props.disableDrill && !drill.isDetail.value }"
      :role="props.disableDrill ? undefined : 'button'"
      :tabindex="props.disableDrill ? undefined : 0"
      @click="handleBodyClick"
      @keydown.enter.prevent="handleBodyClick"
      @keydown.space.prevent="handleBodyClick"
    >
      <slot name="glance" />
      <div
        v-if="drill.isDrill.value && $slots.drill"
        class="rounded-md border border-theme-primary/30 bg-theme-primary/5 p-2"
        @click.stop
      >
        <div class="mb-1 flex items-center justify-between">
          <span class="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-theme-primary">
            <ChevronRight :size="10" /> Drill-down
          </span>
          <button
            type="button"
            class="text-[10px] text-theme-text-muted hover:text-theme-text"
            @click.stop="drill.close"
          >Close</button>
        </div>
        <slot name="drill" :close="drill.close" />
      </div>
    </div>

    <WidgetDrillModal
      v-if="drill.isDetail.value && $slots.detail"
      :title="props.title"
      :subtitle="props.subtitle"
      @close="drill.close"
    >
      <slot name="detail" :close="drill.close" />
    </WidgetDrillModal>
  </div>
</template>
