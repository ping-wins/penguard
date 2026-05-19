<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PlaybookFlowNode } from '../../../utils/playbookGraph'
import { usePlaybooksStore } from '../../../stores/usePlaybooksStore'

const props = defineProps<{
  node: PlaybookFlowNode | null
}>()
const emit = defineEmits<{
  updateConfig: [nodeId: string, config: Record<string, unknown>]
}>()

const { t } = useI18n()
const playbooksStore = usePlaybooksStore()
const configText = ref('{}')
const guidedConfig = ref<Record<string, any>>({})
const error = ref('')
const isJsonMode = ref(false)
const newDestinationName = ref('')
const newDestinationUrl = ref('')
const destinationStatus = ref('')
const isCreatingDestination = ref(false)
const testingDestinationId = ref('')
const title = computed(() => props.node?.data.label ?? t('playbooks.canvas.noNodeSelected'))
const nodeTypeDefinition = computed(() => (
  props.node ? playbooksStore.nodeTypeById[props.node.data.nodeType] ?? null : null
))
const isWebhookNode = computed(() => props.node?.data.nodeType === 'notify.webhook')
const schemaProperties = computed<Record<string, any>>(() => {
  const properties = nodeTypeDefinition.value?.configSchema?.properties
  return properties && typeof properties === 'object' && !Array.isArray(properties) ? properties : {}
})
const requiredKeys = computed<string[]>(() => {
  const required = nodeTypeDefinition.value?.configSchema?.required
  return Array.isArray(required) ? required.map(String) : []
})
const missingRequiredInputs = computed(() => (
  requiredKeys.value.filter((key) => {
    const value = guidedConfig.value[key]
    if (Array.isArray(value)) return value.length === 0
    return value === undefined || value === null || value === ''
  })
))
const missingRequiredLabels = computed(() => (
  missingRequiredInputs.value.map((key) => fieldTitle(key, schemaProperties.value[key]))
))
const hasGuidedFields = computed(() => Object.keys(schemaProperties.value).length > 0)
const canCreateDestination = computed(() => (
  newDestinationName.value.trim().length > 0 && newDestinationUrl.value.trim().length > 0
))

watch(
  () => props.node?.id,
  () => {
    const nextConfig = props.node?.data.config ?? {}
    guidedConfig.value = { ...nextConfig }
    configText.value = JSON.stringify(nextConfig, null, 2)
    error.value = ''
    isJsonMode.value = false
    destinationStatus.value = ''
  },
  { immediate: true },
)

function applyConfig() {
  if (!props.node) return
  if (!isJsonMode.value && hasGuidedFields.value) {
    if (missingRequiredInputs.value.length > 0) {
      error.value = t('playbooks.canvas.missingRequired', { fields: missingRequiredLabels.value.join(', ') })
      return
    }
    emit('updateConfig', props.node.id, normalizedGuidedConfig())
    error.value = ''
    return
  }
  try {
    const parsed = JSON.parse(configText.value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(t('playbooks.canvas.configObjectRequired'))
    }
    emit('updateConfig', props.node.id, parsed)
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('playbooks.canvas.invalidConfig')
  }
}

function applyExampleConfig() {
  if (!props.node || !nodeTypeDefinition.value?.exampleConfig) return
  const nextConfig = { ...nodeTypeDefinition.value.exampleConfig }
  guidedConfig.value = nextConfig
  configText.value = JSON.stringify(nextConfig, null, 2)
  emit('updateConfig', props.node.id, nextConfig)
  error.value = ''
}

function normalizedGuidedConfig() {
  const next: Record<string, any> = {}
  for (const [key, value] of Object.entries(guidedConfig.value)) {
    if (value === '' || value === undefined || value === null) continue
    next[key] = value
  }
  configText.value = JSON.stringify(next, null, 2)
  return next
}

function fieldTitle(key: string, schema: any) {
  return String(schema?.title || key)
}

function fieldDescription(schema: any) {
  return String(schema?.description || '')
}

