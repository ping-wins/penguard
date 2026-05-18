<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  CheckCircle2,
  FileDiff,
  FileText,
  Pencil,
  Plus,
  RefreshCcw,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
  Trash2,
  X,
} from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import { usePoliciesStore } from '../../../stores/usePoliciesStore'
import type {
  PolicyAction,
  PolicyOwnership,
  PolicyProviderSummary,
  PolicyProviderType,
  PolicyReview,
  PolicyRow,
} from '../../../services/policiesClient'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

void props.data
void props.integrationId

const { t } = useI18n()
const policiesStore = usePoliciesStore()
const { providers, policies, pendingReview, lastApplyResult, isLoading, error } = storeToRefs(policiesStore)

type FilterState = {
  providerType: '' | PolicyProviderType
  integrationId: ''
  ownership: '' | PolicyOwnership
  status: ''
  kind: ''
  q: ''
}

type FortiGatePolicyForm = {
  name: string
  srcintf: string
  dstintf: string
  srcaddr: string
  dstaddr: string
  service: string
  action: 'accept' | 'deny'
  schedule: string
  logtraffic: 'all' | 'utm' | 'disable'
  status: 'enable' | 'disable'
}

type FortiWebPolicyForm = {
  sourceIp: string
  incidentId: string
  reason: string
}

const filters = ref<FilterState>({
  providerType: '',
  integrationId: '',
  ownership: '',
  status: '',
  kind: '',
  q: '',
})
const selectedPolicyId = ref<string | null>(null)
const selectedAction = ref<PolicyAction | null>(null)
const selectedProviderType = ref<PolicyProviderType>('fortigate')
const selectedIntegrationId = ref('')
const payloadText = ref('{}')
const showAdvancedPayload = ref(false)
const fortigatePolicyForm = ref<FortiGatePolicyForm>(defaultFortiGatePolicyForm())
const fortiwebPolicyForm = ref<FortiWebPolicyForm>(defaultFortiWebPolicyForm())
const formError = ref('')
const isReviewing = ref(false)
const isApplying = ref(false)

const selectedPolicy = computed(() => policies.value.find(policy => policy.id === selectedPolicyId.value) ?? null)
const selectedProvider = computed(() =>
  providers.value.find(provider => (
    provider.providerType === selectedProviderType.value
    && provider.integrationId === selectedIntegrationId.value
  )) ?? providers.value[0] ?? null,
)

const providerOptions = computed(() => providers.value)
const statusOptions = computed(() => uniqueValues(policies.value.map(policy => policy.status)))

const filteredPolicies = computed(() => {
  const q = filters.value.q.trim().toLowerCase()
  return policies.value.filter((policy) => {
    if (filters.value.providerType && policy.providerType !== filters.value.providerType) return false
    if (filters.value.integrationId && policy.integrationId !== filters.value.integrationId) return false
    if (filters.value.ownership && policy.ownership !== filters.value.ownership) return false
    if (filters.value.status && policy.status !== filters.value.status) return false
    if (filters.value.kind && policy.kind !== filters.value.kind) return false
    if (!q) return true
    return [
      policy.name,
      policy.nativeId,
      policy.kind,
      policy.summary,
      policy.providerType,
      policy.integrationId,
      policy.action ?? '',
    ].some(value => value.toLowerCase().includes(q))
  })
})

const stats = computed(() => {
  const external = policies.value.filter(policy => policy.ownership === 'external').length
  const mutable = policies.value.filter(policy => policy.isMutable).length
  return {
    providers: providers.value.length,
    policies: policies.value.length,
    external,
    mutable,
  }
})

const reviewDiff = computed(() => pendingReview.value?.diff ?? [])
const reviewWarnings = computed(() => pendingReview.value?.warnings ?? [])
const effectiveProviderType = computed<PolicyProviderType>(() => selectedPolicy.value?.providerType ?? selectedProviderType.value)
const supportsStructuredPolicyForm = computed(() =>
  selectedAction.value === 'create'
  && (effectiveProviderType.value === 'fortigate' || effectiveProviderType.value === 'fortiweb'),
)
const usesStructuredPolicyForm = computed(() => supportsStructuredPolicyForm.value && !showAdvancedPayload.value)

onMounted(async () => {
  await refreshAll()
})

