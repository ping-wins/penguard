<script setup lang="ts">
import { computed } from 'vue'
import { ShieldAlert } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

type IpRow = { ip: string; count: number; lastSeen: string; blocked: boolean }

const rows = computed<IpRow[]>(() =>
  Array.isArray(props.data?.rows) ? props.data.rows : []
)

const maxCount = computed(() => rows.value.reduce((m, r) => Math.max(m, r.count), 0))
const source = computed(() => props.data?.source ?? 'siem')

function barWidthPct(count: number): string {
  const n = Number(count)
  if (maxCount.value === 0 || isNaN(n)) return '0%'
  return `${Math.max(4, (n / maxCount.value) * 100)}%`
}

function formatTs(ts: string): string {
  if (!ts) return '—'
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
    title="WAF Top Attacking IPs"
    subtitle="Highest request count"
    :icon="ShieldAlert"
    source="fortiweb"
    disable-drill
  >
    <template #glance>
      <div class="mb-1 flex justify-end text-[10px] text-theme-text-muted">{{ source }}</div>
      <div v-if="rows.length === 0">
        <WidgetEmptyState message="No attacking IPs detected." />
      </div>
      <div v-else class="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto no-scrollbar">
        <div
          v-for="row in rows.slice(0, 8)"
          :key="row.ip"
          class="flex flex-col gap-0.5"
        >
          <div class="flex items-center justify-between gap-2 text-xs">
            <span
              class="font-mono truncate"
              :class="row.blocked ? 'text-red-400' : 'text-theme-text'"
            >{{ row.ip }}</span>
            <span class="shrink-0 tabular-nums text-theme-text-muted">{{ row.count }}</span>
          </div>
          <div class="h-1.5 overflow-hidden rounded-sm bg-theme-text/5">
            <div
              class="h-full rounded-sm"
              :class="row.blocked ? 'bg-red-500/60' : 'bg-amber-400/60'"
              :style="{ width: barWidthPct(row.count) }"
            />
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-3">
        <div class="text-xs font-semibold uppercase tracking-wide text-theme-text-muted">All IPs</div>
        <div v-if="rows.length === 0" class="text-xs text-theme-text-muted">No data.</div>
        <div v-else class="max-h-64 overflow-y-auto no-scrollbar">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-[10px] uppercase tracking-wide text-theme-text-muted">
                <th class="py-1 text-left">IP</th>
                <th class="py-1 text-right">Requests</th>
                <th class="py-1 text-right">Last Seen</th>
                <th class="py-1 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in rows"
                :key="row.ip"
                class="border-t border-theme-border/30"
              >
                <td class="py-0.5 font-mono" :class="row.blocked ? 'text-red-400' : 'text-theme-text'">{{ row.ip }}</td>
                <td class="py-0.5 text-right tabular-nums">{{ row.count }}</td>
                <td class="py-0.5 text-right text-theme-text-muted">{{ formatTs(row.lastSeen) }}</td>
                <td class="py-0.5 text-right">
                  <span
                    class="rounded px-1 py-0.5 text-[10px] font-medium"
                    :class="row.blocked
                      ? 'bg-red-500/20 text-red-300'
                      : 'bg-amber-500/20 text-amber-300'"
                  >
                    {{ row.blocked ? 'Blocked' : 'Allowed' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