function updateArrayField(key: string, value: string, checked: boolean) {
  const current = Array.isArray(guidedConfig.value[key]) ? guidedConfig.value[key] : []
  guidedConfig.value[key] = checked
    ? Array.from(new Set([...current, value]))
    : current.filter((item: string) => item !== value)
}

function isLongTextField(key: string, schema: any) {
  const normalized = key.toLowerCase()
  return schema?.format === 'textarea'
    || normalized.includes('content')
    || normalized.includes('template')
    || normalized.includes('message')
    || normalized.includes('note')
}

async function createDestination() {
  if (!props.node || !canCreateDestination.value) return
  isCreatingDestination.value = true
  destinationStatus.value = ''
  error.value = ''
  try {
    const result = await playbooksStore.createWebhookDestination({
      name: newDestinationName.value.trim(),
      kind: 'discord',
      url: newDestinationUrl.value.trim(),
    })
    guidedConfig.value = {
      ...guidedConfig.value,
      destinationId: result.id,
      content: guidedConfig.value.content || nodeTypeDefinition.value?.exampleConfig?.content || '',
    }
    configText.value = JSON.stringify(guidedConfig.value, null, 2)
    newDestinationUrl.value = ''
    destinationStatus.value = t('playbooks.canvas.destinationCreated', { name: result.name })
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('playbooks.canvas.destinationCreateFailed')
  } finally {
    isCreatingDestination.value = false
  }
}

async function testDestination(destinationId: string) {
  if (!destinationId) return
  testingDestinationId.value = destinationId
  destinationStatus.value = ''
  error.value = ''
  try {
    const content = typeof guidedConfig.value.content === 'string' && guidedConfig.value.content.trim()
      ? guidedConfig.value.content
      : 'Penguard playbook webhook test'
    const result = await playbooksStore.testWebhookDestination(destinationId, content)
    destinationStatus.value = result.ok
      ? t('playbooks.canvas.destinationTestSucceeded', { statusCode: result.statusCode })
      : t('playbooks.canvas.destinationTestFailedWithStatus', { statusCode: result.statusCode })
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('playbooks.canvas.destinationTestFailed')
  } finally {
    testingDestinationId.value = ''
  }
}
</script>

