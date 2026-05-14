<script setup lang="ts">
import { computed } from 'vue'
import { ListChecks } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetEmptyState from './shell/WidgetEmptyState.vue'
import WidgetSlaBadge from './shell/WidgetSlaBadge.vue'

const props = defineProps<{ data: any, catalogId?: string }>()

const events = computed(() => Array.isArray(props.data?.events) ? props.data.events : [])
const summary = computed(() => ({
  total: Number(props.data?.summary?.total ?? events.value.length),
  blocked: Number(props.data?.summary?.blocked ?? 0),
  highSeverity: Number(props.data?.summary?.highSeverity ?? 0),
}))

function eventKey(event: any, index: string | number) {
  return String(event?.id || `${event?.timestamp || 'event'}-${index}`)
}

function severityClass(severity: string | undefined) {
  switch (String(severity || '').toLowerCase()) {
    case 'critical':
      return 'text-red-300 bg-red-500/10 border-red-400/30'
    case 'high':
      return 'text-amber-200 bg-amber-500/10 border-amber-400/30'
    case 'medium':
      return 'text-blue-200 bg-blue-500/10 border-blue-400/30'
    case 'low':
      return 'text-emerald-200 bg-emerald-500/10 border-emerald-400/30'
    default:
      return 'text-theme-text-muted bg-theme-text/5 border-theme-border'
  }
}

function eventType(event: any) {
  return [event?.type, event?.subtype].filter(Boolean).join(' / ') || 'event'
}
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-recent-events'"
    title="Recent Events"
    subtitle="Normalized FortiGate event feed"
    :icon="ListChecks"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
      <div class="flex items-center justify-end text-xs text-theme-text-muted">
        <div class="text-right">
          <div><span class="font-bold text-theme-text">{{ summary.total }}</span> total</div>
          <div><span class="font-bold text-amber-200">{{ summary.highSeverity }}</span> high</div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-2 text-xs">
        <div class="rounded-md bg-theme-text/5 p-2">
          <div class="text-theme-text-muted">Blocked</div>
          <div class="text-lg font-bold text-red-300">{{ summary.blocked }}</div>
        </div>
        <div class="rounded-md bg-theme-text/5 p-2">
          <div class="text-theme-text-muted">High severity</div>
          <div class="text-lg font-bold text-amber-200">{{ summary.highSeverity }}</div>
        </div>
      </div>

      <div class="flex-1 space-y-2 overflow-y-auto pr-1 no-scrollbar">
        <div
          v-for="(event, index) in events"
          :key="eventKey(event, index)"
          class="rounded-md border border-theme-border/60 bg-theme-text/5 p-2 text-sm"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="truncate font-semibold text-theme-text">{{ event.message || 'FortiGate event' }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-theme-text-muted">
                <WidgetSlaBadge :created-at="event.timestamp" />
                <span>{{ eventType(event) }}</span>
                <span v-if="event.sourceIp" class="font-mono">{{ event.sourceIp }}</span>
                <span v-if="event.destinationIp" class="font-mono">to {{ event.destinationIp }}</span>
                <span v-if="event.action" class="uppercase">{{ event.action }}</span>
              </div>
            </div>
            <span class="shrink-0 rounded border px-2 py-1 text-xs font-bold uppercase" :class="severityClass(event.severity)">
              {{ event.severity || 'unknown' }}
            </span>
          </div>
        </div>

        <WidgetEmptyState
          v-if="events.length === 0"
          title="No recent events returned."
          hint="FortiGate event feed is currently empty for this integration."
        />
      </div>
    </template>
  </WidgetShell>
</template>