watch(providers, (items) => {
  if (selectedIntegrationId.value || !items.length) return
  selectedProviderType.value = items[0].providerType
  selectedIntegrationId.value = items[0].integrationId
}, { immediate: true })

watch(selectedIntegrationId, (integrationId) => {
  const provider = providers.value.find(item => item.integrationId === integrationId)
  if (provider) selectedProviderType.value = provider.providerType
})

watch([selectedProviderType, selectedIntegrationId], () => {
  if (selectedAction.value !== 'create') return
  resetCreatePayload(selectedProviderType.value)
})

async function refreshAll() {
  await policiesStore.loadProviders()
  await policiesStore.loadPolicies({})
}

function uniqueValues(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b))
}

function providerName(policy: PolicyRow): string {
  const provider = providers.value.find(item => (
    item.providerType === policy.providerType && item.integrationId === policy.integrationId
  ))
  return provider?.name ?? policy.integrationId
}

function providerLabel(providerType: string): string {
  if (providerType === 'fortigate') return 'FortiGate'
  if (providerType === 'fortiweb') return 'FortiWeb'
  return providerType
}

function ownershipLabel(ownership: string): string {
  const key = `widgets.policyManager.ownership.${ownership}`
  return t(key)
}

function statusLabel(status: string): string {
  const normalized = status.toLowerCase()
  if (normalized === 'enabled') return t('widgets.policyManager.status.enabled')
  if (normalized === 'disabled') return t('widgets.policyManager.status.disabled')
  return status || t('widgets.policyManager.unknown')
}

function actionLabel(action: PolicyAction): string {
  return t(`widgets.policyManager.actions.${action}`)
}

function actionTitle(action: PolicyAction): string {
  return t(`widgets.policyManager.actionTitles.${action}`)
}

function statusTone(status: string): string {
  const normalized = status.toLowerCase()
  if (normalized === 'enabled') return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
  if (normalized === 'disabled') return 'border-slate-400/30 bg-slate-500/10 text-slate-200'
  return 'border-amber-400/30 bg-amber-500/10 text-amber-100'
}

function ownershipTone(ownership: string): string {
  if (ownership === 'fortidashboard') return 'border-cyan-400/30 bg-cyan-500/10 text-cyan-200'
  if (ownership === 'external') return 'border-amber-400/30 bg-amber-500/10 text-amber-100'
  return 'border-theme-border bg-theme-bg/70 text-theme-text-muted'
}

function actionIcon(action: PolicyAction) {
  if (action === 'edit') return Pencil
  if (action === 'enable') return ToggleRight
  if (action === 'disable') return ToggleLeft
  if (action === 'delete') return Trash2
  return Plus
}

function selectableActions(policy: PolicyRow): PolicyAction[] {
  return policy.supports.filter((action): action is PolicyAction =>
    ['edit', 'enable', 'disable', 'delete'].includes(action),
  )
}

function selectPolicy(policy: PolicyRow) {
  selectedPolicyId.value = policy.id
  selectedProviderType.value = policy.providerType
  selectedIntegrationId.value = policy.integrationId
}

function beginCreate(provider?: PolicyProviderSummary) {
  const target = provider ?? selectedProvider.value ?? providers.value[0]
  if (!target) return
  selectedPolicyId.value = null
  selectedAction.value = 'create'
  selectedProviderType.value = target.providerType
  selectedIntegrationId.value = target.integrationId
  resetCreatePayload(target.providerType)
  formError.value = ''
}

function beginPolicyAction(policy: PolicyRow, action: PolicyAction) {
  selectPolicy(policy)
  selectedAction.value = action
  showAdvancedPayload.value = false
  payloadText.value = JSON.stringify(defaultPayload(policy, action), null, 2)
  formError.value = ''
}

function cancelAction() {
  selectedAction.value = null
  formError.value = ''
  payloadText.value = '{}'
  showAdvancedPayload.value = false
}

function defaultCreatePayload(providerType: PolicyProviderType): Record<string, unknown> {
  if (providerType === 'fortigate') {
    return {
      name: 'FD_MANAGED_POLICY',
      srcintf: [],
      dstintf: [],
      srcaddr: [],
      dstaddr: [],
      service: [],
      action: 'accept',
      schedule: 'always',
      logtraffic: 'all',
      status: 'enable',
    }
  }
  return {
    sourceIp: '',
    incidentId: null,
    reason: '',
  }
}

