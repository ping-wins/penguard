<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Filter,
  Layers,
  Play,
  RefreshCcw,
  Sparkles,
  Shield,
  Ticket as TicketIcon,
  Workflow,
  Loader2,
  X,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useTicketsStore } from '../../stores/useTicketsStore'
import {
  useIntegrationsStore,
  type FortiWebBlockReviewResponse,
} from '../../stores/useIntegrationsStore'
import {
  analyzeIncident,
  approvePlaybookRun,
  applyContainmentPlaybook,
  applyPlaybookRunPolicy,
  createPlaybookRunPolicyReview,
  draftContainmentPlaybook,
  enrichIncidentThreatIntel,
  getIncidentTriageContext,
  instantiateRecommendedPlaybook,
  resetIncidentStore,
  suggestContainment,
  type ApplyContainmentResponse,
  type ContainmentSuggestion,
  type FortiGatePolicyScope,
  type IncidentAnalysis,
  type PlaybookRunPolicyApplyResponse,
  type PlaybookDraftResponse,
  type PlaybookRunPolicyReviewResponse,
  type Ticket,
  type TicketStatus,
  type ThreatIntelEnrichmentResponse,
  type ThreatIntelVerdict,
  type TriageContext,
  type TriageLevel,
} from '../../services/ticketsClient'
import { Trash2 } from 'lucide-vue-next'
import { sourceBadgeFor, type SourceBadge } from '../../utils/sourceBadges'

const { t } = useI18n()
const store = useTicketsStore()
const integrationsStore = useIntegrationsStore()

function cvssBadgeClass(severity: string | undefined): string {
  switch (severity) {
    case 'Critical':
      return 'bg-red-600/30 text-red-200 border border-red-500/50'
    case 'High':
      return 'bg-orange-600/30 text-orange-200 border border-orange-500/50'
    case 'Medium':
      return 'bg-amber-600/30 text-amber-100 border border-amber-500/50'
    case 'Low':
      return 'bg-emerald-600/25 text-emerald-200 border border-emerald-500/50'
    default:
      return 'bg-theme-bg/60 text-theme-text-muted border border-theme-border'
  }
}

function cvssCalcUrl(vector: string): string {
  // FIRST hosts the official CVSS 3.1 calculator that accepts the vector as
  // a URL fragment, so clicking the vector chip opens the full breakdown.
  return `https://www.first.org/cvss/calculator/3.1#${encodeURIComponent(vector)}`
}

const severityFilter = ref<string | null>(null)
const statusFilter = ref<TicketStatus | null>(null)
const selected = ref<Ticket | null>(null)
const isSavingPatch = ref(false)
const patchError = ref<string | null>(null)
const aiAnalysis = ref<IncidentAnalysis | null>(null)
const aiContainment = ref<ContainmentSuggestion | null>(null)
const triageContext = ref<TriageContext | null>(null)
const isLoadingTriageContext = ref(false)
const triageContextError = ref<string | null>(null)
const isAnalyzing = ref(false)
const isContaining = ref(false)
const aiError = ref<string | null>(null)
const threatIntel = ref<ThreatIntelEnrichmentResponse | null>(null)
const isEnrichingThreatIntel = ref(false)
const threatIntelError = ref<string | null>(null)
const playbookDraft = ref<PlaybookDraftResponse | null>(null)
const applyResult = ref<ApplyContainmentResponse | null>(null)
const isDrafting = ref(false)
const instantiatingTemplateId = ref<string | null>(null)
const isApplying = ref(false)
const isApprovingRun = ref(false)
const playbookError = ref<string | null>(null)
const policyReview = ref<PlaybookRunPolicyReviewResponse | null>(null)
const policyApplyResult = ref<PlaybookRunPolicyApplyResponse | null>(null)
const isCreatingPolicyReview = ref(false)
const isApplyingPolicyReview = ref(false)
const fortiwebBlockReview = ref<FortiWebBlockReviewResponse | null>(null)
const fortiwebBlockResult = ref<FortiWebBlockReviewResponse | null>(null)
const isCreatingFortiwebBlockReview = ref(false)
const isApplyingFortiwebBlock = ref(false)
const isRemovingFortiwebBlock = ref(false)
const fortiwebBlockError = ref<string | null>(null)
const policyForm = ref({
  integrationId: '',
  scope: 'source_destination' as FortiGatePolicyScope,
  sourceInterface: 'port2',
  destinationInterface: 'port3',
  sourceIp: '',
  destinationIp: '',
  service: 'ALL',
  durationMinutes: 30,
})
const fortiwebBlockForm = ref({
  integrationId: '',
  sourceIp: '',
})

const tickets = computed(() => store.tickets)
const fortiwebIntegrations = computed(() => integrationsStore.integrations.filter(integration => integration.type === 'fortiweb'))
const aiAnalysisBadge = computed(() => aiAnalysis.value ? sourceBadgeFor(aiAnalysis.value) : null)
const selectedDetection = computed(() => {
  const detection = selected.value?.attributes?.detection
  return detection && typeof detection === 'object' ? detection as Record<string, any> : null
})
const visibleTriageContext = computed(() => {
  return triageContext.value?.incidentId ? triageContext.value : null
})
const threatIntelFlagged = computed(() => threatIntel.value?.summary.flagged ?? [])

function formatTriageValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined && item !== null && item !== '')
      .map(([key, item]) => `${key}: ${String(item)}`)
      .join(' · ')
  }
  if (value === undefined || value === null || value === '') return '—'
  return String(value)
}

function confidenceClass(confidence: string | undefined): string {
  if (confidence === 'high') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
  if (confidence === 'medium') return 'border-amber-500/40 bg-amber-500/10 text-amber-200'
  return 'border-sky-500/40 bg-sky-500/10 text-sky-200'
}

function candidateClass(available: boolean): string {
  return available
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
    : 'border-theme-border bg-theme-bg/50 text-theme-text-muted'
}

function thresholdLabel(threshold: any): string {
  if (!threshold || typeof threshold !== 'object') return ''
  return [threshold.path, threshold.operator, threshold.value]
    .filter((part) => part !== undefined && part !== null && part !== '')
    .join(' ')
}

const lanes = computed<{ level: TriageLevel; label: string; description: string; color: string }[]>(() => [
  {
    level: 'T1',
    label: t('tickets.lanes.T1Label'),
    description: t('tickets.lanes.T1Description'),
    color: 'border-red-500/40 bg-red-500/10 text-red-300',
  },
  {
    level: 'T2',
    label: t('tickets.lanes.T2Label'),
    description: t('tickets.lanes.T2Description'),
    color: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  },
  {
    level: 'T3',
    label: t('tickets.lanes.T3Label'),
    description: t('tickets.lanes.T3Description'),
    color: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  },
])

const statusOptions = computed<{ value: TicketStatus; label: string }[]>(() => [
  { value: 'new', label: t('tickets.status.new') },
  { value: 'investigating', label: t('tickets.status.investigating') },
  { value: 'contained', label: t('tickets.status.contained') },
  { value: 'closed', label: t('tickets.status.closed') },
])

const triageOptions: TriageLevel[] = ['T1', 'T2', 'T3']
const policyScopeOptions: { value: FortiGatePolicyScope; labelKey: string }[] = [
  { value: 'source_only', labelKey: 'tickets.policy.scopeSourceOnly' },
  { value: 'source_destination', labelKey: 'tickets.policy.scopeSourceDestination' },
  { value: 'source_destination_service', labelKey: 'tickets.policy.scopeSourceDestinationService' },
]

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

