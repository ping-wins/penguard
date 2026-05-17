<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, CheckCircle2, Clock, History, Loader2, Play, RefreshCcw, ShieldAlert, Workflow } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { usePlaybooksStore } from '../../stores/usePlaybooksStore'
import type { Playbook, PlaybookRun } from '../../services/playbooksClient'

const { t } = useI18n()
const store = usePlaybooksStore()
const selectedId = ref<string | null>(null)
const incidentId = ref('')

const selected = computed(() => store.playbooks.find((playbook) => playbook.id === selectedId.value) ?? store.playbooks[0] ?? null)
const selectedRunId = computed(() => selected.value ? store.latestRunByPlaybook[selected.value.id] : null)
const selectedRun = computed(() => selectedRunId.value ? store.runs[selectedRunId.value] : null)
const visibleRunHistory = computed(() => store.runHistory.slice(0, 8))

function select(playbook: Playbook) {
  selectedId.value = playbook.id
}

function hasApproval(playbook: Playbook): boolean {
  return playbook.nodes.some((node) => node.type === 'approval.required')
}

function hasSensitiveSteps(playbook: Playbook): boolean {
  return playbook.nodes.some((node) => node.sensitive || node.type.includes('fortigate') || node.type === 'approval.required')
}

function edgeLabel(edge: { from: string, to: string }): string {
  return `${edge.from} → ${edge.to}`
}

function nodeDefinition(type: string) {
  return store.nodeTypeById[type]
}

function nodeLabel(type: string): string {
  return nodeDefinition(type)?.label ?? type
}

function nodeBoundary(type: string): string | null {
  return nodeDefinition(type)?.boundary ?? null
}

function nodeExecutionLabel(type: string): string {
  const definition = nodeDefinition(type)
  if (!definition) return t('playbooks.dryRunOnly')
  return definition.liveAvailable ? t('playbooks.liveCapable') : t('playbooks.dryRunOnly')
}

function boundaryLabel(boundary?: string | null): string {
  if (!boundary) return t('playbooks.boundaries.unknown')
  return t(`playbooks.boundaries.${boundary}`)
}

function stepSafetyClass(type: string, sensitive?: boolean) {
  if (sensitive || nodeDefinition(type)?.sensitive) return 'border-red-500/30 bg-red-500/10 text-red-100'
  if (nodeDefinition(type)?.boundary?.includes('dry_run')) return 'border-sky-500/30 bg-sky-500/10 text-sky-100'
  return 'border-theme-border bg-theme-bg/70 text-theme-text-muted'
}

function runStatusClass(status: unknown) {
  const s = String(status ?? '').toLowerCase()
  if (s === 'completed' || s === 'succeeded') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
  if (s === 'waiting_approval' || s === 'pending_approval') return 'border-amber-500/30 bg-amber-500/10 text-amber-100'
  if (s === 'failed' || s === 'error') return 'border-red-500/30 bg-red-500/10 text-red-100'
  return 'border-theme-border bg-theme-bg/70 text-theme-text-muted'
}

function canApproveRun(run: PlaybookRun) {
  return ['waiting_approval', 'pending_approval'].includes(String(run.status ?? '').toLowerCase())
}

async function approveHistoryRun(run: PlaybookRun) {
  await store.approve(run.id).catch(() => undefined)
}

async function simulateSelected() {
  if (!selected.value) return
  await store.simulate(selected.value.id).catch(() => undefined)
}

async function runSelected() {
  if (!selected.value || !incidentId.value.trim()) return
  await store.run(incidentId.value.trim(), selected.value.id).catch(() => undefined)
}

async function approveSelectedRun() {
  if (!selectedRun.value) return
  await store.approve(selectedRun.value.id).catch(() => undefined)
}

onMounted(() => store.refresh())
</script>

