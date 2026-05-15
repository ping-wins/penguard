<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircle2, History, Loader2 } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import WidgetSlaBadge from '../shell/WidgetSlaBadge.vue'
import { approvePlaybookRun, type PlaybookRun } from '../../../services/playbooksClient'
import { ageMs, formatAge } from '../../../composables/useSocMetrics'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const { t } = useI18n()
const approvedOverrides = ref<Record<string, PlaybookRun>>({})
const approving = ref<Record<string, boolean>>({})
const error = ref('')

const runs = computed<PlaybookRun[]>(() => {
  const source = Array.isArray(props.data?.runs) ? props.data.runs : []
  return source.map((run: PlaybookRun) => approvedOverrides.value[run.id] ?? run)
})

const summary = computed(() => {
  const next = {
    active: 0,
    completed: 0,
    failed: 0,
    running: 0,
    waitingApproval: 0,
  }
  for (const run of runs.value) {
    const status = String(run.status ?? '').toLowerCase()
    if (status === 'completed' || status === 'succeeded') next.completed += 1
    else if (status === 'failed' || status === 'error') next.failed += 1
    else next.active += 1
    if (status === 'running') next.running += 1
    if (status === 'waiting_approval' || status === 'pending_approval') next.waitingApproval += 1
  }
  return next
})

const selectedId = ref<string | null>(null)
const selectedRun = computed(() => runs.value.find((run) => run.id === selectedId.value) ?? null)
const oldestAgeMs = computed(() => {
  const ages = runs.value
    .map((run) => ageMs(run.startedAt ?? run.createdAt ?? null))
    .filter((value): value is number => value !== null)
  return ages.length ? Math.max(...ages) : null
})

function statusTone(status: unknown) {
  const s = String(status ?? '').toLowerCase()
  if (s === 'completed' || s === 'succeeded') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
  if (s === 'waiting_approval' || s === 'pending_approval') return 'border-amber-500/30 bg-amber-500/10 text-amber-100'
  if (s === 'failed' || s === 'error') return 'border-red-500/30 bg-red-500/10 text-red-100'
  return 'border-theme-border bg-theme-bg/70 text-theme-text-muted'
}

function canApprove(run: PlaybookRun) {
  return ['waiting_approval', 'pending_approval'].includes(String(run.status ?? '').toLowerCase())
}

async function approveRun(run: PlaybookRun) {
  error.value = ''
  approving.value = { ...approving.value, [run.id]: true }
  try {
    const approved = await approvePlaybookRun(run.id)
    approvedOverrides.value = { ...approvedOverrides.value, [approved.id]: approved }
  } catch (e: any) {
    error.value = e?.message ?? t('widgets.playbookRunHistory.approveError')
  } finally {
    approving.value = { ...approving.value, [run.id]: false }
  }
}

