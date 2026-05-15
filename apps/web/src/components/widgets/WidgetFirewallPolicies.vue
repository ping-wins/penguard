<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban, FileText, ListChecks, Route, Server, ShieldCheck } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetEmptyState from './shell/WidgetEmptyState.vue'

const props = defineProps<{ data: any, catalogId?: string }>()
const { t } = useI18n()

type PolicyRecord = Record<string, unknown>

const policies = computed<PolicyRecord[]>(() => {
  if (!Array.isArray(props.data?.policies)) return []
  return props.data.policies
})

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  return String(value)
}

function asList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'object' && item !== null && 'name' in item) {
          return valueText((item as { name?: unknown }).name)
        }
        return valueText(item)
      })
      .filter(Boolean)
  }
  const text = valueText(value)
  return text ? [text] : []
}

function listText(value: unknown, fallback = t('widgets.firewallPolicies.any')): string {
  const values = asList(value)
  return values.length ? values.join(', ') : fallback
}

function actionValue(policy: PolicyRecord): string {
  return valueText(policy.action).toLowerCase()
}

function loggingValue(policy: PolicyRecord): string {
  return valueText(policy.logging ?? policy.logtraffic ?? policy.logTraffic).toLowerCase()
}

function isBlocking(policy: PolicyRecord): boolean {
  const action = actionValue(policy)
  return policy.isBlocking === true || ['deny', 'block', 'blocked', 'reject'].includes(action)
}

function isOwned(policy: PolicyRecord): boolean {
  const name = valueText(policy.name)
  const comments = valueText(policy.comments ?? policy.comment).toLowerCase()
  return policy.isFortiDashboardOwned === true || name.startsWith('FD_') || comments.includes('fortidashboard owned')
}

function actionLabel(policy: PolicyRecord): string {
  if (isBlocking(policy)) return t('widgets.firewallPolicies.actions.block')
  const action = actionValue(policy)
  if (action === 'accept' || action === 'allow') {
    return loggingValue(policy) && loggingValue(policy) !== 'disable'
      ? t('widgets.firewallPolicies.actions.allowLog')
      : t('widgets.firewallPolicies.actions.allow')
  }
  return action || t('widgets.firewallPolicies.unknown')
}

function actionTone(policy: PolicyRecord): string {
  if (isBlocking(policy)) return 'border-red-400/30 bg-red-500/10 text-red-200'
  return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
}

function policyKindLabel(policy: PolicyRecord): string {
  const kind = valueText(policy.policyKind)
  if (kind === 'temporary_block') return t('widgets.firewallPolicies.kinds.temporaryBlock')
  if (kind === 'lab_allow_log') return t('widgets.firewallPolicies.kinds.labAllowLog')
  if (kind === 'fortidashboard') return t('widgets.firewallPolicies.kinds.fortiDashboard')
  return t('widgets.firewallPolicies.kinds.standard')
}

function sourceInterfaces(policy: PolicyRecord): unknown {
  return policy.sourceInterfaces ?? policy.srcIntf ?? policy.srcintf
}

function destinationInterfaces(policy: PolicyRecord): unknown {
  return policy.destinationInterfaces ?? policy.dstIntf ?? policy.dstintf
}

function sourceAddresses(policy: PolicyRecord): unknown {
  return policy.sourceAddresses ?? policy.srcaddr ?? policy.srcAddr
}

function destinationAddresses(policy: PolicyRecord): unknown {
  return policy.destinationAddresses ?? policy.dstaddr ?? policy.dstAddr
}

function services(policy: PolicyRecord): unknown {
  return policy.services ?? policy.service
}

function interfacesLabel(policy: PolicyRecord): string {
  return `${listText(sourceInterfaces(policy))} -> ${listText(destinationInterfaces(policy))}`
}

function addressesLabel(policy: PolicyRecord): string {
  return `${listText(sourceAddresses(policy))} -> ${listText(destinationAddresses(policy))}`
}

