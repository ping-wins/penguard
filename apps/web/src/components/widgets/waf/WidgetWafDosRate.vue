<script setup lang="ts">
import { computed, ref } from 'vue'
import { Activity } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

type Bucket = { ts: string; blocked: number; allowed: number }

const selectedWindow = ref('1h')
const windows = ['15m', '1h', '6h', '24h']

const buckets = computed<Bucket[]>(() =>
  Array.isArray(props.data?.buckets) ? props.data.buckets : []
)

const WINDOW_BUCKET_COUNT: Record<string, number> = { '15m': 15, '1h': 60, '6h': 360, '24h': 1440 }

const visibleBuckets = computed<Bucket[]>(() => {
  const limit = WINDOW_BUCKET_COUNT[selectedWindow.value] ?? buckets.value.length
  return buckets.value.slice(-limit)
})

const maxVal = computed(() =>
  visibleBuckets.value.reduce((m, b) => Math.max(m, b.blocked + b.allowed), 0)
)

const totalBlocked = computed(() => visibleBuckets.value.reduce((s, b) => s + b.blocked, 0))
const totalAllowed = computed(() => visibleBuckets.value.reduce((s, b) => s + b.allowed, 0))
const source = computed(() => props.data?.source ?? 'siem')

function barHeightPct(val: number): string {
  if (maxVal.value === 0) return '0%'
  return `${Math.max(4, (val / maxVal.value) * 100)}%`
}

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts
  }
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="WAF DoS Rate"
    subtitle="HTTP flood req/min"
    :icon="Activity"
    source="fortiweb"
    disable-drill
  >
    <template #glance>
      <div class="mb-2 flex items-center justify-between gap-2">
        <div class="flex gap-1">
          <button
            v-for="w in windows"
            :key="w"
            type="button"
            class="rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors"
            :class="selectedWindow === w
              ? 'bg-theme-primary/20 text-theme-primary'
              : 'text-theme-text-muted hover:text-theme-text'"
            @click.stop="selectedWindow = w"
          >
            {{ w }}
          </button>
        </div>
        <span class="text-[10px] text-theme-text-muted">{{ source }}</span>
      </div>

      <div v-if="visibleBuckets.length === 0">
        <WidgetEmptyState message="No DoS events in window." />
      </div>
      <div v-else class="flex min-h-0 flex-1 items-end gap-px overflow-hidden">
        <div
          v-for="bucket in visibleBuckets"
          :key="bucket.ts"
          class="group relative flex min-w-0 flex-1 flex-col items-center justify-end"
          :title="`${formatTs(bucket.ts)}\nBlocked: ${bucket.blocked}\nAllowed: ${bucket.allowed}`"
        >
          <div class="w-full rounded-t-sm bg-red-500/70" :style="{ height: barHeightPct(bucket.blocked) }" />
          <div
            v-if="bucket.allowed > 0"
            class="w-full bg-theme-text/20"
            :style="{ height: barHeightPct(bucket.allowed) }"
          />
        </div>
      </div>

      <div class="mt-2 flex justify-between text-[10px] text-theme-text-muted">
        <span class="flex items-center gap-1">
          <span class="h-2 w-2 rounded-sm bg-red-500/70" /> Blocked {{ totalBlocked }}
        </span>
        <span class="flex items-center gap-1">
          <span class="h-2 w-2 rounded-sm bg-theme-text/20" /> Allowed {{ totalAllowed }}
        </span>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-3">
        <div class="text-xs font-semibold uppercase tracking-wide text-theme-text-muted">
          Minute-by-minute breakdown
        </div>
        <div v-if="visibleBuckets.length === 0" class="text-xs text-theme-text-muted">No data.</div>
        <div v-else class="max-h-64 overflow-y-auto no-scrollbar">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-[10px] uppercase tracking-wide text-theme-text-muted">
                <th class="py-1 text-left">Time</th>
                <th class="py-1 text-right">Blocked</th>
                <th class="py-1 text-right">Allowed</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="b in visibleBuckets"
                :key="b.ts"
                class="border-t border-theme-border/30"
              >
                <td class="py-0.5 font-mono text-theme-text-muted">{{ formatTs(b.ts) }}</td>
                <td class="py-0.5 text-right font-semibold text-red-400">{{ b.blocked }}</td>
                <td class="py-0.5 text-right text-theme-text-muted">{{ b.allowed }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