<template>
  <aside class="flex min-h-0 flex-col gap-2 rounded border border-theme-border bg-theme-bg/80 p-3">
    <div>
      <div class="text-xs font-semibold text-theme-text">{{ title }}</div>
      <div v-if="props.node" class="mt-0.5 font-mono text-[10px] text-theme-text-muted">
        {{ props.node.data.nodeType }}
      </div>
    </div>
    <template v-if="props.node">
      <div v-if="nodeTypeDefinition" class="grid gap-2 rounded border border-theme-border bg-theme-panel/60 p-2">
        <div v-if="nodeTypeDefinition.effectSummary" class="text-[11px] leading-snug text-theme-text">
          {{ nodeTypeDefinition.effectSummary }}
        </div>
        <div class="flex flex-wrap gap-1">
          <span class="rounded border border-theme-border px-1.5 py-0.5 text-[10px] text-theme-text-muted">
            {{ nodeTypeDefinition.boundary }}
          </span>
          <span
            class="rounded border px-1.5 py-0.5 text-[10px]"
            :class="nodeTypeDefinition.liveAvailable ? 'border-amber-400/40 text-amber-100' : 'border-sky-400/30 text-sky-100'"
          >
            {{ nodeTypeDefinition.liveAvailable ? t('playbooks.liveCapable') : t('playbooks.dryRunOnly') }}
          </span>
        </div>
      </div>

      <div v-if="missingRequiredLabels.length" data-test="playbook-node-config-missing" class="rounded border border-amber-400/30 bg-amber-500/10 p-2 text-[11px] text-amber-100">
        {{ t('playbooks.canvas.missingRequired', { fields: missingRequiredLabels.join(', ') }) }}
      </div>

      <section v-if="isWebhookNode" class="grid gap-2 rounded border border-theme-border bg-theme-panel/60 p-2">
        <div class="flex items-center justify-between gap-2">
          <h4 class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
            {{ t('playbooks.canvas.webhookDestinations') }}
          </h4>
          <span class="rounded border border-theme-border px-1.5 py-0.5 text-[10px] text-theme-text-muted">
            {{ playbooksStore.webhookDestinations.length }}
          </span>
        </div>
        <div v-if="playbooksStore.webhookDestinations.length" class="grid gap-1">
          <div
            v-for="destination in playbooksStore.webhookDestinations"
            :key="destination.id"
            class="grid gap-1 rounded border border-theme-border bg-theme-bg/70 p-2"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0">
                <div class="truncate text-xs font-semibold text-theme-text">{{ destination.name }}</div>
                <div class="truncate font-mono text-[10px] text-theme-text-muted">{{ destination.redactedUrl }}</div>
              </div>
              <button
                type="button"
                class="shrink-0 rounded border border-theme-border px-2 py-1 text-[10px] text-theme-text-muted hover:text-theme-text disabled:opacity-50"
                :disabled="testingDestinationId === destination.id"
                :data-test="`playbook-webhook-destination-test-${destination.id}`"
                @click="testDestination(destination.id)"
              >
                {{ testingDestinationId === destination.id ? t('common.loading') : t('playbooks.canvas.testDestination') }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="rounded border border-theme-border bg-theme-bg/70 p-2 text-[11px] text-theme-text-muted">
          {{ t('playbooks.canvas.noWebhookDestinations') }}
        </div>
        <div class="grid gap-1">
          <input
            v-model="newDestinationName"
            data-test="playbook-webhook-destination-name"
            class="h-8 rounded border border-theme-border bg-theme-bg px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
            :placeholder="t('playbooks.canvas.destinationNamePlaceholder')"
          />
          <input
            v-model="newDestinationUrl"
            data-test="playbook-webhook-destination-url"
            class="h-8 rounded border border-theme-border bg-theme-bg px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
            type="password"
            autocomplete="off"
            :placeholder="t('playbooks.canvas.destinationUrlPlaceholder')"
          />
          <button
            type="button"
            data-test="playbook-webhook-destination-create"
            class="rounded border border-theme-primary/40 bg-theme-primary/10 px-2 py-1 text-xs font-semibold text-theme-primary hover:bg-theme-primary/20 disabled:opacity-50"
            :disabled="!canCreateDestination || isCreatingDestination"
            @click="createDestination"
          >
            {{ isCreatingDestination ? t('common.loading') : t('playbooks.canvas.createDestination') }}
          </button>
        </div>
        <div v-if="destinationStatus" class="text-[11px] text-emerald-200">
          {{ destinationStatus }}
        </div>
      </section>

      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded border px-2 py-1 text-[11px]"
          :class="!isJsonMode ? 'border-theme-primary/40 bg-theme-primary/10 text-theme-primary' : 'border-theme-border text-theme-text-muted'"
          :disabled="!hasGuidedFields"
          @click="isJsonMode = false"
        >
          {{ t('playbooks.canvas.guidedConfig') }}
        </button>
        <button
          type="button"
          class="rounded border px-2 py-1 text-[11px]"
          :class="isJsonMode ? 'border-theme-primary/40 bg-theme-primary/10 text-theme-primary' : 'border-theme-border text-theme-text-muted'"
          @click="isJsonMode = true"
        >
          {{ t('playbooks.canvas.jsonConfig') }}
        </button>
      </div>

      <div v-if="!isJsonMode && hasGuidedFields" class="grid gap-2">
        <label v-for="(schema, key) in schemaProperties" :key="key" class="grid gap-1">
          <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
            {{ fieldTitle(String(key), schema) }}
          </span>
          <select
            v-if="props.node.data.nodeType === 'notify.webhook' && key === 'destinationId'"
            v-model="guidedConfig[key]"
            :data-test="`playbook-config-field-${String(key)}`"
            class="h-8 rounded border border-theme-border bg-theme-panel px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
          >
            <option value="">{{ t('playbooks.canvas.selectDestination') }}</option>
            <option
              v-for="destination in playbooksStore.webhookDestinations"
              :key="destination.id"
              :value="destination.id"
            >
              {{ destination.name }} · {{ destination.redactedUrl }}
            </option>
          </select>
          <select
            v-else-if="Array.isArray(schema.enum)"
            v-model="guidedConfig[key]"
            :data-test="`playbook-config-field-${String(key)}`"
            class="h-8 rounded border border-theme-border bg-theme-panel px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
          >
            <option value="">{{ fieldTitle(String(key), schema) }}</option>
            <option v-for="option in schema.enum" :key="String(option)" :value="option">
              {{ option }}
            </option>
          </select>
          <div
            v-else-if="schema.type === 'array' && Array.isArray(schema.items?.enum)"
            :data-test="`playbook-config-field-${String(key)}`"
            class="grid gap-1 rounded border border-theme-border bg-theme-panel p-2"
          >
            <label
              v-for="option in schema.items.enum"
              :key="String(option)"
              class="flex items-center gap-2 text-xs text-theme-text"
            >
              <input
                type="checkbox"
                :checked="Array.isArray(guidedConfig[key]) && guidedConfig[key].includes(option)"
                @change="updateArrayField(String(key), String(option), ($event.target as HTMLInputElement).checked)"
              />
              {{ option }}
            </label>
          </div>
          <input
            v-else-if="schema.type === 'integer'"
            v-model.number="guidedConfig[key]"
            type="number"
            :min="schema.minimum"
            :max="schema.maximum"
            :data-test="`playbook-config-field-${String(key)}`"
            class="h-8 rounded border border-theme-border bg-theme-panel px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
          />
          <textarea
            v-else-if="schema.type === 'string' && isLongTextField(String(key), schema)"
            v-model="guidedConfig[key]"
            :data-test="`playbook-config-field-${String(key)}`"
            class="min-h-[76px] resize-none rounded border border-theme-border bg-theme-panel px-2 py-1.5 text-xs text-theme-text outline-none focus:border-theme-primary"
            spellcheck="false"
          />
          <input
            v-else
            v-model="guidedConfig[key]"
            type="text"
            :data-test="`playbook-config-field-${String(key)}`"
            class="h-8 rounded border border-theme-border bg-theme-panel px-2 text-xs text-theme-text outline-none focus:border-theme-primary"
          />
          <span v-if="fieldDescription(schema)" class="text-[10px] leading-snug text-theme-text-muted">
            {{ fieldDescription(schema) }}
          </span>
        </label>
      </div>

      <label v-else class="grid gap-1">
        <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
          {{ t('playbooks.canvas.nodeConfig') }}
        </span>
        <textarea
          v-model="configText"
          data-test="playbook-node-config"
          class="min-h-[120px] resize-none rounded border border-theme-border bg-theme-panel p-2 font-mono text-[11px] text-theme-text outline-none focus:border-theme-primary"
          spellcheck="false"
        />
      </label>
      <div v-if="error" class="text-xs text-red-300">{{ error }}</div>
      <button
        v-if="nodeTypeDefinition?.exampleConfig"
        type="button"
        data-test="playbook-node-config-apply-example"
        class="rounded border border-theme-border bg-theme-panel px-2 py-1 text-xs font-semibold text-theme-text-muted hover:text-theme-text"
        @click="applyExampleConfig"
      >
        {{ t('playbooks.canvas.applyExampleConfig') }}
      </button>
      <button
        type="button"
        data-test="playbook-node-config-apply"
        class="rounded border border-theme-primary/40 bg-theme-primary/10 px-2 py-1 text-xs font-semibold text-theme-primary hover:bg-theme-primary/20"
        @click="applyConfig"
      >
        {{ t('playbooks.canvas.applyConfig') }}
      </button>
    </template>
    <div v-else class="text-xs text-theme-text-muted">
      {{ t('playbooks.canvas.selectNode') }}
    </div>
  </aside>
</template>