const policyReviewRequired = computed(() => Boolean(applyResult.value?.run?.policyReviewRequired))
const canCreatePolicyReview = computed(() => {
  return Boolean(
    applyResult.value?.run?.id
      && policyForm.value.integrationId.trim()
      && policyForm.value.sourceInterface.trim()
      && policyForm.value.destinationInterface.trim()
      && policyForm.value.sourceIp.trim()
      && (policyForm.value.scope === 'source_only' || policyForm.value.destinationIp.trim()),
  )
})
const canApplyPolicyReview = computed(() => Boolean(policyReview.value && !policyApplyResult.value))
const canCreateFortiwebBlockReview = computed(() => {
  return Boolean(fortiwebBlockForm.value.integrationId.trim() && fortiwebBlockForm.value.sourceIp.trim())
})
const canApplyFortiwebBlock = computed(() => Boolean(fortiwebBlockReview.value && fortiwebBlockResult.value?.status !== 'active'))
const canRemoveFortiwebBlock = computed(() => fortiwebBlockResult.value?.status === 'active')

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

let triageContextRequestId = 0
async function loadTriageContext(ticketId: string) {
  const requestId = ++triageContextRequestId
  triageContext.value = null
  triageContextError.value = null
  isLoadingTriageContext.value = true
  try {
    const context = await getIncidentTriageContext(ticketId)
    if (requestId === triageContextRequestId) {
      triageContext.value = context?.incidentId ? context : null
    }
  } catch (e: any) {
    if (requestId === triageContextRequestId) {
      triageContextError.value = e?.message ?? t('tickets.drawer.triageContextError')
    }
  } finally {
    if (requestId === triageContextRequestId) {
      isLoadingTriageContext.value = false
    }
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

async function runThreatIntel(ticket: Ticket) {
  isEnrichingThreatIntel.value = true
  threatIntelError.value = null
  try {
    threatIntel.value = await enrichIncidentThreatIntel(ticket.id)
  } catch (e: any) {
    threatIntelError.value = e?.message ?? t('tickets.threatIntel.error')
  } finally {
    isEnrichingThreatIntel.value = false
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
  threatIntel.value = null
  threatIntelError.value = null
  isEnrichingThreatIntel.value = false
  playbookDraft.value = null
  applyResult.value = null
  playbookError.value = null
  policyReview.value = null
  policyApplyResult.value = null
  isCreatingPolicyReview.value = false
  isApplyingPolicyReview.value = false
  resetFortiwebBlockState()
}

function resetFortiwebBlockState() {
  fortiwebBlockReview.value = null
  fortiwebBlockResult.value = null
  fortiwebBlockError.value = null
  isCreatingFortiwebBlockReview.value = false
  isApplyingFortiwebBlock.value = false
  isRemovingFortiwebBlock.value = false
}

async function runDraftPlaybook(ticket: Ticket) {
  playbookError.value = null
  isDrafting.value = true
  try {
    playbookDraft.value = await draftContainmentPlaybook(ticket.id)
  } catch (e: any) {
    playbookError.value = e?.message ?? 'Failed to draft playbook'
  } finally {
    isDrafting.value = false
  }
}

async function runInstantiateTemplate(ticket: Ticket, templateId: string) {
  playbookError.value = null
  instantiatingTemplateId.value = templateId
  try {
    playbookDraft.value = await instantiateRecommendedPlaybook(ticket.id, templateId)
    aiContainment.value = playbookDraft.value.suggestion
  } catch (e: any) {
    playbookError.value = e?.message ?? t('tickets.ai.instantiateTemplateError')
  } finally {
    instantiatingTemplateId.value = null
  }
}

async function runApplyPlaybook(ticket: Ticket) {
  if (!playbookDraft.value) return
  playbookError.value = null
  isApplying.value = true
  try {
    const result = await applyContainmentPlaybook(ticket.id, playbookDraft.value.playbook.id)
    applyResult.value = result
    if (result.ticket) {
      const idx = store.tickets.findIndex((t) => t.id === ticket.id)
      if (idx >= 0) store.tickets[idx] = result.ticket
      selected.value = result.ticket
    } else {
      await store.refresh()
    }
  } catch (e: any) {
    playbookError.value = e?.message ?? 'Failed to apply playbook'
  } finally {
    isApplying.value = false
  }
}

async function runApprovePlaybook(ticket: Ticket) {
  const runId = applyResult.value?.run?.id
  if (!runId) return
  playbookError.value = null
  isApprovingRun.value = true
  try {
    const approved = await approvePlaybookRun(runId)
    const ticketUpdate = approved.ticketUpdate
    const updatedTicket = ticketUpdate?.ticket
    if (updatedTicket) {
      const idx = store.tickets.findIndex((t) => t.id === ticket.id)
      if (idx >= 0) store.tickets[idx] = updatedTicket
      selected.value = updatedTicket
    } else if (ticketUpdate?.status === 'contained') {
      await store.refresh()
    }
    if (applyResult.value) {
      const ticketWasContained = ticketUpdate?.status === 'contained'
      const ticketUpdateFailed = ticketUpdate?.status === 'failed'
      if (ticketUpdateFailed) {
        playbookError.value = ticketUpdate.error || t('tickets.ai.approveTicketUpdateFailed')
      }
      applyResult.value = {
        ...applyResult.value,
        run: { ...applyResult.value.run, ...approved },
        ticket: updatedTicket ?? applyResult.value.ticket,
        ticketStatus: ticketWasContained
          ? 'contained'
          : applyResult.value.ticketStatus,
      }
      if (approved.policyReviewRequired) {
        primePolicyReviewForm(ticket)
      }
    }
  } catch (e: any) {
    playbookError.value = e?.message ?? 'Failed to approve playbook run'
  } finally {
    isApprovingRun.value = false
  }
}

function stringValue(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return ''
}

function primePolicyReviewForm(ticket: Ticket) {
  const attributes = ticket.attributes ?? {}
  const entities = ticket.entities ?? {}
  const sourceIp = stringValue(
    attributes.sourceIp,
    attributes.source_ip,
    attributes.srcip,
    entities.sourceIp,
    entities.source_ip,
    entities.srcip,
  )
  const destinationIp = stringValue(
    attributes.destinationIp,
    attributes.destination_ip,
    attributes.dstip,
    entities.destinationIp,
    entities.destination_ip,
    entities.dstip,
  )
  policyReview.value = null
  policyApplyResult.value = null
  policyForm.value = {
    ...policyForm.value,
    integrationId: stringValue(attributes.integrationId, attributes.integration_id, entities.integrationId),
    scope: destinationIp ? 'source_destination' : 'source_only',
    sourceIp,
    destinationIp,
    service: stringValue(attributes.service, attributes.destinationService, entities.service) || 'ALL',
  }
}

function sourceIpForTicket(ticket: Ticket): string {
  const attributes = ticket.attributes ?? {}
  const entities = ticket.entities ?? {}
  return stringValue(
    attributes.sourceIp,
    attributes.source_ip,
    attributes.srcip,
    entities.sourceIp,
    entities.source_ip,
    entities.srcip,
  )
}

function primeFortiwebBlockForm(ticket: Ticket) {
  fortiwebBlockForm.value = {
    integrationId: fortiwebBlockForm.value.integrationId || fortiwebIntegrations.value[0]?.id || '',
    sourceIp: sourceIpForTicket(ticket),
  }
}

async function runCreateFortiwebBlockReview(ticket: Ticket) {
  fortiwebBlockError.value = null
  fortiwebBlockReview.value = null
  fortiwebBlockResult.value = null
  isCreatingFortiwebBlockReview.value = true
  try {
    const result = await integrationsStore.reviewFortiwebSourceBlock(
      fortiwebBlockForm.value.integrationId.trim(),
      {
        sourceIp: fortiwebBlockForm.value.sourceIp.trim(),
        incidentId: ticket.id,
        reason: ticket.title,
      },
    )
    if (result.success) {
      fortiwebBlockReview.value = result.data
    } else {
      fortiwebBlockError.value = result.error || t('tickets.fortiweb.reviewError')
    }
  } finally {
    isCreatingFortiwebBlockReview.value = false
  }
}

async function runApplyFortiwebBlock() {
  if (!fortiwebBlockReview.value) return
  fortiwebBlockError.value = null
  isApplyingFortiwebBlock.value = true
  try {
    const result = await integrationsStore.applyFortiwebSourceBlock(
      fortiwebBlockForm.value.integrationId.trim(),
      fortiwebBlockReview.value.id,
      {
        reviewHash: fortiwebBlockReview.value.reviewHash,
        confirmed: true,
      },
    )
    if (result.success) {
      fortiwebBlockResult.value = result.data
    } else {
      fortiwebBlockError.value = result.error || t('tickets.fortiweb.applyError')
    }
  } finally {
    isApplyingFortiwebBlock.value = false
  }
}

async function runRemoveFortiwebBlock() {
  const blockId = fortiwebBlockResult.value?.id || fortiwebBlockReview.value?.id
  if (!blockId) return
  fortiwebBlockError.value = null
  isRemovingFortiwebBlock.value = true
  try {
    const result = await integrationsStore.removeFortiwebSourceBlock(
      fortiwebBlockForm.value.integrationId.trim(),
      blockId,
    )
    if (result.success) {
      fortiwebBlockResult.value = result.data
    } else {
      fortiwebBlockError.value = result.error || t('tickets.fortiweb.removeError')
    }
  } finally {
    isRemovingFortiwebBlock.value = false
  }
}

async function runCreatePolicyReview() {
  const runId = applyResult.value?.run?.id
  if (!runId) return
  playbookError.value = null
  isCreatingPolicyReview.value = true
  policyApplyResult.value = null
  try {
    policyReview.value = await createPlaybookRunPolicyReview(runId, {
      integrationId: policyForm.value.integrationId.trim(),
      scope: policyForm.value.scope,
      sourceIp: policyForm.value.sourceIp.trim(),
      destinationIp: policyForm.value.destinationIp.trim() || undefined,
      service: policyForm.value.service.trim() || 'ALL',
      sourceInterface: policyForm.value.sourceInterface.trim(),
      destinationInterface: policyForm.value.destinationInterface.trim(),
      durationMinutes: Number(policyForm.value.durationMinutes) || 30,
    })
  } catch (e: any) {
    playbookError.value = e?.message ?? t('tickets.policy.reviewError')
  } finally {
    isCreatingPolicyReview.value = false
  }
}

async function runApplyPolicyReview(ticket: Ticket) {
  const runId = applyResult.value?.run?.id
  if (!runId || !policyReview.value) return
  playbookError.value = null
  isApplyingPolicyReview.value = true
  try {
    const result = await applyPlaybookRunPolicy(runId, {
      integrationId: policyForm.value.integrationId.trim(),
      requestId: policyReview.value.request_id,
      reviewHash: policyReview.value.review_hash,
    })
    policyApplyResult.value = result
    const ticketUpdate = result.ticketUpdate
    const updatedTicket = ticketUpdate?.ticket
    if (updatedTicket) {
      const idx = store.tickets.findIndex((t) => t.id === ticket.id)
      if (idx >= 0) store.tickets[idx] = updatedTicket
      selected.value = updatedTicket
    } else if (ticketUpdate?.status === 'contained') {
      await store.refresh()
    } else if (ticketUpdate?.status === 'failed') {
      playbookError.value = ticketUpdate.error || t('tickets.policy.ticketUpdateFailed')
    }
    if (applyResult.value && ticketUpdate?.status === 'contained') {
      applyResult.value = {
        ...applyResult.value,
        ticket: updatedTicket ?? applyResult.value.ticket,
        ticketStatus: 'contained',
      }
    }
  } catch (e: any) {
    playbookError.value = e?.message ?? t('tickets.policy.applyError')
  } finally {
    isApplyingPolicyReview.value = false
  }
}

function severityChipClass(severity: 'low' | 'medium' | 'high') {
  if (severity === 'high') return 'border-red-500/40 bg-red-500/10 text-red-300'
  if (severity === 'medium') return 'border-amber-500/40 bg-amber-500/10 text-amber-300'
  return 'border-sky-500/40 bg-sky-500/10 text-sky-300'
}

function sourceBadgeClass(badge: SourceBadge) {
  if (badge.tone === 'demo') return 'border-amber-500/40 bg-amber-500/10 text-amber-200'
  if (badge.tone === 'simulator') return 'border-sky-500/40 bg-sky-500/10 text-sky-200'
  if (badge.tone === 'ai') return 'border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200'
  return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
}

function threatIntelVerdictClass(verdict: ThreatIntelVerdict | string) {
  if (verdict === 'malicious') return 'border-red-500/40 bg-red-500/10 text-red-300'
  if (verdict === 'suspicious') return 'border-amber-500/40 bg-amber-500/10 text-amber-200'
  if (verdict === 'clean') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
  return 'border-theme-border bg-theme-bg/60 text-theme-text-muted'
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
  (ticketId) => {
    resetAiState()
    triageContext.value = null
    triageContextError.value = null
    if (selected.value) primeFortiwebBlockForm(selected.value)
    if (ticketId) void loadTriageContext(ticketId)
  },
)

watch(
  () => fortiwebIntegrations.value.map(integration => integration.id).join('|'),
  () => {
    if (!fortiwebBlockForm.value.integrationId && fortiwebIntegrations.value[0]) {
      fortiwebBlockForm.value.integrationId = fortiwebIntegrations.value[0].id
    }
  },
)

onMounted(() => {
  store.startRealtime()
  integrationsStore.fetchIntegrations()
})
onBeforeUnmount(() => store.stopRealtime())

const isResetting = ref(false)
const resetMessage = ref<string | null>(null)
async function resetIncidents() {
  if (isResetting.value) return
  const ok = window.confirm(t('tickets.resetConfirm'))
  if (!ok) return
  isResetting.value = true
  resetMessage.value = null
  try {
    const result = await resetIncidentStore()
    resetMessage.value = t('tickets.resetDone', {
      events: result.eventsDeleted,
      incidents: result.incidentsDeleted,
    })
    await store.refresh()
  } catch (error: any) {
    resetMessage.value = error?.message ?? t('tickets.resetFailed')
  } finally {
    isResetting.value = false
  }
}
</script>

<template>
  <div class="flex h-full flex-col w-full">
    <!-- Header -->
    <div class="px-4 pt-4 pb-3 border-b border-theme-border flex items-center justify-between">
      <div>
        <h2 class="font-bold text-lg text-theme-text flex items-center gap-2">
          <TicketIcon :size="18" />
          {{ t('tickets.title') }}
        </h2>
        <p class="text-xs text-theme-text-muted mt-1">
          {{ t('tickets.subtitle') }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          @click="resetIncidents"
          class="flex items-center gap-1 rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-300 transition-colors hover:bg-red-500/20 disabled:opacity-50"
          :disabled="isResetting || store.isLoading"
          :title="t('tickets.resetTooltip')"
        >
          <Trash2 :size="14" />
          <span>{{ isResetting ? t('tickets.resetWorking') : t('tickets.resetLabel') }}</span>
        </button>
        <button
          type="button"
          @click="store.refresh()"
          class="text-theme-text-muted hover:text-theme-text"
          :disabled="store.isLoading"
          :title="t('tickets.refreshTooltip')"
        >
          <RefreshCcw :size="16" :class="store.isLoading ? 'animate-spin' : ''" />
        </button>
      </div>
    </div>
    <div
      v-if="resetMessage"
      class="px-4 py-2 text-xs border-b border-amber-500/30 bg-amber-500/10 text-amber-200"
    >{{ resetMessage }}</div>

    <!-- Filters -->
    <div class="px-4 py-2 border-b border-theme-border bg-theme-bg/30 flex items-center gap-2 flex-wrap text-xs">
      <Filter :size="14" class="text-theme-text-muted" />
      <select v-model="statusFilter" class="bg-theme-bg border border-theme-border rounded px-2 py-1 text-theme-text">
        <option :value="null">{{ t('tickets.filters.allStatuses') }}</option>
        <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <select v-model="severityFilter" class="bg-theme-bg border border-theme-border rounded px-2 py-1 text-theme-text">
        <option :value="null">{{ t('tickets.filters.allSeverities') }}</option>
        <option value="critical">{{ t('tickets.severity.critical') }}</option>
        <option value="high">{{ t('tickets.severity.high') }}</option>
        <option value="medium">{{ t('tickets.severity.medium') }}</option>
        <option value="low">{{ t('tickets.severity.low') }}</option>
        <option value="informational">{{ t('tickets.severity.informational') }}</option>
      </select>
      <span class="ml-auto text-theme-text-muted">
        {{ t('tickets.total', { count: tickets.length }) }}
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
              :data-test="`ticket-card-${ticket.id}`"
              class="w-full text-left px-3 py-2 hover:bg-theme-bg/60 transition flex items-start justify-between gap-3"
            >
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-semibold text-theme-text truncate">{{ ticket.title }}</span>
                  <span
                    class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px]"
                    :class="statusBadgeClass(ticket.ticketStatus)"
                  >
                    {{ t('tickets.status.' + ticket.ticketStatus) }}
                  </span>
                </div>
                <div class="text-xs text-theme-text-muted truncate">{{ ticket.summary }}</div>
                <div class="mt-1 flex items-center gap-2 text-[10px] text-theme-text-muted">
                  <span class="font-mono">{{ ticket.id }}</span>
                  <span>·</span>
                  <span class="uppercase">{{ t('tickets.severity.' + (ticket.severity || 'informational')) }}</span>
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
          {{ t('tickets.lanes.empty') }}
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
                {{ t('tickets.status.' + selected.ticketStatus) }}
              </span>
              <span class="text-[10px] uppercase text-theme-text-muted">{{ t('tickets.severity.' + (selected.severity || 'informational')) }}</span>
            </div>
          </div>
          <button type="button" @click="selected = null" class="text-theme-text-muted hover:text-theme-text" :aria-label="t('common.close')">
            <X :size="16" />
          </button>
        </div>

        <div class="px-4 py-3 border-b border-theme-border">
          <p class="text-sm text-theme-text whitespace-pre-line">{{ selected.summary }}</p>
          <div class="mt-2 text-xs text-theme-text-muted">
            {{ t('tickets.drawer.openedAt', { date: formatTime(selected.createdAt) }) }}
          </div>
        </div>

        <div
          v-if="selectedDetection"
          data-test="ticket-detection-explanation"
          class="px-4 py-3 border-b border-theme-border bg-sky-500/5 space-y-2"
        >
          <h4 class="text-xs uppercase tracking-wider text-sky-300 flex items-center gap-1">
            <Shield :size="13" />
            {{ t('tickets.drawer.detectionExplanation') }}
          </h4>
          <p v-if="selectedDetection.summary" class="text-xs text-theme-text-muted">
            {{ selectedDetection.summary }}
          </p>
          <dl class="grid grid-cols-3 gap-x-2 gap-y-1 text-xs">
            <dt class="text-theme-text-muted">{{ t('tickets.drawer.ruleId') }}</dt>
            <dd class="col-span-2 font-mono text-theme-text break-all">{{ selectedDetection.ruleId || selected.ruleId }}</dd>
            <dt class="text-theme-text-muted">{{ t('tickets.drawer.eventType') }}</dt>
            <dd class="col-span-2 font-mono text-theme-text break-all">{{ selectedDetection.matchedEventType || '—' }}</dd>
            <dt class="text-theme-text-muted">{{ t('tickets.drawer.observedCount') }}</dt>
            <dd class="col-span-2 font-mono text-theme-text break-all">{{ selectedDetection.observedCount ?? selected.attributes?.count ?? '—' }}</dd>
            <dt v-if="selected.attributes?.attackType" class="text-theme-text-muted">{{ t('tickets.drawer.attackType') }}</dt>
            <dd v-if="selected.attributes?.attackType" class="col-span-2 font-mono text-theme-text break-all">{{ selected.attributes.attackType }}</dd>
          </dl>
          <div v-if="Array.isArray(selectedDetection.thresholds) && selectedDetection.thresholds.length" class="flex flex-wrap gap-1">
            <span
              v-for="threshold in selectedDetection.thresholds"
              :key="thresholdLabel(threshold)"
              class="rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 font-mono text-[10px] text-sky-100"
            >
              {{ thresholdLabel(threshold) }}
            </span>
          </div>
        </div>

        <div
          v-if="isLoadingTriageContext || triageContextError || visibleTriageContext"
          data-test="ticket-triage-context"
          class="px-4 py-3 border-b border-theme-border bg-emerald-500/5 space-y-3"
        >
          <div class="flex items-center justify-between gap-2">
            <h4 class="text-xs uppercase tracking-wider text-emerald-300 flex items-center gap-1">
              <Shield :size="13" />
              {{ t('tickets.drawer.triageContext') }}
            </h4>
            <span
              v-if="visibleTriageContext"
              class="rounded border px-1.5 py-0.5 text-[10px] uppercase"
              :class="confidenceClass(visibleTriageContext.confidence)"
            >
              {{ visibleTriageContext.confidence }}
            </span>
          </div>
          <div v-if="isLoadingTriageContext" class="text-xs text-theme-text-muted flex items-center gap-1">
            <Loader2 :size="12" class="animate-spin" />
            {{ t('tickets.drawer.loadingTriageContext') }}
          </div>
          <div v-else-if="triageContextError" class="text-xs text-red-300 flex items-start gap-1">
            <AlertCircle :size="13" class="mt-0.5" />
            {{ triageContextError }}
          </div>
          <div v-else-if="visibleTriageContext" class="space-y-3">
            <dl class="grid grid-cols-3 gap-x-2 gap-y-1 text-xs">
              <dt class="text-theme-text-muted">{{ t('tickets.drawer.alertFamily') }}</dt>
              <dd class="col-span-2 font-mono text-theme-text break-all">{{ visibleTriageContext.alertFamily }}</dd>
              <dt class="text-theme-text-muted">{{ t('tickets.drawer.attackType') }}</dt>
              <dd class="col-span-2 font-mono text-theme-text break-all">{{ visibleTriageContext.attackType }}</dd>
              <dt class="text-theme-text-muted">{{ t('tickets.drawer.recommended') }}</dt>
              <dd class="col-span-2 text-theme-text">
                {{ visibleTriageContext.recommendedTriageLevel }} · {{ t('tickets.status.' + visibleTriageContext.recommendedTicketStatus) }}
              </dd>
            </dl>

            <div v-if="visibleTriageContext.mitreMappings?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.drawer.mitreMappings') }}</div>
              <div class="mt-1 space-y-1">
                <div
                  v-for="mapping in visibleTriageContext.mitreMappings"
                  :key="`${mapping.tacticId}-${mapping.techniqueId}`"
                  class="rounded border border-emerald-500/30 bg-emerald-950/20 p-2 text-xs"
                >
                  <div class="flex flex-wrap items-center gap-1">
                    <span class="font-mono text-emerald-200">{{ mapping.techniqueId }}</span>
                    <span class="text-theme-text">{{ mapping.techniqueName }}</span>
                    <span class="text-theme-text-muted">·</span>
                    <span class="font-mono text-theme-text-muted">{{ mapping.tacticId }}</span>
                    <span class="text-theme-text-muted">{{ mapping.tacticName }}</span>
                  </div>
                  <p class="mt-1 text-[11px] text-theme-text-muted leading-relaxed">{{ mapping.reason }}</p>
                </div>
              </div>
            </div>

            <div v-if="visibleTriageContext.evidence?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.drawer.evidence') }}</div>
              <ul class="mt-1 space-y-1">
                <li
                  v-for="item in visibleTriageContext.evidence"
                  :key="item.id"
                  class="rounded border border-theme-border/70 bg-theme-bg/40 p-2 text-xs"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="font-semibold text-theme-text">{{ item.label }}</span>
                    <span class="font-mono text-[10px] text-theme-text-muted">{{ item.source }}</span>
                  </div>
                  <div class="mt-1 font-mono text-theme-text break-all">{{ formatTriageValue(item.value) }}</div>
                  <div v-if="item.threshold" class="mt-1 text-[10px] text-theme-text-muted">
                    {{ t('tickets.drawer.threshold') }}: {{ formatTriageValue(item.threshold) }}
                  </div>
                </li>
              </ul>
            </div>

            <div v-if="visibleTriageContext.responseCandidates?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.drawer.recommendedResponse') }}</div>
              <div class="mt-1 space-y-1">
                <div
                  v-for="candidate in visibleTriageContext.responseCandidates"
                  :key="candidate.id"
                  class="rounded border p-2 text-xs"
                  :class="candidateClass(candidate.availableNow)"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="font-semibold">{{ candidate.label }}</span>
                    <span class="font-mono text-[10px]">{{ candidate.id }}</span>
                  </div>
                  <p class="mt-1 leading-relaxed opacity-80">{{ candidate.reason }}</p>
                  <div class="mt-1 flex flex-wrap gap-1 text-[10px]">
                    <span class="rounded border border-current/30 px-1.5 py-0.5">
                      {{ candidate.availableNow ? t('tickets.drawer.available') : t('tickets.drawer.unavailable') }}
                    </span>
                    <span v-if="candidate.requiresApproval" class="rounded border border-current/30 px-1.5 py-0.5">
                      {{ t('tickets.ai.requiresApproval') }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="visibleTriageContext.playbookTemplates?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.drawer.playbookTemplates') }}</div>
              <div class="mt-1 space-y-1">
                <div
                  v-for="template in visibleTriageContext.playbookTemplates"
                  :key="template.templateId"
                  class="rounded border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs text-emerald-100"
                >
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div class="font-semibold text-theme-text">{{ template.label }}</div>
                      <div class="font-mono text-[10px] text-theme-text-muted break-all">{{ template.templateId }}</div>
                      <p class="mt-1 text-[11px] text-theme-text-muted leading-relaxed">{{ template.reason }}</p>
                    </div>
                    <button
                      type="button"
                      :data-test="`ticket-instantiate-template-${template.templateId}`"
                      :disabled="instantiatingTemplateId === template.templateId"
                      @click="runInstantiateTemplate(selected!, template.templateId)"
                      class="shrink-0 inline-flex items-center gap-1 rounded border border-emerald-500/50 bg-emerald-500/15 px-2 py-1 text-[10px] font-semibold text-emerald-100 hover:bg-emerald-500/25 disabled:opacity-50"
                    >
                      <Loader2 v-if="instantiatingTemplateId === template.templateId" :size="11" class="animate-spin" />
                      <Workflow v-else :size="11" />
                      {{ t('tickets.drawer.instantiateTemplate') }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="visibleTriageContext.missingData?.length" class="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-100">
              <div class="font-semibold">{{ t('tickets.drawer.missingData') }}</div>
              <ul class="mt-1 space-y-1">
                <li v-for="item in visibleTriageContext.missingData" :key="item.id">
                  {{ item.label }}: {{ item.reason }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="px-4 py-3 border-b border-theme-border space-y-3">
          <div>
            <label class="block text-xs uppercase tracking-wider text-theme-text-muted mb-1">{{ t('tickets.drawer.triageLevel') }}</label>
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
            <label class="block text-xs uppercase tracking-wider text-theme-text-muted mb-1">{{ t('tickets.drawer.ticketStatus') }}</label>
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
            {{ t('common.saving') }}
          </div>
        </div>

        <!-- Threat Intel -->
        <div class="px-4 py-3 border-b border-theme-border bg-sky-500/5 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <h4 class="text-xs uppercase tracking-wider text-sky-300 flex items-center gap-1">
              <Shield :size="13" />
              {{ t('tickets.threatIntel.header') }}
            </h4>
            <button
              type="button"
              data-test="ticket-threat-intel-enrich"
              :disabled="isEnrichingThreatIntel"
              @click="runThreatIntel(selected!)"
              class="text-xs px-2 py-1 rounded border border-sky-500/40 bg-sky-500/10 text-sky-200 hover:bg-sky-500/20 disabled:opacity-50 flex items-center gap-1"
            >
              <Loader2 v-if="isEnrichingThreatIntel" :size="11" class="animate-spin" />
              <Shield v-else :size="11" />
              {{ t('tickets.threatIntel.enrich') }}
            </button>
          </div>

          <div v-if="threatIntelError" class="text-xs text-red-300 flex items-start gap-1">
            <AlertCircle :size="13" class="mt-0.5" />
            {{ threatIntelError }}
          </div>

          <div v-if="threatIntel" data-test="ticket-threat-intel-result" class="space-y-2">
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span class="rounded border border-sky-500/40 bg-sky-500/10 px-1.5 py-0.5 font-mono text-sky-200">
                {{ threatIntel.provider }}
              </span>
              <span
                v-if="!threatIntel.providerConfigured"
                class="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-amber-200"
              >
                {{ t('tickets.threatIntel.notConfigured') }}
              </span>
              <span class="text-theme-text-muted">
                {{ t('tickets.threatIntel.indicatorCount', { count: threatIntel.summary.total }) }}
              </span>
            </div>
            <div class="grid grid-cols-4 gap-1 text-[10px]">
              <span class="rounded border border-red-500/30 bg-red-500/10 px-1.5 py-1 text-red-200">
                {{ t('tickets.threatIntel.malicious', { count: threatIntel.summary.malicious }) }}
              </span>
              <span class="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-1 text-amber-200">
                {{ t('tickets.threatIntel.suspicious', { count: threatIntel.summary.suspicious }) }}
              </span>
              <span class="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-1 text-emerald-200">
                {{ t('tickets.threatIntel.clean', { count: threatIntel.summary.clean }) }}
              </span>
              <span class="rounded border border-theme-border bg-theme-bg/60 px-1.5 py-1 text-theme-text-muted">
                {{ t('tickets.threatIntel.unknown', { count: threatIntel.summary.unknown }) }}
              </span>
            </div>
            <div v-if="threatIntelFlagged.length" class="space-y-1">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">
                {{ t('tickets.threatIntel.flagged') }}
              </div>
              <div class="space-y-1">
                <a
                  v-for="item in threatIntelFlagged"
                  :key="`${item.type}-${item.value}`"
                  :href="item.referenceUrl || undefined"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="block rounded border px-2 py-1 text-[11px] hover:brightness-110"
                  :class="threatIntelVerdictClass(item.verdict)"
                >
                  <span class="font-mono break-all">{{ item.type }} · {{ item.value }}</span>
                  <span class="ml-1">· {{ item.verdict }} · {{ item.score }}</span>
                </a>
              </div>
            </div>
            <p v-else class="text-xs text-theme-text-muted italic">
              {{ t('tickets.threatIntel.noFlagged') }}
            </p>
          </div>
          <p v-else class="text-xs text-theme-text-muted italic">
            {{ t('tickets.threatIntel.hint') }}
          </p>
        </div>

        <!-- FortiWeb Response -->
        <div class="px-4 py-3 border-b border-theme-border bg-emerald-500/5 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <h4 class="text-xs uppercase tracking-wider text-emerald-300 flex items-center gap-1">
              <Shield :size="13" />
              {{ t('tickets.fortiweb.title') }}
            </h4>
            <span
              v-if="fortiwebBlockResult?.status === 'active'"
              class="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-200"
            >
              {{ t('tickets.fortiweb.active') }}
            </span>
            <span
              v-else-if="fortiwebBlockResult?.status === 'removed'"
              class="rounded border border-theme-border bg-theme-bg/60 px-1.5 py-0.5 text-[10px] text-theme-text-muted"
            >
              {{ t('tickets.fortiweb.removed') }}
            </span>
          </div>

          <div v-if="fortiwebIntegrations.length" class="grid grid-cols-2 gap-2 text-xs">
            <label class="col-span-2 flex flex-col gap-1">
              <span class="text-theme-text-muted">{{ t('tickets.fortiweb.integrationId') }}</span>
              <select
                v-model="fortiwebBlockForm.integrationId"
                class="rounded border border-theme-border bg-theme-bg px-2 py-1 text-theme-text outline-none focus:border-emerald-400"
              >
                <option
                  v-for="integration in fortiwebIntegrations"
                  :key="integration.id"
                  :value="integration.id"
                >
                  {{ integration.name || integration.id }}
                </option>
              </select>
            </label>
            <label class="col-span-2 flex flex-col gap-1">
              <span class="text-theme-text-muted">{{ t('tickets.fortiweb.sourceIp') }}</span>
              <input
                v-model="fortiwebBlockForm.sourceIp"
                class="rounded border border-theme-border bg-theme-bg px-2 py-1 font-mono text-theme-text outline-none focus:border-emerald-400"
              >
            </label>
          </div>
          <div v-else class="text-xs text-theme-text-muted">
            {{ t('tickets.fortiweb.noIntegration') }}
          </div>

          <div v-if="fortiwebBlockError" class="text-xs text-red-300 flex items-start gap-1">
            <AlertCircle :size="13" class="mt-0.5" />
            {{ fortiwebBlockError }}
          </div>

          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              data-test="ticket-create-fortiweb-block-review"
              :disabled="!canCreateFortiwebBlockReview || isCreatingFortiwebBlockReview || !fortiwebIntegrations.length"
              @click="runCreateFortiwebBlockReview(selected!)"
              class="inline-flex items-center gap-1 rounded border border-emerald-500/50 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-100 hover:bg-emerald-500/25 disabled:opacity-50"
            >
              <Loader2 v-if="isCreatingFortiwebBlockReview" :size="12" class="animate-spin" />
              <CheckCircle2 v-else :size="12" />
              {{ t('tickets.fortiweb.createReview') }}
            </button>
            <button
              type="button"
              data-test="ticket-apply-fortiweb-block"
              :disabled="!canApplyFortiwebBlock || isApplyingFortiwebBlock"
              @click="runApplyFortiwebBlock"
              class="inline-flex items-center gap-1 rounded border border-amber-500/50 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-100 hover:bg-amber-500/25 disabled:opacity-50"
            >
              <Loader2 v-if="isApplyingFortiwebBlock" :size="12" class="animate-spin" />
              <Shield v-else :size="12" />
              {{ t('tickets.fortiweb.apply') }}
            </button>
            <button
              type="button"
              data-test="ticket-remove-fortiweb-block"
              :disabled="!canRemoveFortiwebBlock || isRemovingFortiwebBlock"
              @click="runRemoveFortiwebBlock"
              class="inline-flex items-center gap-1 rounded border border-theme-border bg-theme-bg/60 px-3 py-1.5 text-xs font-semibold text-theme-text hover:bg-theme-border disabled:opacity-50"
            >
              <Loader2 v-if="isRemovingFortiwebBlock" :size="12" class="animate-spin" />
              <X v-else :size="12" />
              {{ t('tickets.fortiweb.remove') }}
            </button>
          </div>

          <div v-if="fortiwebBlockReview" class="rounded border border-theme-border bg-theme-bg/60 p-2 text-xs">
            <div class="font-semibold text-theme-text">{{ t('tickets.fortiweb.proposedChanges') }}</div>
            <ul class="mt-1 space-y-1 text-theme-text-muted">
              <li
                v-for="change in fortiwebBlockReview.proposedChanges"
                :key="`${change.operation}-${change.target}-${change.sourceIp || ''}`"
              >
                {{ change.operation }} · {{ change.target }}
              </li>
            </ul>
          </div>
        </div>

        <!-- AI Assistant -->
        <div class="px-4 py-3 border-b border-theme-border bg-fuchsia-500/5">
          <div class="flex items-center justify-between mb-2">
            <h4 class="text-xs uppercase tracking-wider text-fuchsia-300 flex items-center gap-1">
              <Sparkles :size="13" />
              {{ t('tickets.ai.header') }}
            </h4>
            <div class="flex gap-2">
              <button
                type="button"
                :disabled="isAnalyzing"
                @click="runAnalysis(selected!)"
                data-test="ticket-ai-analyze"
                class="text-xs px-2 py-1 rounded border border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200 hover:bg-fuchsia-500/20 disabled:opacity-50 flex items-center gap-1"
              >
                <Loader2 v-if="isAnalyzing" :size="11" class="animate-spin" />
                <Sparkles v-else :size="11" />
                {{ t('tickets.ai.analyze') }}
              </button>
              <button
                type="button"
                data-test="ticket-ai-containment"
                :disabled="isContaining"
                @click="runContainment(selected!)"
                class="text-xs px-2 py-1 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 flex items-center gap-1"
              >
                <Loader2 v-if="isContaining" :size="11" class="animate-spin" />
                <Shield v-else :size="11" />
                {{ t('tickets.ai.suggestContainment') }}
              </button>
            </div>
          </div>

          <div v-if="aiError" class="text-xs text-red-300 flex items-start gap-1 mb-2">
            <AlertCircle :size="13" class="mt-0.5" />
            {{ aiError }}
          </div>

          <div v-if="aiAnalysis" data-test="ticket-ai-analysis" class="mt-2 p-3 rounded-lg border border-fuchsia-500/30 bg-fuchsia-950/30 space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-sm font-semibold text-fuchsia-100">{{ aiAnalysis.headline }}</span>
              <div class="flex items-center gap-1">
                <span
                  v-if="aiAnalysisBadge"
                  class="rounded border px-1.5 py-0.5 text-[10px]"
                  :class="sourceBadgeClass(aiAnalysisBadge)"
                >
                  {{ aiAnalysisBadge.label }}
                </span>
                <span class="text-xs font-mono px-1.5 py-0.5 rounded border border-fuchsia-500/40 text-fuchsia-200">
                  {{ t('tickets.ai.riskScore', { score: aiAnalysis.riskScore }) }}
                </span>
              </div>
            </div>
            <p class="text-xs text-theme-text whitespace-pre-line leading-relaxed">{{ aiAnalysis.summary }}</p>
            <div class="text-xs">
              <span class="text-theme-text-muted">{{ t('tickets.ai.suggestedLabel') }}</span>
              <span class="ml-1 text-fuchsia-200 font-semibold">{{ aiAnalysis.suggestedTriage }} · {{ t('tickets.status.' + aiAnalysis.suggestedTicketStatus) }}</span>
              <button
                type="button"
                :disabled="isSavingPatch"
                @click="applySuggestedAnalysis(selected!)"
                class="ml-2 px-2 py-0.5 rounded border border-fuchsia-500/40 text-fuchsia-200 hover:bg-fuchsia-500/15 text-[10px] disabled:opacity-50"
              >
                {{ t('common.apply') }}
              </button>
            </div>
            <!-- CVSS v3.1 base score + vector + justification -->
            <div
              v-if="aiAnalysis.cvss && (aiAnalysis.cvss.score !== null || aiAnalysis.cvss.vector)"
              class="rounded border border-fuchsia-500/30 bg-fuchsia-950/40 p-2 space-y-1"
            >
              <div class="flex flex-wrap items-center gap-2 text-[11px]">
                <span class="uppercase tracking-wider text-theme-text-muted">{{ t('tickets.ai.cvssLabel') }}</span>
                <span
                  v-if="aiAnalysis.cvss.score !== null"
                  class="font-mono font-semibold px-1.5 py-0.5 rounded"
                  :class="cvssBadgeClass(aiAnalysis.cvss.severity)"
                >
                  {{ aiAnalysis.cvss.score.toFixed(1) }} · {{ aiAnalysis.cvss.severity || '—' }}
                </span>
                <a
                  v-if="aiAnalysis.cvss.vector"
                  :href="cvssCalcUrl(aiAnalysis.cvss.vector)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="font-mono text-[10px] text-fuchsia-300 hover:text-fuchsia-200 underline underline-offset-2 break-all"
                >
                  {{ aiAnalysis.cvss.vector }}
                </a>
              </div>
              <p
                v-if="aiAnalysis.cvss.justification"
                class="text-[11px] text-theme-text leading-relaxed"
              >{{ aiAnalysis.cvss.justification }}</p>
            </div>
            <!-- MITRE ATT&CK techniques cited by the model -->
            <div v-if="aiAnalysis.mitreTechniques?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.ai.mitreLabel') }}</div>
              <div class="flex flex-wrap gap-1 mt-1">
                <a
                  v-for="technique in aiAnalysis.mitreTechniques"
                  :key="technique.id"
                  :href="technique.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200 hover:bg-fuchsia-500/20"
                  :title="technique.name"
                >
                  {{ technique.id }} · {{ technique.name }}
                </a>
              </div>
            </div>
            <div v-if="aiAnalysis.indicatorsOfCompromise?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.ai.iocsLabel') }}</div>
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
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.ai.nextStepsLabel') }}</div>
              <ol class="list-decimal list-inside text-xs text-theme-text space-y-0.5 mt-1">
                <li v-for="(step, i) in aiAnalysis.nextSteps" :key="i">{{ step }}</li>
              </ol>
            </div>
            <div v-if="aiAnalysis.references?.length">
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.ai.referencesLabel') }}</div>
              <ul class="text-[11px] space-y-0.5 mt-1">
                <li v-for="ref in aiAnalysis.references" :key="ref" class="break-all">
                  <a
                    :href="ref"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-fuchsia-300 hover:text-fuchsia-200 underline underline-offset-2"
                  >
                    {{ ref }}
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div v-if="aiContainment" class="mt-3 p-3 rounded-lg border border-emerald-500/30 bg-emerald-950/30 space-y-2">
            <div class="text-sm font-semibold text-emerald-100 flex items-center gap-1">
              <Shield :size="13" />
              {{ t('tickets.ai.containmentPlanLabel') }}
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
                    {{ t('tickets.severity.' + step.severity) }}
                  </span>
                </div>
                <p class="text-theme-text-muted leading-relaxed">{{ step.description }}</p>
                <div class="mt-1 flex items-center gap-2 text-[10px] text-theme-text-muted">
                  <span class="font-mono">{{ step.playbookNodeType }}</span>
                  <span v-if="step.requiresApproval" class="text-amber-300">{{ t('tickets.ai.requiresApproval') }}</span>
                  <span v-else class="text-emerald-300">{{ t('tickets.ai.autoSafe') }}</span>
                </div>
              </li>
            </ol>
            <div class="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                data-test="ticket-draft-playbook"
                :disabled="isDrafting"
                @click="runDraftPlaybook(selected!)"
                class="text-xs px-2 py-1 rounded border border-emerald-500/40 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25 disabled:opacity-50 flex items-center gap-1"
              >
                <Loader2 v-if="isDrafting" :size="11" class="animate-spin" />
                <Workflow v-else :size="11" />
                {{ t('tickets.ai.draftPlaybook') }}
              </button>
            </div>
            <p v-if="!playbookDraft" class="text-[10px] text-theme-text-muted italic mt-2">
              {{ t('tickets.ai.draftHint') }}
            </p>
          </div>

          <div v-if="playbookError" class="mt-3 p-2 rounded border border-red-500/40 bg-red-500/10 text-xs text-red-300 flex items-start gap-1">
            <AlertCircle :size="13" class="mt-0.5" />
            {{ playbookError }}
          </div>

          <div v-if="playbookDraft" data-test="ticket-draft-playbook-result" class="mt-3 p-3 rounded-lg border border-emerald-500/30 bg-emerald-950/40 space-y-2">
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-semibold text-emerald-100 flex items-center gap-1">
                <Workflow :size="13" />
                {{ t('tickets.ai.draftPlaybook') }}
              </span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded border border-emerald-500/40 text-emerald-200">
                {{ playbookDraft.playbook.id }}
              </span>
            </div>
            <div class="text-xs text-theme-text-muted">{{ playbookDraft.playbook.name }}</div>

            <div>
              <div class="text-[10px] uppercase tracking-wider text-theme-text-muted">{{ t('tickets.ai.simulationLabel') }}</div>
              <div class="text-xs flex items-center gap-2">
                <span :class="playbookDraft.simulation.valid ? 'text-emerald-300' : 'text-red-300'">
                  {{ playbookDraft.simulation.valid ? t('tickets.ai.simulationValid') : t('tickets.ai.simulationInvalid') }}
                </span>
                <span class="text-theme-text-muted">·</span>
                <span class="text-theme-text">{{ t('tickets.ai.stepsCount', { count: playbookDraft.simulation.steps?.length || 0 }) }}</span>
              </div>
              <ol v-if="playbookDraft.simulation.steps?.length" class="mt-1 list-decimal list-inside text-[11px] text-theme-text space-y-0.5">
                <li v-for="step in playbookDraft.simulation.steps" :key="step.nodeId">
                  <span class="font-mono">{{ step.nodeType }}</span>
                  <span class="text-theme-text-muted ml-1">→ {{ step.status }}</span>
                  <span v-if="step.sensitive" class="ml-1 text-[10px] text-amber-300">{{ t('tickets.ai.sensitive') }}</span>
                </li>
              </ol>
            </div>

            <div class="flex gap-2 pt-2 border-t border-emerald-500/20">
              <button
                type="button"
                data-test="ticket-apply-playbook"
                :disabled="isApplying || !!applyResult"
                @click="runApplyPlaybook(selected!)"
                class="text-xs px-3 py-1.5 rounded border border-emerald-500/50 bg-emerald-500/20 text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-50 flex items-center gap-1 font-semibold"
              >
                <Loader2 v-if="isApplying" :size="12" class="animate-spin" />
                <Play v-else :size="12" />
                {{ t('tickets.ai.applyDryRun') }}
              </button>
              <p class="text-[10px] text-theme-text-muted self-center">
                {{ t('tickets.ai.safetyNote') }}
              </p>
            </div>
          </div>

          <div v-if="applyResult" data-test="ticket-containment-result" class="mt-3 p-3 rounded-lg border border-emerald-400/50 bg-emerald-500/15 text-xs space-y-1">
            <div class="font-semibold text-emerald-100 flex items-center gap-1">
              <CheckCircle2 :size="13" />
              {{ applyResult.ticketStatus === 'contained' ? t('tickets.ai.threatContained') : t('tickets.ai.containmentPaused') }}
            </div>
            <div class="text-theme-text-muted">
              {{ t('tickets.ai.runStatus', { id: applyResult.run.id, status: applyResult.run.status }) }}
            </div>
            <button
              v-if="applyResult.run.status === 'waiting_approval'"
              type="button"
              data-test="ticket-approve-playbook"
              :disabled="isApprovingRun"
              @click="runApprovePlaybook(selected!)"
              class="mt-2 text-xs px-3 py-1.5 rounded border border-amber-500/50 bg-amber-500/20 text-amber-100 hover:bg-amber-500/30 disabled:opacity-50 flex items-center gap-1 font-semibold"
            >
              <Loader2 v-if="isApprovingRun" :size="12" class="animate-spin" />
              <CheckCircle2 v-else :size="12" />
              {{ t('tickets.ai.approveRun') }}
            </button>
          </div>

          <div
            v-if="policyReviewRequired"
            data-test="ticket-policy-review"
            class="mt-3 rounded-lg border border-sky-500/40 bg-sky-500/10 p-3 text-xs"
          >
            <div class="font-semibold text-sky-100 flex items-center gap-1">
              <Shield :size="13" />
              {{ t('tickets.policy.title') }}
            </div>
            <p class="mt-1 text-theme-text-muted leading-relaxed">
              {{ t('tickets.policy.subtitle') }}
            </p>

            <div class="mt-3 grid grid-cols-2 gap-2">
              <label class="col-span-2 flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.integrationId') }}</span>
                <input
                  v-model="policyForm.integrationId"
                  data-test="ticket-policy-integration"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 text-theme-text outline-none focus:border-sky-400"
                >
              </label>
              <label class="flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.sourceInterface') }}</span>
                <input
                  v-model="policyForm.sourceInterface"
                  data-test="ticket-policy-source-interface"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 text-theme-text outline-none focus:border-sky-400"
                >
              </label>
              <label class="flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.destinationInterface') }}</span>
                <input
                  v-model="policyForm.destinationInterface"
                  data-test="ticket-policy-destination-interface"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 text-theme-text outline-none focus:border-sky-400"
                >
              </label>
              <label class="flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.sourceIp') }}</span>
                <input
                  v-model="policyForm.sourceIp"
                  data-test="ticket-policy-source-ip"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 font-mono text-theme-text outline-none focus:border-sky-400"
                >
              </label>
              <label class="flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.destinationIp') }}</span>
                <input
                  v-model="policyForm.destinationIp"
                  data-test="ticket-policy-destination-ip"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 font-mono text-theme-text outline-none focus:border-sky-400"
                >
              </label>
              <label class="col-span-2 flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.scope') }}</span>
                <select
                  v-model="policyForm.scope"
                  data-test="ticket-policy-scope"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 text-theme-text outline-none focus:border-sky-400"
                >
                  <option v-for="option in policyScopeOptions" :key="option.value" :value="option.value">
                    {{ t(option.labelKey) }}
                  </option>
                </select>
              </label>
              <label class="flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.service') }}</span>
                <input
                  v-model="policyForm.service"
                  data-test="ticket-policy-service"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 text-theme-text outline-none focus:border-sky-400"
                >
              </label>
              <label class="flex flex-col gap-1">
                <span class="text-theme-text-muted">{{ t('tickets.policy.durationMinutes') }}</span>
                <input
                  v-model.number="policyForm.durationMinutes"
                  data-test="ticket-policy-duration"
                  min="1"
                  type="number"
                  class="rounded border border-theme-border bg-theme-bg px-2 py-1 text-theme-text outline-none focus:border-sky-400"
                >
              </label>
            </div>

            <div class="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                data-test="ticket-create-policy-review"
                :disabled="!canCreatePolicyReview || isCreatingPolicyReview"
                @click="runCreatePolicyReview"
                class="inline-flex items-center gap-1 rounded border border-sky-500/50 bg-sky-500/15 px-3 py-1.5 text-xs font-semibold text-sky-100 hover:bg-sky-500/25 disabled:opacity-50"
              >
                <Loader2 v-if="isCreatingPolicyReview" :size="12" class="animate-spin" />
                <CheckCircle2 v-else :size="12" />
                {{ t('tickets.policy.createReview') }}
              </button>
              <button
                type="button"
                data-test="ticket-apply-policy-review"
                :disabled="!canApplyPolicyReview || isApplyingPolicyReview"
                @click="runApplyPolicyReview(selected!)"
                class="inline-flex items-center gap-1 rounded border border-emerald-500/50 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-100 hover:bg-emerald-500/25 disabled:opacity-50"
              >
                <Loader2 v-if="isApplyingPolicyReview" :size="12" class="animate-spin" />
                <Play v-else :size="12" />
                {{ t('tickets.policy.apply') }}
              </button>
            </div>

            <div v-if="policyReview" class="mt-3 rounded border border-theme-border bg-theme-bg/60 p-2">
              <div class="font-semibold text-theme-text">
                {{ t('tickets.policy.proposedPolicy') }}: {{ policyReview.proposed_policy_name }}
              </div>
              <div class="mt-1 text-theme-text-muted">
                {{ t('tickets.policy.placement') }}: {{ policyReview.placement }}
              </div>
              <ul class="mt-2 space-y-1 text-theme-text">
                <li v-for="change in policyReview.changes" :key="`${change.object_type}-${change.name}`">
                  {{ change.operation }} · {{ change.object_type }} · {{ change.name }}
                </li>
              </ul>
              <div v-if="policyReview.warnings.length" class="mt-2 text-amber-300">
                {{ policyReview.warnings.join(' ') }}
              </div>
            </div>

            <div v-if="policyApplyResult" class="mt-2 font-semibold text-emerald-200">
              {{ t('tickets.policy.applied') }}
            </div>
          </div>

          <p v-if="!aiAnalysis && !aiContainment && !aiError && !isAnalyzing && !isContaining" class="text-xs text-theme-text-muted italic">
            {{ t('tickets.ai.hint') }}
          </p>
        </div>

        <!-- Entities -->
        <div v-if="selected.entities && Object.keys(selected.entities).length" class="px-4 py-3 border-b border-theme-border">
          <h4 class="text-xs uppercase tracking-wider text-theme-text-muted mb-2">{{ t('tickets.drawer.entities') }}</h4>
          <dl class="text-xs grid grid-cols-3 gap-x-2 gap-y-1">
            <template v-for="(value, key) in selected.entities" :key="key">
              <dt class="col-span-1 text-theme-text-muted">{{ key }}</dt>
              <dd class="col-span-2 text-theme-text font-mono break-all">{{ value }}</dd>
            </template>
          </dl>
        </div>

        <!-- Timeline -->
        <div class="px-4 py-3">
          <h4 class="text-xs uppercase tracking-wider text-theme-text-muted mb-2">{{ t('tickets.drawer.timeline') }}</h4>
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
