<script setup lang="ts">
import { computed } from 'vue'
import { Waves } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

type FeedItem = {
  id: string
  ts: string
  sourceIp: string
  action: string
  severity: string
  message: string
  policy: string
}

const items = computed<FeedItem[]>(() =>
  Array.isArray(props.data?.items) ? props.data.items : []
)

const source = computed(() => props.data?.source ?? 'siem')

function severityClass(severity: string): string {
  switch ((severity ?? '').toLowerCase()) {
    case 'critical': return 'bg-red-500/20 text-red-300 border-red-500/30'
    case 'high': return 'bg-orange-500/20 text-orange-300 border-orange-500/30'
    case 'medium': return 'bg-amber-500/20 text-amber-300 border-amber-500/30'
    default: return 'bg-theme-text/10 text-theme-text-muted border-theme-border'
  }
}

function formatTs(ts: string): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ts
  }
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="WAF DoS Events"
    subtitle="Live event feed"
    :icon="Waves"
    source="fortiweb"
    disable-drill
  >
    <template #glance>
      <div class="mb-1 flex items-center justify-between text-[10px] text-theme-text-muted">
        <span>{{ items.length }} events</span>
        <span>{{ source }}</span>
      </div>
      <div v-if="items.length === 0">
        <WidgetEmptyState title="No DoS events." />
      </div>
      <div v-else class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar">
        <div
          v-for="(item, idx) in items.slice(0, 10)"
          :key="item.id ?? String(idx)"
          class="rounded border border-theme-border/30 bg-theme-text/5 px-2 py-1.5 text-xs"
        >
          <div class="flex items-center justify-between gap-2">
            <span
              class="rounded border px-1 py-0.5 text-[10px] font-medium uppercase"
              :class="severityClass(item.severity)"
            >{{ item.severity }}</span>
            <span class="font-mono text-[10px] text-theme-text-muted">{{ formatTs(item.ts) }}</span>
          </div>
          <div class="mt-1 truncate text-theme-text">{{ item.message }}</div>
          <div class="mt-0.5 flex gap-2 text-[10px] text-theme-text-muted">
            <span class="font-mono">{{ item.sourceIp || '—' }}</span>
            <span v-if="item.action" class="uppercase">{{ item.action }}</span>
            <span v-if="item.policy" class="truncate">{{ item.policy }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold uppercase tracking-wide text-theme-text-muted">All events</div>
        <div v-if="items.length === 0" class="text-xs text-theme-text-muted">No data.</div>
        <div v-else class="max-h-80 overflow-y-auto no-scrollbar space-y-1">
          <div
            v-for="(item, idx) in items"
            :key="item.id ?? String(idx)"
            class="rounded border border-theme-border/30 bg-theme-text/5 px-2 py-1.5 text-xs"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="rounded border px-1 py-0.5 text-[10px] font-medium uppercase" :class="severityClass(item.severity)">{{ item.severity }}</span>
              <span class="font-mono text-[10px] text-theme-text-muted">{{ formatTs(item.ts) }}</span>
            </div>
            <div class="mt-1 text-theme-text">{{ item.message }}</div>
            <div class="mt-0.5 flex gap-2 text-[10px] text-theme-text-muted">
              <span class="font-mono">{{ item.sourceIp || '—' }}</span>
              <span v-if="item.action" class="uppercase">{{ item.action }}</span>
              <span v-if="item.policy">{{ item.policy }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
