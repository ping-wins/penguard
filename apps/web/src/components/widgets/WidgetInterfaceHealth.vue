<script setup lang="ts">
import { computed } from 'vue'
import { Network } from 'lucide-vue-next'

const props = defineProps<{ data: any }>()

const interfaces = computed(() => Array.isArray(props.data?.interfaces) ? props.data.interfaces : [])
const summary = computed(() => {
  const fallbackUp = interfaces.value.filter((iface: any) => iface?.status === 'up').length
  const fallbackTotal = interfaces.value.length
  return {
    total: Number(props.data?.summary?.total ?? fallbackTotal),
    up: Number(props.data?.summary?.up ?? fallbackUp),
    down: Number(props.data?.summary?.down ?? Math.max(0, fallbackTotal - fallbackUp)),
    totalRxBytes: Number(props.data?.summary?.totalRxBytes ?? 0),
    totalTxBytes: Number(props.data?.summary?.totalTxBytes ?? 0),
  }
})

function interfaceKey(iface: any, index: string | number) {
  return String(iface?.id || iface?.name || index)
}

function statusClass(status: string | undefined) {
  return String(status || '').toLowerCase() === 'up' ? 'bg-emerald-400' : 'bg-red-400'
}

function statusTextClass(status: string | undefined) {
  return String(status || '').toLowerCase() === 'up' ? 'text-emerald-300' : 'text-red-300'
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 MB'
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3 text-theme-text">
        <Network :size="24" class="shrink-0 text-emerald-400" />
        <div class="min-w-0">
          <span class="text-xl font-bold">Interface Health</span>
          <div class="text-xs text-theme-text-muted truncate">Operational link state and traffic totals</div>
        </div>
      </div>
      <div class="shrink-0 text-right text-xs text-theme-text-muted">
        <div><span class="font-bold text-emerald-300">{{ summary.up }}</span> up</div>
        <div><span class="font-bold text-red-300">{{ summary.down }}</span> down</div>
      </div>
    </div>

    <div class="grid grid-cols-3 gap-2 text-xs">
      <div class="rounded-md bg-theme-text/5 p-2">
        <div class="text-theme-text-muted">Total</div>
        <div class="text-lg font-bold text-theme-text">{{ summary.total }}</div>
      </div>
      <div class="rounded-md bg-theme-text/5 p-2">
        <div class="text-theme-text-muted">RX</div>
        <div class="font-semibold text-theme-text">{{ formatBytes(summary.totalRxBytes) }}</div>
      </div>
      <div class="rounded-md bg-theme-text/5 p-2">
        <div class="text-theme-text-muted">TX</div>
        <div class="font-semibold text-theme-text">{{ formatBytes(summary.totalTxBytes) }}</div>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto rounded-md bg-theme-text/5 p-2 no-scrollbar">
      <div
        v-for="(iface, index) in interfaces"
        :key="interfaceKey(iface, index)"
        class="border-b border-theme-border/50 py-2 last:border-0"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="h-2 w-2 rounded-full" :class="statusClass(iface.status)" />
              <span class="truncate font-semibold text-theme-text">{{ iface.name || iface.id || 'interface' }}</span>
              <span v-if="iface.alias" class="rounded bg-theme-bg px-1.5 py-0.5 text-[10px] uppercase text-theme-text-muted">
                {{ iface.alias }}
              </span>
            </div>
            <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-theme-text-muted">
              <span v-if="iface.ip" class="font-mono">{{ iface.ip }}</span>
              <span v-if="iface.role">{{ iface.role }}</span>
              <span>{{ formatBytes(Number(iface.rxBytes ?? 0)) }} rx</span>
              <span>{{ formatBytes(Number(iface.txBytes ?? 0)) }} tx</span>
            </div>
          </div>
          <span class="shrink-0 text-xs font-bold uppercase" :class="statusTextClass(iface.status)">
            {{ iface.status || 'unknown' }}
          </span>
        </div>
      </div>

      <div v-if="interfaces.length === 0" class="flex h-full min-h-28 items-center justify-center text-center text-xs italic text-theme-text-muted">
        No interfaces returned.
      </div>
    </div>
  </div>
</template>