function defaultFortiGatePolicyForm(): FortiGatePolicyForm {
  return {
    name: 'FD_MANAGED_POLICY',
    srcintf: '',
    dstintf: '',
    srcaddr: '',
    dstaddr: '',
    service: '',
    action: 'accept',
    schedule: 'always',
    logtraffic: 'all',
    status: 'enable',
  }
}

function defaultFortiWebPolicyForm(): FortiWebPolicyForm {
  return {
    sourceIp: '',
    incidentId: '',
    reason: '',
  }
}

function resetCreatePayload(providerType: PolicyProviderType) {
  const payload = defaultCreatePayload(providerType)
  if (providerType === 'fortigate') {
    fortigatePolicyForm.value = defaultFortiGatePolicyForm()
  } else {
    fortiwebPolicyForm.value = defaultFortiWebPolicyForm()
    fortiwebPolicyForm.value.sourceIp = String(payload.sourceIp ?? '')
    fortiwebPolicyForm.value.incidentId = String(payload.incidentId ?? '')
    fortiwebPolicyForm.value.reason = String(payload.reason ?? '')
  }
  payloadText.value = JSON.stringify(payload, null, 2)
  showAdvancedPayload.value = false
}

function defaultPayload(policy: PolicyRow, action: PolicyAction): Record<string, unknown> {
  if (action === 'edit') {
    if (policy.providerType === 'fortiweb' && policy.kind === 'server_policy') {
      return {
        operation: 'prepare_waf_dos_policy',
        targetServerPolicy: policy.nativeId,
        inlineProtectionProfile: 'FD Inline DoS Protection',
        dosPreventionPolicy: 'Predefined',
        reason: 'Prepare FortiWeb policy for WAF/DoS lab validation',
      }
    }
    return {
      name: policy.name,
      status: policy.status === 'enabled' ? 'enable' : 'disable',
      action: policy.action || undefined,
    }
  }
  return {}
}

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function requireText(value: string, labelKey: string): string {
  const trimmed = value.trim()
  if (!trimmed) {
    throw new Error(t('widgets.policyManager.errors.requiredField', { field: t(labelKey) }))
  }
  return trimmed
}

function requireList(value: string, labelKey: string): string[] {
  const values = splitList(value)
  if (!values.length) {
    throw new Error(t('widgets.policyManager.errors.requiredList', { field: t(labelKey) }))
  }
  return values
}

function namedItems(value: string, labelKey: string): Array<{ name: string }> {
  return requireList(value, labelKey).map(name => ({ name }))
}

function structuredPayload(): Record<string, unknown> {
  if (effectiveProviderType.value === 'fortigate') {
    return {
      name: requireText(fortigatePolicyForm.value.name, 'widgets.policyManager.form.name'),
      srcintf: namedItems(fortigatePolicyForm.value.srcintf, 'widgets.policyManager.form.sourceInterfaces'),
      dstintf: namedItems(fortigatePolicyForm.value.dstintf, 'widgets.policyManager.form.destinationInterfaces'),
      srcaddr: namedItems(fortigatePolicyForm.value.srcaddr, 'widgets.policyManager.form.sourceAddresses'),
      dstaddr: namedItems(fortigatePolicyForm.value.dstaddr, 'widgets.policyManager.form.destinationAddresses'),
      service: namedItems(fortigatePolicyForm.value.service, 'widgets.policyManager.form.services'),
      action: fortigatePolicyForm.value.action,
      schedule: requireText(fortigatePolicyForm.value.schedule, 'widgets.policyManager.form.schedule'),
      logtraffic: fortigatePolicyForm.value.logtraffic,
      status: fortigatePolicyForm.value.status,
    }
  }

  return {
    sourceIp: requireText(fortiwebPolicyForm.value.sourceIp, 'widgets.policyManager.form.sourceIp'),
    incidentId: fortiwebPolicyForm.value.incidentId.trim() || null,
    reason: requireText(fortiwebPolicyForm.value.reason, 'widgets.policyManager.form.reason'),
  }
}

function toggleAdvancedPayload() {
  if (!showAdvancedPayload.value) {
    try {
      payloadText.value = JSON.stringify(structuredPayload(), null, 2)
    } catch {
      payloadText.value = JSON.stringify(defaultCreatePayload(effectiveProviderType.value), null, 2)
    }
  }
  showAdvancedPayload.value = !showAdvancedPayload.value
}

