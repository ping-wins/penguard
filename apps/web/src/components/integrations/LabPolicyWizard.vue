<script setup lang="ts">
import { computed, ref } from 'vue'
import { ClipboardCheck, Play, ShieldCheck } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import {
  useIntegrationsStore,
  type FortiGatePolicyApplyResponse,
  type FortiGatePolicyPayload,
  type FortiGatePolicyPreflightResponse,
  type FortiGatePolicyReviewResponse,
} from '../../stores/useIntegrationsStore'

const props = defineProps<{
  integrationId: string
}>()

const { t } = useI18n()
const integrationsStore = useIntegrationsStore()

const sourceInterface = ref('port2')
const destinationInterface = ref('port3')
const sourceIp = ref('')
const destinationIp = ref('')
const service = ref('ALL')
const preflight = ref<FortiGatePolicyPreflightResponse | null>(null)
const review = ref<FortiGatePolicyReviewResponse | null>(null)
const applied = ref<FortiGatePolicyApplyResponse | null>(null)
const isLoading = ref(false)
const errorMessage = ref<string | null>(null)

const policyPayload = computed<FortiGatePolicyPayload>(() => ({
  intent: 'lab_allow_log',
  scope: 'source_destination_service',
  source_interface: sourceInterface.value.trim(),
  destination_interface: destinationInterface.value.trim(),
  source_ip: sourceIp.value.trim(),
  destination_ip: destinationIp.value.trim(),
  service: service.value.trim() || 'ALL',
}))

const canSubmit = computed(() => {
  return Boolean(
    policyPayload.value.source_interface
      && policyPayload.value.destination_interface
      && policyPayload.value.source_ip
      && policyPayload.value.destination_ip,
  )
})

async function runPreflight() {
  isLoading.value = true
  errorMessage.value = null
  applied.value = null
  const result = await integrationsStore.preflightFortigatePolicy(props.integrationId, policyPayload.value)
  if (result.success) {
    preflight.value = result.data
    review.value = null
  } else {
    errorMessage.value = result.error
  }
  isLoading.value = false
}

async function createReview() {
  isLoading.value = true
  errorMessage.value = null
  const result = await integrationsStore.createFortigatePolicyReview(props.integrationId, policyPayload.value)
  if (result.success) {
    review.value = result.data
    preflight.value = result.data
  } else {
    errorMessage.value = result.error
  }
  isLoading.value = false
}

async function applyReview() {
  if (!review.value) return
  isLoading.value = true
  errorMessage.value = null
  const result = await integrationsStore.applyFortigatePolicy(props.integrationId, {
    request_id: review.value.request_id,
    review_hash: review.value.review_hash,
  })
  if (result.success) {
    applied.value = result.data
  } else {
    errorMessage.value = result.error
  }
  isLoading.value = false
}
</script>

<template>
  <section
    class="mt-2 rounded border border-theme-border bg-theme-bg/70 p-2 text-xs text-theme-text-muted"
    :data-test="`fortigate-lab-policy-wizard-${integrationId}`"
  >
    <div class="flex items-start gap-2">
      <ShieldCheck :size="16" class="mt-0.5 shrink-0 text-theme-primary" />
      <div class="min-w-0 flex-1">
        <div class="font-medium text-theme-text">
          {{ t('integrations.fortigatePolicy.title') }}
        </div>
        <p class="mt-0.5 leading-snug">
          {{ t('integrations.fortigatePolicy.subtitle') }}
        </p>
      </div>
    </div>

    <div class="mt-3 grid grid-cols-2 gap-2">
      <label class="flex flex-col gap-1">
        <span>{{ t('integrations.fortigatePolicy.sourceInterface') }}</span>
        <input v-model="sourceInterface" class="rounded border border-theme-border bg-theme-panel px-2 py-1 text-theme-text outline-none focus:border-theme-primary">
      </label>
      <label class="flex flex-col gap-1">
        <span>{{ t('integrations.fortigatePolicy.destinationInterface') }}</span>
        <input v-model="destinationInterface" class="rounded border border-theme-border bg-theme-panel px-2 py-1 text-theme-text outline-none focus:border-theme-primary">
      </label>
      <label class="flex flex-col gap-1">
        <span>{{ t('integrations.fortigatePolicy.sourceIp') }}</span>
        <input v-model="sourceIp" class="rounded border border-theme-border bg-theme-panel px-2 py-1 text-theme-text outline-none focus:border-theme-primary">
      </label>
      <label class="flex flex-col gap-1">
        <span>{{ t('integrations.fortigatePolicy.destinationIp') }}</span>
        <input v-model="destinationIp" class="rounded border border-theme-border bg-theme-panel px-2 py-1 text-theme-text outline-none focus:border-theme-primary">
      </label>
      <label class="col-span-2 flex flex-col gap-1">
        <span>{{ t('integrations.fortigatePolicy.service') }}</span>
        <input v-model="service" class="rounded border border-theme-border bg-theme-panel px-2 py-1 text-theme-text outline-none focus:border-theme-primary">
      </label>
    </div>

    <div class="mt-3 flex flex-wrap gap-2">
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded border border-theme-border px-2 py-1 text-[11px] font-medium text-theme-text transition-colors hover:bg-theme-border disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!canSubmit || isLoading"
        @click="runPreflight"
      >
        <ClipboardCheck :size="13" />
        {{ t('integrations.fortigatePolicy.preflight') }}
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded border border-theme-border px-2 py-1 text-[11px] font-medium text-theme-text transition-colors hover:bg-theme-border disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!preflight || isLoading"
        @click="createReview"
      >
        <ClipboardCheck :size="13" />
        {{ t('integrations.fortigatePolicy.createReview') }}
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded border border-theme-primary/60 px-2 py-1 text-[11px] font-semibold text-theme-primary transition-colors hover:bg-theme-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!review || isLoading"
        @click="applyReview"
      >
        <Play :size="13" />
        {{ t('integrations.fortigatePolicy.apply') }}
      </button>
    </div>

    <div v-if="errorMessage" class="mt-2 text-red-400">
      {{ errorMessage }}
    </div>

    <div v-if="preflight" class="mt-3 rounded border border-theme-border bg-theme-panel/70 p-2">
      <div class="font-medium text-theme-text">
        {{ t('integrations.fortigatePolicy.proposedPolicy') }}:
        {{ preflight.proposed_policy_name }}
      </div>
      <div class="mt-1">{{ t('integrations.fortigatePolicy.placement') }}: {{ preflight.placement }}</div>
      <div class="mt-2 font-medium text-theme-text">{{ t('integrations.fortigatePolicy.objectChanges') }}</div>
      <ul class="mt-1 space-y-1">
        <li v-for="change in preflight.changes" :key="`${change.object_type}-${change.name}`">
          {{ change.operation }} · {{ change.object_type }} · {{ change.name }}
        </li>
      </ul>
      <div v-if="preflight.warnings.length" class="mt-2 text-amber-300">
        {{ t('integrations.fortigatePolicy.warnings') }}: {{ preflight.warnings.join(' ') }}
      </div>
    </div>

    <div v-if="applied" class="mt-2 text-theme-primary">
      {{ t('integrations.fortigatePolicy.applied') }}
    </div>
  </section>
</template>
