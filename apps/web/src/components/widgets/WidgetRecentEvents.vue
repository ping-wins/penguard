<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListChecks } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetEmptyState from './shell/WidgetEmptyState.vue'
import WidgetSlaBadge from './shell/WidgetSlaBadge.vue'

const props = defineProps<{ data: any, catalogId?: string }>()
const { t } = useI18n()

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
  return [event?.type, event?.subtype].filter(Boolean).join(' / ') || t('widgets.recentEvents.typeFallback')
}
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-recent-events'"
    :title="t('widgets.recentEvents.title')"
    :subtitle="t('widgets.recentEvents.subtitle')"
    :icon="ListChecks"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
      <div class="flex items-center justify-end text-xs text-theme-text-muted">
        <div class="text-right">
          <div><span class="font-bold text-theme-text">{{ summary.total }}</span> {{ t('widgets.recentEvents.totalLabel') }}</div>
          <div><span class="font-bold text-amber-200">{{ summary.highSeverity }}</span> {{ t('widgets.recentEvents.highLabel') }}</div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-2 text-xs">
        <div class="rounded-md bg-theme-text/5 p-2">
          <div class="text-theme-text-muted">{{ t('widgets.recentEvents.blocked') }}</div>
          <div class="text-lg font-bold text-red-300">{{ summary.blocked }}</div>
        </div>
        <div class="rounded-md bg-theme-text/5 p-2">
          <div class="text-theme-text-muted">{{ t('widgets.recentEvents.highSeverity') }}</div>
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
              <div class="truncate font-semibold text-theme-text">{{ event.message || t('widgets.recentEvents.eventFallback') }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-theme-text-muted">
                <WidgetSlaBadge :created-at="event.timestamp" />
                <span>{{ eventType(event) }}</span>
                <span v-if="event.sourceIp" class="font-mono">{{ event.sourceIp }}</span>
                <span v-if="event.destinationIp" class="font-mono">{{ t('widgets.recentEvents.to', { ip: event.destinationIp }) }}</span>
                <span v-if="event.action" class="uppercase">{{ event.action }}</span>
              </div>
            </div>
            <span class="shrink-0 rounded border px-2 py-1 text-xs font-bold uppercase" :class="severityClass(event.severity)">
              {{ event.severity || t('widgets.recentEvents.unknownSeverity') }}
            </span>
          </div>
        </div>

        <WidgetEmptyState
          v-if="events.length === 0"
          :title="t('widgets.recentEvents.emptyTitle')"
          :hint="t('widgets.recentEvents.emptyHint')"
        />
      </div>
    </template>
  </WidgetShell>
</template>
