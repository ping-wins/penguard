<script setup lang="ts">
import { computed, ref } from 'vue'
import { Globe } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import WidgetEntityChip from '../shell/WidgetEntityChip.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

type IpRow = {
  ip: string
  totalCount: number
  deniedCount: number
  acceptedCount: number
  highSeverityCount: number
  destinations: Set<string>
  lastSeen: string | null
}

const events = computed<any[]>(() => Array.isArray(props.data?.events) ? props.data.events : [])

const rows = computed<IpRow[]>(() => {
  const map = new Map<string, IpRow>()
  for (const event of events.value) {
    if (!event || typeof event !== 'object') continue
    const ip = String(event.sourceIp || event.srcIp || '').trim()
    if (!ip) continue
    let row = map.get(ip)
    if (!row) {
      row = {
        ip,
        totalCount: 0,
        deniedCount: 0,
        acceptedCount: 0,
        highSeverityCount: 0,
        destinations: new Set<string>(),
        lastSeen: null,
      }
      map.set(ip, row)
    }
    const action = String(event.action || '').toLowerCase()
    row.totalCount += 1
    if (['deny', 'drop', 'block'].includes(action)) row.deniedCount += 1
    else if (['accept', 'allow'].includes(action)) row.acceptedCount += 1
    const severity = String(event.severity || '').toLowerCase()
    if (severity === 'critical' || severity === 'high') row.highSeverityCount += 1
    const dest = event.destinationIp || event.dstIp
    if (dest) row.destinations.add(String(dest))
    if (event.timestamp && (!row.lastSeen || event.timestamp > row.lastSeen)) row.lastSeen = String(event.timestamp)
  }
  return Array.from(map.values()).sort((a, b) => b.deniedCount - a.deniedCount || b.totalCount - a.totalCount)
})

const totals = computed(() => {
  let denied = 0
  let high = 0
  for (const row of rows.value) {
    denied += row.deniedCount
    high += row.highSeverityCount
  }
  return { denied, high, unique: rows.value.length }
})

const selectedIp = ref<string | null>(null)
function selectIp(ip: string | null) {
  selectedIp.value = selectedIp.value === ip ? null : ip
}

const selectedRow = computed(() => rows.value.find((r) => r.ip === selectedIp.value) ?? null)
const selectedEvents = computed(() => selectedIp.value ? events.value.filter((e: any) => String(e?.sourceIp || e?.srcIp || '') === selectedIp.value) : [])
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="Top Source IPs"
    subtitle="Derived from FortiGate recent events"
    :icon="Globe"
    source="fortigate"
  >
    <template #glance>
      <div class="grid grid-cols-3 gap-2">
        <WidgetKpiTile label="Unique IPs" :value="totals.unique" />
        <WidgetKpiTile label="Denied" :value="totals.denied" :tone="totals.denied > 0 ? 'critical' : 'default'" />
        <WidgetKpiTile label="High sev" :value="totals.high" :tone="totals.high > 0 ? 'warning' : 'default'" />
      </div>
      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar">
        <button
          v-for="row in rows.slice(0, 8)"
          :key="row.ip"
          type="button"
          class="flex items-center justify-between gap-2 rounded border border-theme-border/40 bg-theme-text/5 px-2 py-1.5 text-xs transition-colors hover:border-theme-primary/40"
          :class="selectedIp === row.ip ? 'border-theme-primary/60 bg-theme-primary/10' : ''"
          @click.stop="selectIp(row.ip)"
        >
          <span class="flex min-w-0 items-center gap-1.5">
            <Globe :size="12" class="text-theme-text-muted" />
            <span class="truncate font-mono text-theme-text">{{ row.ip }}</span>
          </span>
          <span class="flex shrink-0 items-center gap-2 text-[10px] tabular-nums">
            <span v-if="row.deniedCount > 0" class="text-red-300">{{ row.deniedCount }} deny</span>
            <span v-if="row.highSeverityCount > 0" class="text-amber-300">{{ row.highSeverityCount }} high</span>
            <span class="text-theme-text-muted">{{ row.totalCount }} total</span>
          </span>
        </button>
        <WidgetEmptyState
          v-if="rows.length === 0"
          title="No source IPs"
          hint="FortiGate recent events feed has no source IP attribution yet."
        />
      </div>
    </template>

    <template #drill>
      <div v-if="!selectedRow" class="text-xs text-theme-text-muted">
        Click an IP to inspect its event activity.
      </div>
      <div v-else class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <span class="truncate font-mono text-xs font-semibold text-theme-text">{{ selectedRow.ip }}</span>
          <span class="shrink-0 text-[10px] uppercase tracking-wide text-theme-text-muted">
            {{ selectedRow.deniedCount }} deny · {{ selectedRow.acceptedCount }} accept
          </span>
        </div>
        <div v-if="selectedRow.destinations.size" class="flex flex-wrap gap-1.5">
          <WidgetEntityChip
            v-for="dest in Array.from(selectedRow.destinations).slice(0, 6)"
            :key="dest"
            field="destinationIp"
            :value="dest"
          />
        </div>
        <div class="max-h-40 overflow-y-auto rounded border border-theme-border/40 bg-theme-bg/40 p-2 text-[11px]">
          <div
            v-for="(event, idx) in selectedEvents.slice(0, 12)"
            :key="idx"
            class="flex items-center justify-between gap-2 border-b border-theme-border/30 py-0.5 last:border-0"
          >
            <span class="truncate text-theme-text">{{ event.message || event.type || 'event' }}</span>
            <span class="shrink-0 text-theme-text-muted">{{ event.action || event.severity || '--' }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section class="grid grid-cols-3 gap-2">
          <WidgetKpiTile label="Unique IPs" :value="totals.unique" />
          <WidgetKpiTile label="Denied" :value="totals.denied" :tone="totals.denied > 0 ? 'critical' : 'default'" />
          <WidgetKpiTile label="High sev" :value="totals.high" :tone="totals.high > 0 ? 'warning' : 'default'" />
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">All source IPs</h3>
          <table class="w-full text-xs">
            <thead class="text-[10px] uppercase tracking-wide text-theme-text-muted">
              <tr>
                <th class="text-left font-semibold">Source IP</th>
                <th class="text-right font-semibold">Denied</th>
                <th class="text-right font-semibold">High sev</th>
                <th class="text-right font-semibold">Destinations</th>
                <th class="text-right font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.ip" class="border-t border-theme-border/40">
                <td class="py-1 pr-2 font-mono text-theme-text">{{ row.ip }}</td>
                <td class="py-1 pr-2 text-right tabular-nums" :class="row.deniedCount > 0 ? 'text-red-300' : 'text-theme-text-muted'">{{ row.deniedCount }}</td>
                <td class="py-1 pr-2 text-right tabular-nums" :class="row.highSeverityCount > 0 ? 'text-amber-300' : 'text-theme-text-muted'">{{ row.highSeverityCount }}</td>
                <td class="py-1 pr-2 text-right tabular-nums text-theme-text-muted">{{ row.destinations.size }}</td>
                <td class="py-1 text-right tabular-nums">{{ row.totalCount }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