<template>
  <div class="flex h-full flex-col w-full">
    <div class="px-4 pt-4 pb-3 border-b border-theme-border flex items-center justify-between">
      <div>
        <h2 class="font-bold text-lg text-theme-text flex items-center gap-2">
          <Workflow :size="18" />
          {{ t('playbooks.title') }}
        </h2>
        <p class="text-xs text-theme-text-muted mt-1">{{ t('playbooks.subtitle') }}</p>
      </div>
      <button
        type="button"
        class="text-theme-text-muted hover:text-theme-text disabled:opacity-50"
        :disabled="store.isLoading"
        :title="t('playbooks.refreshTooltip')"
        @click="store.refresh()"
      >
        <RefreshCcw :size="16" :class="store.isLoading ? 'animate-spin' : ''" />
      </button>
    </div>

    <div v-if="store.error" class="mx-4 mt-3 rounded border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-200 flex items-start gap-2">
      <AlertCircle :size="14" class="mt-0.5" />
      {{ store.error }}
    </div>

    <section
      data-test="playbook-canvas-builder-hint"
      class="m-3 rounded-lg border border-sky-500/30 bg-sky-500/10 p-3"
    >
      <h3 class="text-sm font-semibold text-sky-100">{{ t('playbooks.canvasBuilderTitle') }}</h3>
      <p class="mt-1 text-xs leading-snug text-theme-text-muted">
        {{ t('playbooks.canvasBuilderHint') }}
      </p>
    </section>

    <section data-test="playbook-run-history" class="mx-3 mb-3 rounded-lg border border-theme-border bg-theme-panel/40 p-3">
      <div class="mb-2 flex items-center justify-between gap-2">
        <div>
          <h3 class="flex items-center gap-1.5 text-sm font-semibold text-theme-text">
            <History :size="15" />
            {{ t('playbooks.runHistoryTitle') }}
          </h3>
          <p class="mt-0.5 text-xs text-theme-text-muted">{{ t('playbooks.runHistorySubtitle') }}</p>
        </div>
        <span class="rounded border border-theme-border bg-theme-bg/70 px-2 py-0.5 text-[10px] text-theme-text-muted">
          {{ t('playbooks.runHistoryCount', { count: store.runHistory.length }) }}
        </span>
      </div>
      <div v-if="visibleRunHistory.length" class="max-h-52 space-y-1 overflow-y-auto pr-1">
        <div
          v-for="run in visibleRunHistory"
          :key="run.id"
          class="grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded border border-theme-border/60 bg-theme-bg/40 p-2 text-xs"
        >
          <div class="min-w-0">
            <div class="flex min-w-0 flex-wrap items-center gap-1.5">
              <span class="font-mono font-semibold text-theme-text">{{ run.id }}</span>
              <span class="rounded border px-1.5 py-0.5 text-[10px] uppercase" :class="runStatusClass(run.status)">
                {{ run.status }}
              </span>
            </div>
            <div class="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px] text-theme-text-muted">
              <span class="truncate"><b>{{ t('playbooks.playbookId') }}</b> {{ run.playbookId || '--' }}</span>
              <span class="truncate"><b>{{ t('playbooks.incidentId') }}</b> {{ run.incidentId || '--' }}</span>
            </div>
          </div>
          <button
            v-if="canApproveRun(run)"
            type="button"
            :data-test="`playbook-run-history-approve-${run.id}`"
            class="self-start rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] font-semibold text-amber-100 hover:bg-amber-500/20 disabled:opacity-50"
            :disabled="store.isApproving[run.id]"
            @click="approveHistoryRun(run)"
          >
            {{ store.isApproving[run.id] ? t('playbooks.approving') : t('playbooks.approve') }}
          </button>
        </div>
      </div>
      <div v-else class="rounded border border-dashed border-theme-border p-3 text-xs text-theme-text-muted">
        {{ t('playbooks.runHistoryEmpty') }}
      </div>
    </section>

    <div v-if="store.isLoading" class="px-4 py-6 text-sm text-theme-text-muted flex items-center gap-2">
      <Loader2 :size="15" class="animate-spin" />
      {{ t('playbooks.loading') }}
    </div>

    <div v-else-if="store.isEmpty" class="px-4 py-6 text-sm text-theme-text-muted">
      {{ t('playbooks.empty') }}
    </div>

    <div v-else class="grid min-h-0 flex-1 grid-cols-[minmax(0,0.95fr)_minmax(0,1.2fr)] gap-3 overflow-hidden p-3">
      <div class="overflow-y-auto space-y-2 pr-1">
        <button
          v-for="playbook in store.playbooks"
          :key="playbook.id"
          type="button"
          :data-test="`playbook-card-${playbook.id}`"
          class="w-full rounded-lg border p-3 text-left transition hover:bg-theme-bg/60"
          :class="selected?.id === playbook.id ? 'border-theme-primary/60 bg-theme-primary/10' : 'border-theme-border bg-theme-bg/30'"
          @click="select(playbook)"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-semibold text-theme-text truncate">{{ playbook.name }}</div>
              <div class="mt-1 text-xs text-theme-text-muted line-clamp-2">{{ playbook.description || playbook.id }}</div>
            </div>
            <span class="rounded border px-1.5 py-0.5 text-[10px] uppercase"
              :class="playbook.enabled ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200' : 'border-theme-border bg-theme-bg/60 text-theme-text-muted'">
              {{ playbook.enabled ? t('playbooks.enabled') : t('playbooks.disabled') }}
            </span>
          </div>
          <div class="mt-3 flex flex-wrap gap-1">
            <span class="rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[10px] text-sky-100">{{ t('playbooks.dryRunOnly') }}</span>
            <span v-if="hasApproval(playbook)" class="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-100">{{ t('playbooks.requiresApproval') }}</span>
            <span v-if="hasSensitiveSteps(playbook)" class="rounded border border-red-500/30 bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-100">{{ t('playbooks.sensitiveSteps') }}</span>
          </div>
        </button>
      </div>

      <div v-if="selected" data-test="playbook-detail" class="min-h-0 overflow-y-auto rounded-lg border border-theme-border bg-theme-bg/30 p-3 space-y-4">
        <div class="flex items-start justify-between gap-2">
          <div>
            <div class="text-xs font-mono text-theme-text-muted">{{ selected.id }}</div>
            <h3 class="mt-1 text-base font-bold text-theme-text">{{ selected.name }}</h3>
          </div>
          <button
            type="button"
            data-test="playbook-simulate"
            class="flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
            :disabled="store.isSimulating[selected.id]"
            @click="simulateSelected"
          >
            <Loader2 v-if="store.isSimulating[selected.id]" :size="12" class="animate-spin" />
            <Play v-else :size="12" />
            {{ t('playbooks.simulate') }}
          </button>
        </div>

        <section>
          <h4 class="text-xs uppercase tracking-wider text-theme-text-muted mb-2">{{ t('playbooks.nodes') }}</h4>
          <ol class="space-y-2">
            <li v-for="(node, index) in selected.nodes" :key="node.id" class="rounded border border-theme-border bg-theme-panel/50 p-2 text-xs">
              <div class="flex items-center justify-between gap-2">
                <div class="min-w-0">
                  <span class="font-mono text-theme-text">{{ index + 1 }}. {{ node.type }}</span>
                  <div class="mt-0.5 text-theme-text-muted">{{ nodeLabel(node.type) }}</div>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <span class="rounded border px-1.5 py-0.5 text-[10px]" :class="stepSafetyClass(node.type, node.sensitive)">
                    {{ nodeExecutionLabel(node.type) }}
                  </span>
                  <ShieldAlert v-if="node.type === 'approval.required' || node.sensitive || nodeDefinition(node.type)?.sensitive" :size="13" class="text-amber-300" />
                </div>
              </div>
              <div class="mt-1 text-theme-text-muted font-mono">{{ node.id }}</div>
              <div v-if="nodeBoundary(node.type)" class="mt-1 text-[11px] text-theme-text-muted">
                {{ boundaryLabel(nodeBoundary(node.type)) }}
              </div>
            </li>
          </ol>
        </section>

        <section>
          <h4 class="text-xs uppercase tracking-wider text-theme-text-muted mb-2">{{ t('playbooks.edges') }}</h4>
          <div class="flex flex-wrap gap-1">
            <span v-for="edge in selected.edges" :key="edgeLabel(edge)" class="rounded border border-theme-border bg-theme-panel/60 px-2 py-1 text-xs font-mono text-theme-text">
              {{ edgeLabel(edge) }}
            </span>
          </div>
        </section>

        <section class="rounded-lg border border-theme-border bg-theme-panel/40 p-3 space-y-3">
          <h4 class="text-xs uppercase tracking-wider text-theme-text-muted">{{ t('playbooks.runTitle') }}</h4>
          <div class="flex gap-2">
            <input
              v-model="incidentId"
              data-test="playbook-run-incident-id"
              class="min-w-0 flex-1 rounded border border-theme-border bg-theme-bg px-2 py-1 text-xs text-theme-text placeholder:text-theme-text-muted"
              :placeholder="t('playbooks.incidentPlaceholder')"
            />
            <button
              type="button"
              data-test="playbook-run"
              class="rounded border border-sky-500/40 bg-sky-500/10 px-2 py-1 text-xs font-semibold text-sky-100 hover:bg-sky-500/20 disabled:opacity-50"
              :disabled="!incidentId.trim() || store.isRunning[selected.id]"
              @click="runSelected"
            >
              {{ store.isRunning[selected.id] ? t('playbooks.running') : t('playbooks.runDryRun') }}
            </button>
          </div>
        </section>

        <section v-if="selectedRun" data-test="playbook-run-detail" class="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
          <div class="flex items-start justify-between gap-2">
            <div>
              <h4 class="text-xs uppercase tracking-wider text-amber-100">{{ t('playbooks.run') }} {{ selectedRun.id }}</h4>
              <div class="mt-1 text-xs text-theme-text-muted">
                {{ selectedRun.status }} · {{ selectedRun.dryRun ? t('playbooks.dryRunOnly') : '' }}
              </div>
              <div v-if="selectedRun.ticketUpdate?.status === 'contained'" class="mt-1 text-xs font-semibold text-emerald-200">
                {{ t('playbooks.ticketContained') }}
              </div>
            </div>
            <button
              v-if="selectedRun.status === 'waiting_approval'"
              type="button"
              data-test="playbook-approve-run"
              class="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs font-semibold text-amber-100 hover:bg-amber-500/20 disabled:opacity-50"
              :disabled="store.isApproving[selectedRun.id]"
              @click="approveSelectedRun"
            >
              {{ store.isApproving[selectedRun.id] ? t('playbooks.approving') : t('playbooks.approve') }}
            </button>
          </div>
          <ol class="mt-3 space-y-1">
            <li v-for="step in selectedRun.steps" :key="`${selectedRun.id}-${step.nodeId}-${step.status}`" class="flex items-center justify-between gap-2 rounded border border-theme-border bg-theme-bg/50 px-2 py-1 text-xs">
              <span class="font-mono text-theme-text">{{ step.nodeType }}</span>
              <span class="text-theme-text-muted">{{ step.status }}</span>
            </li>
          </ol>
        </section>

        <section v-if="store.simulations[selected.id]" data-test="playbook-simulation" class="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3">
          <h4 class="text-xs uppercase tracking-wider text-emerald-200 mb-2 flex items-center gap-1">
            <CheckCircle2 :size="13" />
            {{ t('playbooks.simulation') }}
          </h4>
          <div class="text-xs text-theme-text-muted mb-2">
            {{ store.simulations[selected.id].dryRun ? t('playbooks.dryRunOnly') : '' }}
          </div>
          <ol class="space-y-1">
            <li v-for="step in store.simulations[selected.id].steps" :key="`${step.nodeId}-${step.status}`" class="flex items-center justify-between gap-2 rounded border border-theme-border bg-theme-bg/50 px-2 py-1 text-xs">
              <span class="font-mono text-theme-text">{{ step.nodeType }}</span>
              <span class="flex items-center gap-1 text-theme-text-muted">
                <Clock :size="11" />
                {{ step.status }}
              </span>
            </li>
          </ol>
        </section>
      </div>
    </div>
  </div>
</template>