function parsePayload(): Record<string, unknown> {
  try {
    const parsed = JSON.parse(payloadText.value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(t('widgets.policyManager.errors.payloadObject'))
    }
    return parsed as Record<string, unknown>
  } catch (err) {
    if (err instanceof SyntaxError) {
      throw new Error(t('widgets.policyManager.errors.invalidJson'))
    }
    throw err
  }
}

async function createReview() {
  if (!selectedAction.value) return
  formError.value = ''
  isReviewing.value = true
  try {
    const payload = usesStructuredPolicyForm.value ? structuredPayload() : parsePayload()
    const policy = selectedPolicy.value
    await policiesStore.reviewPolicy({
      providerType: policy?.providerType ?? selectedProviderType.value,
      integrationId: policy?.integrationId ?? selectedIntegrationId.value,
      policyId: policy?.id ?? null,
      action: selectedAction.value,
      payload,
    })
  } catch (err) {
    formError.value = err instanceof Error ? err.message : t('widgets.policyManager.errors.review')
  } finally {
    isReviewing.value = false
  }
}

async function applyReview(review: PolicyReview) {
  isApplying.value = true
  formError.value = ''
  try {
    await policiesStore.applyReview(review.id, review.reviewHash)
    await policiesStore.loadPolicies({})
  } catch (err) {
    formError.value = err instanceof Error ? err.message : t('widgets.policyManager.errors.apply')
  } finally {
    isApplying.value = false
  }
}
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'soc-policy-manager'"
    :title="t('widgets.policyManager.title')"
    :subtitle="t('widgets.policyManager.subtitle')"
    :icon="ShieldCheck"
    source="soc"
    :disable-drill="true"
  >
    <template #glance>
      <div class="flex min-h-0 flex-1 flex-col gap-3">
        <div class="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <WidgetKpiTile :label="t('widgets.policyManager.kpis.providers')" :value="stats.providers" />
          <WidgetKpiTile :label="t('widgets.policyManager.kpis.policies')" :value="stats.policies" />
          <WidgetKpiTile :label="t('widgets.policyManager.kpis.external')" :value="stats.external" :tone="stats.external ? 'warning' : 'default'" />
          <WidgetKpiTile :label="t('widgets.policyManager.kpis.mutable')" :value="stats.mutable" />
        </div>

        <div class="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(140px,0.9fr)_minmax(120px,0.7fr)_minmax(120px,0.7fr)_minmax(120px,0.7fr)_auto]">
          <label class="min-w-0">
            <span class="sr-only">{{ t('widgets.policyManager.search') }}</span>
            <input
              v-model="filters.q"
              data-test="policy-search"
              class="h-8 w-full rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
              :placeholder="t('widgets.policyManager.search')"
            />
          </label>
          <select
            v-model="filters.providerType"
            data-test="policy-provider-filter"
            class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
          >
            <option value="">{{ t('widgets.policyManager.filters.allProviders') }}</option>
            <option value="fortigate">FortiGate</option>
            <option value="fortiweb">FortiWeb</option>
          </select>
          <select
            v-model="filters.status"
            data-test="policy-status-filter"
            class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
          >
            <option value="">{{ t('widgets.policyManager.filters.allStatuses') }}</option>
            <option v-for="status in statusOptions" :key="status" :value="status">{{ statusLabel(status) }}</option>
          </select>
          <select
            v-model="filters.ownership"
            data-test="policy-ownership-filter"
            class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
          >
            <option value="">{{ t('widgets.policyManager.filters.allOwners') }}</option>
            <option value="fortidashboard">{{ t('widgets.policyManager.ownership.fortidashboard') }}</option>
            <option value="external">{{ t('widgets.policyManager.ownership.external') }}</option>
            <option value="unknown">{{ t('widgets.policyManager.ownership.unknown') }}</option>
          </select>
          <div class="flex items-center justify-end gap-1">
            <button
              type="button"
              data-test="policy-refresh"
              class="inline-flex h-8 w-8 items-center justify-center rounded border border-theme-border bg-theme-bg/80 text-theme-text-muted hover:border-theme-primary/40 hover:text-theme-text"
              :title="t('common.refresh')"
              @click.stop="refreshAll"
            >
              <RefreshCcw :size="14" :class="{ 'animate-spin': isLoading }" />
            </button>
            <button
              type="button"
              data-test="policy-create"
              class="inline-flex h-8 w-8 items-center justify-center rounded border border-emerald-400/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              :title="t('widgets.policyManager.actions.create')"
              :disabled="providers.length === 0"
              @click.stop="beginCreate()"
            >
              <Plus :size="14" />
            </button>
          </div>
        </div>

        <div v-if="error" class="flex items-start gap-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          <AlertTriangle :size="14" class="mt-0.5 shrink-0" />
          <span>{{ error }}</span>
        </div>

        <div class="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]">
          <div class="min-h-0 overflow-hidden rounded border border-theme-border/70 bg-theme-bg/45">
            <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-theme-border/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
              <span>{{ t('widgets.policyManager.columns.policy') }}</span>
              <span>{{ t('widgets.policyManager.columns.actions') }}</span>
            </div>
            <div class="max-h-full min-h-0 overflow-y-auto no-scrollbar">
              <button
                v-for="policy in filteredPolicies"
                :key="policy.id"
                type="button"
                class="w-full border-b border-theme-border/40 px-3 py-2.5 text-left text-xs last:border-0 hover:bg-theme-text/5"
                :class="selectedPolicyId === policy.id ? 'bg-theme-primary/10 ring-1 ring-inset ring-theme-primary/30' : ''"
                @click.stop="selectPolicy(policy)"
              >
                <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
                  <div class="min-w-0">
                    <div class="flex min-w-0 items-center gap-1.5">
                      <ShieldCheck :size="14" class="shrink-0 text-theme-primary" />
                      <span class="truncate font-semibold text-theme-text">{{ policy.name }}</span>
                    </div>
                    <div class="mt-1 flex flex-wrap items-center gap-1.5">
                      <span class="rounded border border-theme-border bg-theme-bg/70 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                        {{ providerLabel(policy.providerType) }}
                      </span>
                      <span class="max-w-[160px] truncate rounded border border-theme-border bg-theme-bg/70 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                        {{ providerName(policy) }}
                      </span>
                      <span class="rounded border border-theme-border bg-theme-bg/70 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                        {{ policy.kind }}
                      </span>
                      <span class="rounded border px-1.5 py-0.5 text-[10px]" :class="ownershipTone(policy.ownership)">
                        {{ ownershipLabel(policy.ownership) }}
                      </span>
                    </div>
                    <div class="mt-1 truncate text-[11px] text-theme-text-muted">{{ policy.summary || policy.nativeId }}</div>
                  </div>
                  <div class="flex shrink-0 flex-col items-end gap-1">
                    <span class="rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide" :class="statusTone(policy.status)">
                      {{ statusLabel(policy.status) }}
                    </span>
                    <div class="flex items-center gap-1">
                      <button
                        v-for="action in selectableActions(policy)"
                        :key="action"
                        type="button"
                        :data-test="`policy-action-${action}`"
                        class="inline-flex h-6 w-6 items-center justify-center rounded border border-theme-border bg-theme-bg/80 text-theme-text-muted hover:border-theme-primary/40 hover:text-theme-text"
                        :title="actionTitle(action)"
                        @click.stop="beginPolicyAction(policy, action)"
                      >
                        <component :is="actionIcon(action)" :size="12" />
                      </button>
                    </div>
                  </div>
                </div>
              </button>
              <WidgetEmptyState
                v-if="!filteredPolicies.length && !isLoading"
                :title="t('widgets.policyManager.emptyTitle')"
                :hint="t('widgets.policyManager.emptyHint')"
              />
              <div v-if="isLoading" class="px-3 py-6 text-center text-xs text-theme-text-muted">
                {{ t('common.loading') }}
              </div>
            </div>
          </div>

          <aside class="min-h-0 overflow-y-auto rounded border border-theme-border/70 bg-theme-bg/45 p-3 no-scrollbar">
            <div v-if="!selectedAction && !pendingReview" class="flex h-full min-h-[180px] flex-col items-center justify-center gap-2 text-center text-xs text-theme-text-muted">
              <FileText :size="22" class="text-theme-primary" />
              <span>{{ t('widgets.policyManager.noAction') }}</span>
            </div>
            <div v-else class="flex min-h-0 flex-col gap-3">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-theme-text">
                    {{ selectedAction ? actionLabel(selectedAction) : t('widgets.policyManager.review') }}
                  </div>
                  <div class="truncate text-[11px] text-theme-text-muted">
                    {{ selectedPolicy?.name || selectedProvider?.name || t('widgets.policyManager.newPolicy') }}
                  </div>
                </div>
                <button
                  type="button"
                  class="rounded p-1 text-theme-text-muted hover:bg-theme-border hover:text-theme-text"
                  :title="t('common.close')"
                  @click.stop="cancelAction"
                >
                  <X :size="14" />
                </button>
              </div>

              <div v-if="selectedAction === 'create'" class="grid grid-cols-1 gap-2">
                <select
                  v-model="selectedIntegrationId"
                  data-test="policy-create-provider"
                  class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                >
                  <option
                    v-for="provider in providerOptions"
                    :key="`${provider.providerType}:${provider.integrationId}`"
                    :value="provider.integrationId"
                  >
                    {{ providerLabel(provider.providerType) }} / {{ provider.name }}
                  </option>
                </select>
              </div>

              <div
                v-if="usesStructuredPolicyForm"
                data-test="policy-structured-form"
                class="grid gap-2"
              >
                <template v-if="effectiveProviderType === 'fortigate'">
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.name') }}
                    </span>
                    <input
                      v-model="fortigatePolicyForm.name"
                      data-test="policy-form-name"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.sourceInterfaces') }}
                    </span>
                    <input
                      v-model="fortigatePolicyForm.srcintf"
                      data-test="policy-form-srcintf"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.destinationInterfaces') }}
                    </span>
                    <input
                      v-model="fortigatePolicyForm.dstintf"
                      data-test="policy-form-dstintf"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.sourceAddresses') }}
                    </span>
                    <input
                      v-model="fortigatePolicyForm.srcaddr"
                      data-test="policy-form-srcaddr"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.destinationAddresses') }}
                    </span>
                    <input
                      v-model="fortigatePolicyForm.dstaddr"
                      data-test="policy-form-dstaddr"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.services') }}
                    </span>
                    <input
                      v-model="fortigatePolicyForm.service"
                      data-test="policy-form-service"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <div class="grid grid-cols-1 gap-2">
                    <label class="grid gap-1">
                      <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                        {{ t('widgets.policyManager.form.action') }}
                      </span>
                      <select
                        v-model="fortigatePolicyForm.action"
                        data-test="policy-form-action"
                        class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                      >
                        <option value="accept">{{ t('widgets.policyManager.form.accept') }}</option>
                        <option value="deny">{{ t('widgets.policyManager.form.deny') }}</option>
                      </select>
                    </label>
                    <label class="grid gap-1">
                      <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                        {{ t('widgets.policyManager.form.status') }}
                      </span>
                      <select
                        v-model="fortigatePolicyForm.status"
                        data-test="policy-form-status"
                        class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                      >
                        <option value="enable">{{ t('widgets.policyManager.form.enable') }}</option>
                        <option value="disable">{{ t('widgets.policyManager.form.disable') }}</option>
                      </select>
                    </label>
                  </div>
                  <div class="grid grid-cols-1 gap-2">
                    <label class="grid gap-1">
                      <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                        {{ t('widgets.policyManager.form.schedule') }}
                      </span>
                      <input
                        v-model="fortigatePolicyForm.schedule"
                        data-test="policy-form-schedule"
                        class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                      />
                    </label>
                    <label class="grid gap-1">
                      <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                        {{ t('widgets.policyManager.form.logtraffic') }}
                      </span>
                      <select
                        v-model="fortigatePolicyForm.logtraffic"
                        data-test="policy-form-logtraffic"
                        class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                      >
                        <option value="all">{{ t('widgets.policyManager.form.logAll') }}</option>
                        <option value="utm">{{ t('widgets.policyManager.form.logSecurity') }}</option>
                        <option value="disable">{{ t('widgets.policyManager.form.logDisable') }}</option>
                      </select>
                    </label>
                  </div>
                </template>

                <template v-else>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.sourceIp') }}
                    </span>
                    <input
                      v-model="fortiwebPolicyForm.sourceIp"
                      data-test="policy-form-source-ip"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.incidentId') }}
                    </span>
                    <input
                      v-model="fortiwebPolicyForm.incidentId"
                      data-test="policy-form-incident-id"
                      class="h-8 rounded border border-theme-border bg-theme-bg/80 px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                  <label class="grid gap-1">
                    <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                      {{ t('widgets.policyManager.form.reason') }}
                    </span>
                    <textarea
                      v-model="fortiwebPolicyForm.reason"
                      data-test="policy-form-reason"
                      class="min-h-[64px] resize-none rounded border border-theme-border bg-theme-bg/80 p-2 text-xs text-theme-text outline-none focus:border-theme-primary"
                    />
                  </label>
                </template>
              </div>

              <div v-if="supportsStructuredPolicyForm" class="flex justify-end">
                <button
                  type="button"
                  data-test="policy-advanced-json-toggle"
                  class="text-[11px] font-semibold text-theme-primary hover:text-theme-primary/80"
                  @click.stop="toggleAdvancedPayload"
                >
                  {{ showAdvancedPayload ? t('widgets.policyManager.hideAdvancedJson') : t('widgets.policyManager.showAdvancedJson') }}
                </button>
              </div>

              <label v-if="!supportsStructuredPolicyForm || showAdvancedPayload" class="grid gap-1">
                <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                  {{ t('widgets.policyManager.payload') }}
                </span>
                <textarea
                  v-model="payloadText"
                  data-test="policy-payload"
                  class="min-h-[104px] resize-none rounded border border-theme-border bg-theme-bg/80 p-2 font-mono text-[11px] leading-relaxed text-theme-text outline-none focus:border-theme-primary"
                  spellcheck="false"
                />
              </label>

              <div v-if="formError" class="rounded border border-red-500/30 bg-red-500/10 px-2 py-1.5 text-xs text-red-200">
                {{ formError }}
              </div>

              <button
                v-if="selectedAction"
                type="button"
                data-test="policy-review"
                class="inline-flex h-8 items-center justify-center gap-1.5 rounded border border-theme-primary/40 bg-theme-primary/15 px-3 text-xs font-semibold text-theme-primary hover:bg-theme-primary/25 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="isReviewing"
                @click.stop="createReview"
              >
                <FileDiff :size="14" />
                {{ isReviewing ? t('common.loading') : t('widgets.policyManager.createReview') }}
              </button>

              <div v-if="pendingReview" data-test="policy-review-panel" class="grid gap-2 rounded border border-theme-primary/30 bg-theme-primary/5 p-2">
                <div class="flex items-center justify-between gap-2">
                  <span class="truncate text-xs font-semibold text-theme-text">{{ pendingReview.title }}</span>
                  <span class="shrink-0 rounded border border-theme-border bg-theme-bg px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                    {{ pendingReview.status }}
                  </span>
                </div>
                <div v-if="reviewDiff.length" class="grid gap-1">
                  <div class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
                    {{ t('widgets.policyManager.diff') }}
                  </div>
                  <div
                    v-for="(entry, index) in reviewDiff"
                    :key="index"
                    class="rounded border border-theme-border/60 bg-theme-bg/70 px-2 py-1 text-[11px] text-theme-text-muted"
                  >
                    <span class="font-semibold text-theme-text">{{ entry.field ?? t('common.details') }}</span>
                    <span> {{ entry.before ?? '-' }} -> {{ entry.after ?? '-' }}</span>
                  </div>
                </div>
                <div v-if="reviewWarnings.length" class="grid gap-1">
                  <div
                    v-for="(warning, index) in reviewWarnings"
                    :key="index"
                    class="flex items-start gap-1.5 rounded border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100"
                  >
                    <AlertTriangle :size="12" class="mt-0.5 shrink-0" />
                    <span>{{ warning.message ?? warning }}</span>
                  </div>
                </div>
                <button
                  type="button"
                  data-test="policy-apply"
                  class="inline-flex h-8 items-center justify-center gap-1.5 rounded border border-emerald-400/40 bg-emerald-500/10 px-3 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="isApplying"
                  @click.stop="applyReview(pendingReview)"
                >
                  <CheckCircle2 :size="14" />
                  {{ isApplying ? t('common.loading') : t('widgets.policyManager.applyReview') }}
                </button>
              </div>

              <div v-if="lastApplyResult" class="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1.5 text-xs text-emerald-200">
                {{ t('widgets.policyManager.applied') }}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