function selectRun(id: string) {
  selectedId.value = selectedId.value === id ? null : id
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    :title="t('widgets.playbookRunHistory.title')"
    :subtitle="t('widgets.playbookRunHistory.subtitle')"
    :icon="History"
    source="soar_skipper"
  >
    <template #glance>
      <div class="grid grid-cols-3 gap-2">
        <WidgetKpiTile :label="t('widgets.playbookRunHistory.total')" :value="runs.length" />
        <WidgetKpiTile :label="t('widgets.playbookRunHistory.completed')" :value="summary.completed" tone="healthy" />
        <WidgetKpiTile :label="t('widgets.playbookRunHistory.waiting')" :value="summary.waitingApproval" :tone="summary.waitingApproval > 0 ? 'warning' : 'default'" />
      </div>

      <div v-if="error" class="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">
        {{ error }}
      </div>

      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar">
        <button
          v-for="run in runs.slice(0, 8)"
          :key="run.id"
          type="button"
          class="rounded border border-theme-border/40 bg-theme-text/5 p-2 text-left text-xs transition-colors hover:border-theme-primary/40"
          :class="selectedId === run.id ? 'border-theme-primary/60 bg-theme-primary/10' : ''"
          @click.stop="selectRun(run.id)"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-mono font-semibold text-theme-text">{{ run.id }}</div>
              <div class="mt-0.5 grid grid-cols-2 gap-x-2 text-[10px] text-theme-text-muted">
                <span class="truncate">{{ run.playbookId || '--' }}</span>
                <span class="truncate">{{ run.incidentId || '--' }}</span>
              </div>
            </div>
            <span class="shrink-0 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide" :class="statusTone(run.status)">
              {{ run.status }}
            </span>
          </div>
          <div class="mt-2 flex items-center justify-between gap-2">
            <WidgetSlaBadge :created-at="run.startedAt ?? run.createdAt" />
            <button
              v-if="canApprove(run)"
              type="button"
              :data-test="`playbook-run-history-approve-${run.id}`"
              class="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-100 hover:bg-amber-500/20 disabled:opacity-50"
              :disabled="approving[run.id]"
              @click.stop="approveRun(run)"
            >
              <Loader2 v-if="approving[run.id]" :size="10" class="animate-spin" />
              <CheckCircle2 v-else :size="10" />
              {{ t('widgets.playbookRunHistory.approve') }}
            </button>
          </div>
        </button>
        <div v-if="runs.length === 0" class="flex flex-1 items-center justify-center text-xs italic text-theme-text-muted">
          {{ t('widgets.playbookRunHistory.empty') }}
        </div>
      </div>
    </template>

    <template #drill>
      <div v-if="!selectedRun" class="text-xs text-theme-text-muted">
        {{ t('widgets.playbookRunHistory.selectRun') }}
      </div>
      <div v-else class="space-y-2 text-xs">
        <div class="grid grid-cols-2 gap-1 rounded border border-theme-border bg-theme-bg/50 p-2">
          <span class="text-theme-text-muted">{{ t('widgets.playbookRunHistory.runId') }}</span>
          <span class="font-mono text-theme-text">{{ selectedRun.id }}</span>
          <span class="text-theme-text-muted">{{ t('widgets.playbookRunHistory.playbookId') }}</span>
          <span class="font-mono text-theme-text">{{ selectedRun.playbookId || '--' }}</span>
          <span class="text-theme-text-muted">{{ t('widgets.playbookRunHistory.incidentId') }}</span>
          <span class="font-mono text-theme-text">{{ selectedRun.incidentId || '--' }}</span>
        </div>
        <div v-if="Array.isArray(selectedRun.steps)" class="max-h-40 overflow-y-auto rounded border border-theme-border/50 bg-theme-bg/50 p-2">
          <div
            v-for="(step, index) in selectedRun.steps"
            :key="`${selectedRun.id}-${step.nodeId ?? index}`"
            class="flex items-center justify-between gap-2 border-b border-theme-border/30 py-1 last:border-0"
          >
            <span class="truncate font-mono text-theme-text">{{ step.nodeType || step.nodeId || index + 1 }}</span>
            <span class="shrink-0 text-[10px] text-theme-text-muted">{{ step.status }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <section class="grid grid-cols-4 gap-2">
        <WidgetKpiTile :label="t('widgets.playbookRunHistory.active')" :value="summary.active" />
        <WidgetKpiTile :label="t('widgets.playbookRunHistory.completed')" :value="summary.completed" tone="healthy" />
        <WidgetKpiTile :label="t('widgets.playbookRunHistory.failed')" :value="summary.failed" :tone="summary.failed > 0 ? 'critical' : 'default'" />
        <WidgetKpiTile :label="t('widgets.playbookRunHistory.oldest')" :value="oldestAgeMs !== null ? formatAge(oldestAgeMs) : '--'" />
      </section>
      <table class="mt-4 w-full text-xs">
        <thead class="text-[10px] uppercase tracking-wide text-theme-text-muted">
          <tr>
            <th class="text-left font-semibold">{{ t('widgets.playbookRunHistory.runId') }}</th>
            <th class="text-left font-semibold">{{ t('widgets.playbookRunHistory.playbookId') }}</th>
            <th class="text-left font-semibold">{{ t('widgets.playbookRunHistory.incidentId') }}</th>
            <th class="text-left font-semibold">{{ t('widgets.playbookRunHistory.status') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in runs" :key="run.id" class="border-t border-theme-border/40">
            <td class="py-1 pr-2 font-mono text-theme-text">{{ run.id }}</td>
            <td class="py-1 pr-2 text-theme-text-muted">{{ run.playbookId || '--' }}</td>
            <td class="py-1 pr-2 text-theme-text-muted">{{ run.incidentId || '--' }}</td>
            <td class="py-1 pr-2">{{ run.status }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </WidgetShell>
</template>
