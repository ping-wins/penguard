<script setup lang="ts">
import { computed, ref } from 'vue'
import { PlayCircle } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import WidgetSlaBadge from '../shell/WidgetSlaBadge.vue'
import { useWidgetSeries } from '../../../composables/useWidgetSeries'
import { ageMs, formatAge } from '../../../composables/useSocMetrics'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const runs = computed<any[]>(() => Array.isArray(props.data?.runs) ? props.data.runs : [])
const count = computed(() => Number(props.data?.count) || runs.value.length)

const runningCount = computed(() => runs.value.filter((r: any) => String(r?.status).toLowerCase() === 'running').length)
const waitingCount = computed(() => runs.value.filter((r: any) => ['waiting_approval', 'pending_approval'].includes(String(r?.status).toLowerCase())).length)
const oldestAgeMs = computed(() => {
  const ages = runs.value.map((r: any) => ageMs(r?.startedAt ?? r?.createdAt)).filter((v): v is number => v !== null)
  return ages.length > 0 ? Math.max(...ages) : null
})

const runningSeries = useWidgetSeries(props.instanceId, 'running')
const waitingSeries = useWidgetSeries(props.instanceId, 'waitingApproval')

const selectedId = ref<string | null>(null)
function selectRun(id: string | null) {
  selectedId.value = selectedId.value === id ? null : id
}

const selectedRun = computed(() => runs.value.find((r: any) => r?.id === selectedId.value) ?? null)

function statusTone(status: unknown): 'default' | 'critical' | 'warning' | 'healthy' {
  const s = String(status ?? '').toLowerCase()
  if (s === 'failed' || s === 'error') return 'critical'
  if (s === 'waiting_approval' || s === 'pending_approval') return 'warning'
  if (s === 'completed' || s === 'succeeded') return 'healthy'
  return 'default'
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="Active Playbook Runs"
    subtitle="SOAR run queue"
    :icon="PlayCircle"
    source="soar_skipper"
  >
    <template #glance>
      <div class="grid grid-cols-3 gap-2">
        <WidgetKpiTile label="Active" :value="count" />
        <WidgetKpiTile label="Running" :value="runningCount" :series="runningSeries.points.value" />
        <WidgetKpiTile label="Waiting approval" :value="waitingCount" :series="waitingSeries.points.value" :tone="waitingCount > 0 ? 'warning' : 'default'" />
      </div>
      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar">
        <button
          v-for="run in runs.slice(0, 8)"
          :key="run.id"
          type="button"
          class="flex flex-col gap-1 rounded border border-theme-border/40 bg-theme-text/5 p-2 text-left text-xs transition-colors hover:border-theme-primary/40"
          :class="selectedId === run.id ? 'border-theme-primary/60 bg-theme-primary/10' : ''"
          @click.stop="selectRun(run.id)"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="truncate font-semibold text-theme-text">{{ run.name || run.playbookId || run.id }}</span>
            <span class="shrink-0 text-[10px] uppercase tracking-wide" :class="{
              'text-emerald-300': statusTone(run.status) === 'healthy',
              'text-amber-300': statusTone(run.status) === 'warning',
              'text-red-300': statusTone(run.status) === 'critical',
              'text-theme-text-muted': statusTone(run.status) === 'default',
            }">{{ run.status }}</span>
          </div>
          <div class="flex items-center justify-between gap-2 text-[10px] text-theme-text-muted">
            <span class="truncate">Step {{ run.currentStep ?? '--' }}</span>
            <WidgetSlaBadge :created-at="run.startedAt ?? run.createdAt" />
          </div>
        </button>
        <div v-if="runs.length === 0" class="flex flex-1 items-center justify-center text-xs italic text-theme-text-muted">
          No active runs.
        </div>
      </div>
    </template>

    <template #drill>
      <div v-if="!selectedRun" class="text-xs text-theme-text-muted">
        Select a run to see its steps.
      </div>
      <div v-else class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-xs font-semibold text-theme-text">{{ selectedRun.name || selectedRun.playbookId }}</span>
          <span class="text-[10px] uppercase tracking-wide text-theme-text-muted">{{ selectedRun.status }}</span>
        </div>
        <div v-if="Array.isArray(selectedRun.steps)" class="max-h-40 overflow-y-auto rounded border border-theme-border/50 bg-theme-bg/50 p-2 text-[11px]">
          <div
            v-for="(step, idx) in selectedRun.steps"
            :key="step.id ?? idx"
            class="flex items-center gap-2 border-b border-theme-border/30 py-1 last:border-0"
          >
            <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="{
              'bg-emerald-400': String(step.status).toLowerCase() === 'completed',
              'bg-amber-400': ['running', 'waiting_approval'].includes(String(step.status).toLowerCase()),
              'bg-red-400': String(step.status).toLowerCase() === 'failed',
              'bg-theme-text-muted': !['completed','running','waiting_approval','failed'].includes(String(step.status).toLowerCase()),
            }" />
            <span class="truncate text-theme-text">{{ step.name || step.id }}</span>
            <span class="ml-auto shrink-0 text-[10px] text-theme-text-muted">{{ step.status }}</span>
          </div>
        </div>
        <div v-else class="text-xs text-theme-text-muted">No step detail available on this run.</div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section class="grid grid-cols-3 gap-2">
          <WidgetKpiTile label="Active" :value="count" />
          <WidgetKpiTile label="Waiting approval" :value="waitingCount" :tone="waitingCount > 0 ? 'warning' : 'default'" />
          <WidgetKpiTile label="Oldest age" :value="oldestAgeMs !== null ? formatAge(oldestAgeMs) : '--'" />
        </section>
        <section>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">Runs</h3>
          <table class="w-full text-xs">
            <thead class="text-[10px] uppercase tracking-wide text-theme-text-muted">
              <tr>
                <th class="text-left font-semibold">Run</th>
                <th class="text-left font-semibold">Playbook</th>
                <th class="text-left font-semibold">Status</th>
                <th class="text-right font-semibold">Age</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.id" class="border-t border-theme-border/40">
                <td class="py-1 pr-2 font-mono text-theme-text">{{ run.id }}</td>
                <td class="py-1 pr-2 text-theme-text-muted">{{ run.playbookId || run.name || '--' }}</td>
                <td class="py-1 pr-2 capitalize">{{ run.status }}</td>
                <td class="py-1 text-right tabular-nums text-theme-text-muted">{{ formatAge(ageMs(run.startedAt ?? run.createdAt)) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
