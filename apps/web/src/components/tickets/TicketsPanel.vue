<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Filter,
  Layers,
  RefreshCcw,
  Sparkles,
  Shield,
  Ticket as TicketIcon,
  Loader2,
  X,
} from 'lucide-vue-next'
import { useTicketsStore } from '../../stores/useTicketsStore'
import { useThemeStore } from '../../stores/useThemeStore'
import {
  analyzeIncident,
  suggestContainment,
  type ContainmentSuggestion,
  type IncidentAnalysis,
  type Ticket,
  type TicketStatus,
  type TriageLevel,
} from '../../services/ticketsClient'

const store = useTicketsStore()
const themeStore = useThemeStore()

const severityFilter = ref<string | null>(null)
const statusFilter = ref<TicketStatus | null>(null)
const selected = ref<Ticket | null>(null)
const isSavingPatch = ref(false)
const patchError = ref<string | null>(null)
const aiAnalysis = ref<IncidentAnalysis | null>(null)
const aiContainment = ref<ContainmentSuggestion | null>(null)
const isAnalyzing = ref(false)
const isContaining = ref(false)
const aiError = ref<string | null>(null)

const tickets = computed(() => store.tickets)

const lanes: { level: TriageLevel; label: string; description: string; color: string }[] = [
  {
    level: 'T1',
    label: 'T1 · Critical',
    description: 'Severity high/critical — immediate response',
    color: 'border-red-500/40 bg-red-500/10 text-red-300',
  },
  {
    level: 'T2',
    label: 'T2 · Investigate',
    description: 'Severity medium — analyst triage required',
    color: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  },
  {
    level: 'T3',
    label: 'T3 · Monitor',
    description: 'Low/informational — backlog',
    color: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  },
]

const statusOptions: { value: TicketStatus; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'contained', label: 'Contained' },
  { value: 'closed', label: 'Closed' },
]

const triageOptions: TriageLevel[] = ['T1', 'T2', 'T3']

const filteredByLane = computed<Record<TriageLevel, Ticket[]>>(() => {
  const result: Record<TriageLevel, Ticket[]> = { T1: [], T2: [], T3: [] }
  for (const ticket of tickets.value) {
    if (severityFilter.value && ticket.severity !== severityFilter.value) continue
    if (statusFilter.value && ticket.ticketStatus !== statusFilter.value) continue
    result[ticket.triageLevel]?.push(ticket)
  }
  return result
})

const statusBadgeClass = (status: TicketStatus) => {
  switch (status) {
    case 'new':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
    case 'investigating':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-300'
    case 'contained':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
    case 'closed':
    default:
      return 'border-theme-border bg-theme-bg/40 text-theme-text-muted'
  }
}

async function applyPatch(
  ticket: Ticket,
  patch: { triageLevel?: TriageLevel; ticketStatus?: TicketStatus },
) {
  isSavingPatch.value = true
  patchError.value = null
  try {
    const updated = await store.patchTicket(ticket.id, patch)
    if (selected.value && selected.value.id === ticket.id) {
      selected.value = updated
    }
  } catch (e: any) {
    patchError.value = e?.message ?? 'Failed to update ticket'
  } finally {
    isSavingPatch.value = false
  }
}

async function runAnalysis(ticket: Ticket) {
  isAnalyzing.value = true
  aiError.value = null
  try {
    aiAnalysis.value = await analyzeIncident(ticket.id)
  } catch (e: any) {
    aiError.value = e?.message ?? 'Failed to analyze incident'
  } finally {
    isAnalyzing.value = false
  }
}

async function runContainment(ticket: Ticket) {
  isContaining.value = true
  aiError.value = null
  try {
    aiContainment.value = await suggestContainment(ticket.id)
  } catch (e: any) {
    aiError.value = e?.message ?? 'Failed to fetch containment suggestions'
  } finally {
    isContaining.value = false
  }
}

async function applySuggestedAnalysis(ticket: Ticket) {
  if (!aiAnalysis.value) return
  await applyPatch(ticket, {
    triageLevel: aiAnalysis.value.suggestedTriage,
    ticketStatus: aiAnalysis.value.suggestedTicketStatus,
  })
}

function resetAiState() {
  aiAnalysis.value = null
  aiContainment.value = null
  aiError.value = null
}

function severityChipClass(severity: 'low' | 'medium' | 'high') {
  if (severity === 'high') return 'border-red-500/40 bg-red-500/10 text-red-300'
  if (severity === 'medium') return 'border-amber-500/40 bg-amber-500/10 text-amber-300'
  return 'border-sky-500/40 bg-sky-500/10 text-sky-300'
}