function loggingLabel(policy: PolicyRecord): string {
  const logging = loggingValue(policy)
  if (!logging) return t('widgets.firewallPolicies.loggingUnknown')
  if (logging === 'all' || logging === 'enable') return t('widgets.firewallPolicies.logAll')
  if (logging === 'utm') return t('widgets.firewallPolicies.logUtm')
  if (logging === 'disable' || logging === 'disabled') return t('widgets.firewallPolicies.loggingDisabled')
  return t('widgets.firewallPolicies.logValue', { value: logging })
}
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-firewall-policies'"
    :title="t('widgets.firewallPolicies.title')"
    :subtitle="t('widgets.firewallPolicies.subtitle')"
    :icon="ListChecks"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
      <div class="flex-1 overflow-y-auto rounded-md bg-theme-text/5 no-scrollbar">
        <div class="grid grid-cols-[1fr_auto] gap-x-3 px-3 py-2 text-[10px] uppercase tracking-wide text-theme-text-muted border-b border-theme-border/50">
          <span>{{ t('widgets.firewallPolicies.policy') }}</span>
          <span>{{ t('widgets.firewallPolicies.enforcement') }}</span>
        </div>

        <div
          v-for="(policy, index) in policies"
          :key="valueText(policy.id) || valueText(policy.name) || index"
          class="border-b border-theme-border/40 px-3 py-2.5 text-sm last:border-0"
        >
          <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
            <div class="min-w-0">
              <div class="flex min-w-0 items-center gap-1.5">
                <Ban v-if="isBlocking(policy)" :size="15" class="shrink-0 text-red-300" />
                <ShieldCheck v-else :size="15" class="shrink-0 text-emerald-300" />
                <div class="truncate font-semibold text-theme-text">
                  {{ valueText(policy.name) || `Policy ${valueText(policy.id)}` }}
                </div>
              </div>
              <div class="mt-1 flex flex-wrap gap-1.5 text-[10px] font-semibold uppercase tracking-wide">
                <span class="rounded border border-theme-border bg-theme-bg/60 px-1.5 py-0.5 text-theme-text-muted">
                  {{ policyKindLabel(policy) }}
                </span>
                <span
                  v-if="isOwned(policy)"
                  class="rounded border border-cyan-400/30 bg-cyan-500/10 px-1.5 py-0.5 text-cyan-200"
                >
                  FortiDashboard
                </span>
                <span
                  v-if="policy.id"
                  class="rounded border border-theme-border bg-theme-bg/60 px-1.5 py-0.5 text-theme-text-muted"
                >
                  {{ t('widgets.firewallPolicies.id') }} {{ valueText(policy.id) }}
                </span>
              </div>
            </div>
            <div class="flex shrink-0 flex-col items-end gap-1">
              <span
                class="rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
                :class="actionTone(policy)"
              >
                {{ actionLabel(policy) }}
              </span>
              <span class="text-[10px] text-theme-text-muted">{{ valueText(policy.status) || t('widgets.firewallPolicies.unknown') }}</span>
            </div>
          </div>

          <div class="mt-2 grid gap-1.5 text-[11px] text-theme-text-muted">
            <div class="flex min-w-0 items-center gap-1.5">
              <Route :size="12" class="shrink-0 text-theme-primary" />
              <span class="shrink-0 font-semibold uppercase tracking-wide">{{ t('widgets.firewallPolicies.interfaces') }}</span>
              <span class="truncate text-theme-text">{{ interfacesLabel(policy) }}</span>
            </div>
            <div class="flex min-w-0 items-center gap-1.5">
              <Server :size="12" class="shrink-0 text-theme-primary" />
              <span class="shrink-0 font-semibold uppercase tracking-wide">{{ t('widgets.firewallPolicies.addresses') }}</span>
              <span class="truncate text-theme-text">{{ addressesLabel(policy) }}</span>
            </div>
            <div class="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
              <div class="min-w-0 truncate">
                <span class="font-semibold uppercase tracking-wide">{{ t('widgets.firewallPolicies.service') }}</span>
                <span class="ml-1 text-theme-text">{{ listText(services(policy), t('common.all')) }}</span>
              </div>
              <div class="min-w-0 truncate">
                <span class="font-semibold uppercase tracking-wide">{{ t('widgets.firewallPolicies.schedule') }}</span>
                <span class="ml-1 text-theme-text">{{ valueText(policy.schedule) || t('widgets.firewallPolicies.unknown') }}</span>
              </div>
              <div class="min-w-0 truncate">
                <span class="font-semibold uppercase tracking-wide">{{ t('widgets.firewallPolicies.logging') }}</span>
                <span class="ml-1 text-theme-text">{{ loggingLabel(policy) }}</span>
              </div>
            </div>
            <div
              v-if="valueText(policy.comments ?? policy.comment)"
              class="flex min-w-0 items-start gap-1.5 text-theme-text-muted"
            >
              <FileText :size="12" class="mt-0.5 shrink-0 text-theme-primary" />
              <span class="line-clamp-2">{{ valueText(policy.comments ?? policy.comment) }}</span>
            </div>
          </div>
        </div>

        <WidgetEmptyState
          v-if="!policies.length"
          :title="t('widgets.firewallPolicies.emptyTitle')"
          :hint="t('widgets.firewallPolicies.emptyHint')"
        />
      </div>
    </template>
  </WidgetShell>
</template>
