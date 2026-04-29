<script setup lang="ts">
import { computed } from 'vue'
import { ShieldAlert } from 'lucide-vue-next'

const props = defineProps<{ data: any }>()

const signals = computed(() => Array.isArray(props.data?.signals) ? props.data.signals : [])
const summary = computed(() => ({
  critical: Number(props.data?.summary?.critical ?? 0),
  warning: Number(props.data?.summary?.warning ?? 0),
  healthy: Number(props.data?.summary?.healthy ?? 0),
}))
const score = computed(() => {
  const value = Number(props.data?.score)
  return Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value))) : null
})
const scoreDisplay = computed(() => score.value ?? 'N/A')
const scorePercent = computed(() => score.value ?? 0)
const level = computed(() => String(props.data?.level || 'unknown').toLowerCase())
const levelLabel = computed(() => level.value.replace(/^\w/, (letter) => letter.toUpperCase()))

function severityClass(severity: string | undefined) {
  switch (String(severity || '').toLowerCase()) {
    case 'critical':
      return 'border-red-400/40 bg-red-950/30 text-red-200'
    case 'warning':
      return 'border-amber-400/40 bg-amber-950/30 text-amber-100'
    case 'healthy':
      return 'border-emerald-400/35 bg-emerald-950/25 text-emerald-100'
    default:
      return 'border-theme-border bg-theme-text/5 text-theme-text'
  }
}

function severityDotClass(severity: string | undefined) {
  switch (String(severity || '').toLowerCase()) {
    case 'critical':
      return 'bg-red-400'
    case 'warning':
      return 'bg-amber-400'
    case 'healthy':
      return 'bg-emerald-400'
    default:
      return 'bg-theme-text-muted'
  }
}

function levelClass() {
  switch (level.value) {
    case 'high':
      return 'bg-red-500/15 text-red-300 border-red-400/30'
    case 'medium':
      return 'bg-amber-500/15 text-amber-200 border-amber-400/30'
    case 'low':
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
    default:
      return 'bg-theme-text/10 text-theme-text-muted border-theme-border'
  }
}

function formatSignalValue(signal: any) {
  if (signal?.value === null || signal?.value === undefined || signal?.value === '') return 'No value'
  if (signal?.unit === 'percent') return `${signal.value}%`
  return signal?.unit ? `${signal.value} ${signal.unit}` : String(signal.value)
}
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-start justify-between gap-3">
      <div class="flex items-center gap-3 text-theme-text min-w-0">
        <ShieldAlert :size="24" class="text-amber-400 shrink-0" />
        <div class="min-w-0">
          <span class="text-xl font-bold">Risk Posture</span>
          <div class="text-xs text-theme-text-muted truncate">Derived SOC signals from FortiGate telemetry</div>
        </div>
      </div>
      <span class="shrink-0 rounded-md border px-2 py-1 text-xs font-semibold uppercase" :class="levelClass()">
        {{ levelLabel }}
      </span>
    </div>

    <div class="grid grid-cols-[auto_1fr] gap-4 rounded-md bg-theme-text/5 p-3">
      <div class="text-5xl font-bold leading-none text-theme-text">{{ scoreDisplay }}</div>
      <div class="flex min-w-0 flex-col justify-center gap-2">
        <div class="flex items-center justify-between text-xs text-theme-text-muted">
          <span>Risk score</span>
          <span>{{ scorePercent }} / 100</span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-theme-bg">
          <div
            class="h-full rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-400"
            :style="{ width: `${scorePercent}%` }"
          />
        </div>
      </div>
    </div>

    <div class="grid grid-cols-3 gap-2 text-center text-xs">
      <div class="rounded-md bg-red-500/10 p-2 text-red-200">
        <div class="font-bold text-theme-text">{{ summary.critical }}</div>
        <div>Critical</div>
      </div>
      <div class="rounded-md bg-amber-500/10 p-2 text-amber-100">
        <div class="font-bold text-theme-text">{{ summary.warning }}</div>
        <div>Warning</div>
      </div>
      <div class="rounded-md bg-emerald-500/10 p-2 text-emerald-100">
        <div class="font-bold text-theme-text">{{ summary.healthy }}</div>
        <div>Healthy</div>
      </div>
    </div>

    <div class="flex-1 space-y-2 overflow-y-auto pr-1 no-scrollbar">
      <div
        v-for="signal in signals"
        :key="signal.id || signal.label"
        class="rounded-md border p-2 text-sm"
        :class="severityClass(signal.severity)"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2 font-semibold text-theme-text">
              <span class="h-2 w-2 rounded-full" :class="severityDotClass(signal.severity)" />
              <span class="truncate">{{ signal.label || 'Risk signal' }}</span>
            </div>
            <div v-if="signal.description" class="mt-1 text-xs text-theme-text-muted">
              {{ signal.description }}
            </div>
          </div>
          <span class="shrink-0 rounded bg-theme-bg/70 px-2 py-1 text-xs font-semibold text-theme-text">
            {{ formatSignalValue(signal) }}
          </span>
        </div>
      </div>

      <div v-if="signals.length === 0" class="flex h-full min-h-24 items-center justify-center text-center text-xs italic text-theme-text-muted">
        No risk signals returned.
      </div>
    </div>
  </div>
</template>