function formatTime(value: string | null | undefined) {
  if (!value) return ''
  try {
    return new Date(value).toISOString().replace('T', ' ').slice(0, 19)
  } catch (e) {
    return value
  }
}

watch(
  () => selected.value?.id,
  () => {
    resetAiState()
  },
)

onMounted(() => store.startPolling(8000))
onBeforeUnmount(() => store.stopPolling())
</script>

<template>
  <div class="flex h-full flex-col w-full">
    <!-- Header -->
    <div class="px-4 pt-4 pb-3 border-b border-theme-border flex items-center justify-between">
      <div>
        <h2 class="font-bold text-lg text-theme-text flex items-center gap-2">
          <TicketIcon :size="18" />
          SOC Tickets
        </h2>
        <p class="text-xs text-theme-text-muted mt-1">
          Triagem T1/T2/T3 sobre incidentes do Kowalski SIEM. Atualiza a cada 8s.
        </p>
      </div>
      <button
        type="button"
        @click="store.refresh()"
        class="text-theme-text-muted hover:text-theme-text"
        :disabled="store.isLoading"
        title="Atualizar agora"
      >
        <RefreshCcw :size="16" :class="store.isLoading ? 'animate-spin' : ''" />
      </button>
    </div>

    <!-- Filters -->
    <div class="px-4 py-2 border-b border-theme-border bg-theme-bg/30 flex items-center gap-2 flex-wrap text-xs">
      <Filter :size="14" class="text-theme-text-muted" />
      <select v-model="statusFilter" class="bg-theme-bg border border-theme-border rounded px-2 py-1 text-theme-text">
        <option :value="null">Todos status</option>
        <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <select v-model="severityFilter" class="bg-theme-bg border border-theme-border rounded px-2 py-1 text-theme-text">
        <option :value="null">Toda severidade</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
        <option value="informational">Informational</option>
      </select>
      <span class="ml-auto text-theme-text-muted">
        Total: {{ tickets.length }}
      </span>
    </div>

    <div v-if="store.error" class="px-4 py-2 text-xs border-b border-red-500/30 bg-red-500/10 text-red-300 flex items-start gap-2">
      <AlertCircle :size="14" class="mt-0.5 shrink-0" />
      <span>{{ store.error }}</span>
    </div>

    <!-- Lanes -->
    <div class="flex-1 overflow-y-auto px-3 py-3 space-y-4">
      <section
        v-for="lane in lanes"
        :key="lane.level"
        class="rounded-lg border border-theme-border bg-theme-bg/30"
      >
        <header class="flex items-center justify-between gap-2 px-3 py-2 border-b border-theme-border">
          <div class="flex items-center gap-2">
            <span
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wider"
              :class="lane.color"
            >
              <Layers :size="11" />
              {{ lane.label }}
            </span>
            <span class="text-xs text-theme-text-muted">{{ filteredByLane[lane.level].length }}</span>
          </div>
          <span class="text-[10px] text-theme-text-muted hidden md:inline">{{ lane.description }}</span>
        </header>
        <ul v-if="filteredByLane[lane.level].length" class="divide-y divide-theme-border/60">
          <li
            v-for="ticket in filteredByLane[lane.level]"
            :key="ticket.id"
          >
            <button
              type="button"
              @click="selected = ticket"
              class="w-full text-left px-3 py-2 hover:bg-theme-bg/60 transition flex items-start justify-between gap-3"
            >
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-semibold text-theme-text truncate">{{ ticket.title }}</span>
                  <span
                    class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px]"
                    :class="statusBadgeClass(ticket.ticketStatus)"
                  >
                    {{ ticket.ticketStatus }}
                  </span>
                </div>
                <div class="text-xs text-theme-text-muted truncate">{{ ticket.summary }}</div>
                <div class="mt-1 flex items-center gap-2 text-[10px] text-theme-text-muted">
                  <span class="font-mono">{{ ticket.id }}</span>
                  <span>·</span>
                  <span class="uppercase">{{ ticket.severity }}</span>
                  <span>·</span>
                  <Clock :size="10" />
                  <span>{{ formatTime(ticket.createdAt) }}</span>
                </div>
              </div>
              <ChevronRight :size="14" class="text-theme-text-muted mt-1 shrink-0" />
            </button>
          </li>
        </ul>
        <div v-else class="px-3 py-3 text-xs text-theme-text-muted italic">
          Sem tickets nesta lane.
        </div>
      </section>
    </div>

    <!-- Detail drawer -->
    <div
      v-if="selected"
      class="fixed inset-0 z-40 flex justify-end bg-black/50 backdrop-blur-sm"
      @click.self="selected = null"
    >
      <div class="w-full max-w-md h-full bg-theme-panel border-l border-theme-border overflow-y-auto shadow-2xl">
        <div class="px-4 py-3 border-b border-theme-border flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-xs text-theme-text-muted">{{ selected.id }}</div>
            <h3 class="text-lg font-bold text-theme-text mt-1">{{ selected.title }}</h3>
            <div class="mt-2 flex items-center gap-2 flex-wrap">
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wider"
                :class="lanes.find(l => l.level === selected!.triageLevel)?.color || ''">
                {{ selected.triageLevel }}
              </span>
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px]"
                :class="statusBadgeClass(selected.ticketStatus)">
                {{ selected.ticketStatus }}
              </span>
              <span class="text-[10px] uppercase text-theme-text-muted">{{ selected.severity }}</span>
            </div>
          </div>
          <button type="button" @click="selected = null" class="text-theme-text-muted hover:text-theme-text">
            <X :size="16" />
          </button>
        </div>

        <div class="px-4 py-3 border-b border-theme-border">
          <p class="text-sm text-theme-text whitespace-pre-line">{{ selected.summary }}</p>
          <div class="mt-2 text-xs text-theme-text-muted">
            Aberto em {{ formatTime(selected.createdAt) }}
          </div>
        </div>

        <!-- Actions -->
        <div class="px-4 py-3 border-b border-theme-border space-y-3">
          <div>
            <label class="block text-xs uppercase tracking-wider text-theme-text-muted mb-1">Triage level</label>
            <div class="flex gap-2">
              <button
                v-for="level in triageOptions"
                :key="level"
                type="button"
                :disabled="isSavingPatch || level === selected.triageLevel"
                @click="applyPatch(selected!, { triageLevel: level })"
                class="px-3 py-1 rounded border text-xs font-semibold disabled:opacity-60"
                :class="level === selected.triageLevel
                  ? lanes.find(l => l.level === level)?.color
                  : 'border-theme-border text-theme-text hover:brightness-110'"
              >
                {{ level }}
              </button>
            </div>
          </div>
          <div>
            <label class="block text-xs uppercase tracking-wider text-theme-text-muted mb-1">Ticket status</label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="opt in statusOptions"
                :key="opt.value"
                type="button"
                :disabled="isSavingPatch || opt.value === selected.ticketStatus"
                @click="applyPatch(selected!, { ticketStatus: opt.value })"
                class="px-3 py-1 rounded border text-xs font-semibold disabled:opacity-60"
                :class="opt.value === selected.ticketStatus
                  ? statusBadgeClass(opt.value)
                  : 'border-theme-border text-theme-text hover:brightness-110'"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div v-if="patchError" class="text-xs text-red-300 flex items-start gap-1">
            <AlertCircle :size="13" class="mt-0.5" />
            {{ patchError }}
          </div>
          <div v-if="isSavingPatch" class="text-xs text-theme-text-muted flex items-center gap-1">
            <Loader2 :size="12" class="animate-spin" />
            Salvando...
          </div>
        </div>

        <!-- AI Assistant -->
        <div class="px-4 py-3 border-b border-theme-border bg-fuchsia-500/5">
          <div class="flex items-center justify-between mb-2">
            <h4 class="text-xs uppercase tracking-wider text-fuchsia-300 flex items-center gap-1">
              <Sparkles :size="13" />
              AI assistant
            </h4>
            <div class="flex gap-2">
              <button
                type="button"
                :disabled="isAnalyzing"
                @click="runAnalysis(selected!)"
                class="text-xs px-2 py-1 rounded border border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200 hover:bg-fuchsia-500/20 disabled:opacity-50 flex items-center gap-1"
              >
                <Loader2 v-if="isAnalyzing" :size="11" class="animate-spin" />
                <Sparkles v-else :size="11" />
                Analyze
              </button>
              <button
                type="button"
                :disabled="isContaining"
                @click="runContainment(selected!)"
                class="text-xs px-2 py-1 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 flex items-center gap-1"
              >
                <Loader2 v-if="isContaining" :size="11" class="animate-spin" />
                <Shield v-else :size="11" />
                Suggest containment
              </button>
            </div>
          </div>

          <div v-if="aiError" class="text-xs text-red-300 flex items-start gap-1 mb-2">
            <AlertCircle :size="13" class="mt-0.5" />
            {{ aiError }}
          </div>

          <div v-if="aiAnalysis" class="mt-2 p-3 rounded-lg border border-fuchsia-500/30 bg-fuchsia-950/30 space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-sm font-semibold text-fuchsia-100">{{ aiAnalysis.headline }}</span>
              <span class="text-xs font-mono px-1.5 py-0.5 rounded border border-fuchsia-500/40 text-fuchsia-200">
                risk {{ aiAnalysis.riskScore }}/100
              </span>
            </div>
            <p class="text-xs text-theme-text whitespace-pre-line leading-relaxed">{{ aiAnalysis.summary }}</p>
            <div class="text-xs">
              <span class="text-theme-text-muted">Suggested:</span>
              <span class="ml-1 text-fuchsia-200 font-semibold">{{ aiAnalysis.suggestedTriage }} · {{ aiAnalysis.suggestedTicketStatus }}</span>
              <button
                type="button"
                :disabled="isSavingPatch"
                @click="applySuggestedAnalysis(selected!)"
                class="ml-2 px-2 py-0.5 rounded border border-fuchsia-500/40 text-fuchsia-200 hover:bg-fuchsia-500/15 text-[10px] disabled:opacity-50"
              >
                Apply
              </button>
            </div>
            <div v-if="aiAnalysis.indicatorsOfCompromise?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">IoCs</div>
              <div class="flex flex-wrap gap-1 mt-1">
                <span
                  v-for="ioc in aiAnalysis.indicatorsOfCompromise"
                  :key="ioc"
                  class="text-[10px] font-mono px-1.5 py-0.5 rounded border border-theme-border bg-theme-bg/60 text-theme-text"
                >
                  {{ ioc }}
                </span>
              </div>
            </div>
            <div v-if="aiAnalysis.nextSteps?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">Next steps</div>
              <ol class="list-decimal list-inside text-xs text-theme-text space-y-0.5 mt-1">
                <li v-for="(step, i) in aiAnalysis.nextSteps" :key="i">{{ step }}</li>
              </ol>
            </div>
            <div v-if="aiAnalysis.references?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">References</div>
              <ul class="text-[10px] text-fuchsia-200 underline break-all">
                <li v-for="ref in aiAnalysis.references" :key="ref">{{ ref }}</li>
              </ul>
            </div>
          </div>

          <div v-if="aiContainment" class="mt-3 p-3 rounded-lg border border-emerald-500/30 bg-emerald-950/30 space-y-2">
            <div class="text-sm font-semibold text-emerald-100 flex items-center gap-1">
              <Shield :size="13" />
              Containment plan
            </div>
            <p class="text-xs text-theme-text leading-relaxed">{{ aiContainment.summary }}</p>
            <ol class="space-y-2">
              <li
                v-for="(step, i) in aiContainment.steps"
                :key="i"
                class="text-xs border border-theme-border/70 bg-theme-bg/40 rounded p-2"
              >
                <div class="flex items-center justify-between gap-2 mb-1">
                  <span class="font-semibold text-theme-text">{{ i + 1 }}. {{ step.title }}</span>
                  <span
                    class="text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wider"
                    :class="severityChipClass(step.severity)"
                  >
                    {{ step.severity }}
                  </span>
                </div>
                <p class="text-theme-text-muted leading-relaxed">{{ step.description }}</p>
                <div class="mt-1 flex items-center gap-2 text-[10px] text-theme-text-muted">
                  <span class="font-mono">{{ step.playbookNodeType }}</span>
                  <span v-if="step.requiresApproval" class="text-amber-300">requires approval</span>
                  <span v-else class="text-emerald-300">auto-safe</span>
                </div>
              </li>
            </ol>
            <p class="text-[10px] text-theme-text-muted italic">
              Steps stay as drafts until Phase 4 wires them into soar_skipper.
            </p>
          </div>

          <p v-if="!aiAnalysis && !aiContainment && !aiError && !isAnalyzing && !isContaining" class="text-xs text-theme-text-muted italic">
            Run "Analyze" to get an AI summary or "Suggest containment" to draft a plan. Nothing is executed automatically.
          </p>
        </div>

        <!-- Entities -->
        <div v-if="selected.entities && Object.keys(selected.entities).length" class="px-4 py-3 border-b border-theme-border">
          <h4 class="text-xs uppercase tracking-wider text-theme-text-muted mb-2">Entidades</h4>
          <dl class="text-xs grid grid-cols-3 gap-x-2 gap-y-1">
            <template v-for="(value, key) in selected.entities" :key="key">
              <dt class="col-span-1 text-theme-text-muted">{{ key }}</dt>
              <dd class="col-span-2 text-theme-text font-mono break-all">{{ value }}</dd>
            </template>
          </dl>
        </div>

        <!-- Timeline -->
        <div class="px-4 py-3">
          <h4 class="text-xs uppercase tracking-wider text-theme-text-muted mb-2">Timeline</h4>
          <ul class="space-y-2">
            <li
              v-for="item in selected.timeline"
              :key="item.id"
              class="text-xs border-l-2 border-theme-border pl-3"
            >
              <div class="text-theme-text">{{ item.message }}</div>
              <div class="text-theme-text-muted">{{ formatTime(item.occurredAt) }}</div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
