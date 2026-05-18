<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Bot, CheckCircle2, KeyRound, PlugZap, Save, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useSocAssistantSettingsStore } from '../../stores/useSocAssistantSettingsStore'

type ProviderOption = {
  id: 'anthropic' | 'gemini' | 'openai'
  label: string
  defaultModel: string
}

const PROVIDERS: ProviderOption[] = [
  { id: 'anthropic', label: 'Anthropic', defaultModel: 'claude-sonnet-4-6' },
  { id: 'gemini', label: 'Gemini', defaultModel: 'gemini-flash-latest' },
  { id: 'openai', label: 'OpenAI', defaultModel: 'gpt-4o' },
]

const store = useSocAssistantSettingsStore()
const { t, locale } = useI18n()

const provider = ref<ProviderOption['id']>('anthropic')
const model = ref('claude-sonnet-4-6')
const apiKeyDraft = ref('')
const saved = ref(false)

const selectedProvider = computed(() => (
  PROVIDERS.find((option) => option.id === provider.value) ?? PROVIDERS[0]
))

const savedProviderId = computed<ProviderOption['id']>(() => {
  const knownProvider = PROVIDERS.find((option) => option.id === store.settings?.provider)
  return knownProvider?.id ?? 'anthropic'
})

const savedModel = computed(() => {
  const knownProvider = PROVIDERS.find((option) => option.id === store.settings?.provider)
  return store.settings?.model || knownProvider?.defaultModel || PROVIDERS[0].defaultModel
})

const hasUnsavedFormChanges = computed(() => (
  provider.value !== savedProviderId.value
  || model.value.trim() !== savedModel.value
  || apiKeyDraft.value.length > 0
))

const canSave = computed(() => (
  !store.isLoading
  && !store.isSaving
  && !store.isTesting
  && provider.value.length > 0
  && model.value.trim().length > 0
))

const updatedAtLabel = computed(() => formatDateTime(store.settings?.updatedAt ?? null))
const lastTestedAtLabel = computed(() => formatDateTime(store.settings?.lastTestedAt ?? null))

function syncFromSettings() {
  provider.value = savedProviderId.value
  model.value = savedModel.value
  apiKeyDraft.value = ''
}

function formatDateTime(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

function selectProvider(id: ProviderOption['id']) {
  const previousDefaultModel = selectedProvider.value.defaultModel
  provider.value = id
  const option = PROVIDERS.find((item) => item.id === id)
  if (option && (!model.value.trim() || model.value === previousDefaultModel)) {
    model.value = option.defaultModel
  }
}

function testStatusLabel(status: string | null | undefined): string {
  if (!status) return t('settings.ai.testStatus.never')
  const keys: Record<string, string> = {
    configured: 'settings.ai.testStatus.configured',
    not_configured: 'settings.ai.testStatus.not_configured',
    success: 'settings.ai.testStatus.success',
    failed: 'settings.ai.testStatus.failed',
  }
  return t(keys[status] ?? 'settings.ai.testStatus.failed')
}

async function save() {
  saved.value = false
  const payload: { provider: string; model: string; apiKey?: string } = {
    provider: provider.value,
    model: model.value.trim(),
  }
  if (apiKeyDraft.value.length > 0) payload.apiKey = apiKeyDraft.value
  const result = await store.save(payload)
  if (result) {
    apiKeyDraft.value = ''
    saved.value = true
    window.setTimeout(() => {
      saved.value = false
    }, 2200)
  }
}

async function clearApiKey() {
  saved.value = false
  const result = await store.save({
    provider: provider.value,
    model: model.value.trim(),
    apiKey: '',
  })
  if (result) {
    apiKeyDraft.value = ''
    saved.value = true
    window.setTimeout(() => {
      saved.value = false
    }, 2200)
  }
}

async function testConnection() {
  await store.testConnection()
}

watch(() => store.settings, () => {
  if (!hasUnsavedFormChanges.value) syncFromSettings()
})

onMounted(async () => {
  await store.load()
  syncFromSettings()
})
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-2 text-sm">
    <header class="flex items-center gap-2">
      <Bot class="h-5 w-5 text-theme-primary" />
      <div>
        <h3 class="text-lg font-semibold text-theme-text">{{ t('settings.ai.title') }}</h3>
        <p class="text-xs text-theme-text-muted">{{ t('settings.ai.subtitle') }}</p>
      </div>
    </header>

    <p
      v-if="store.error"
      class="rounded border border-red-400/40 bg-red-950/20 p-2 text-xs text-red-200"
    >
      {{ store.error }}
    </p>
    <p
      v-if="saved"
      class="flex items-center gap-2 rounded border border-emerald-400/40 bg-emerald-950/20 p-2 text-xs text-emerald-200"
    >
      <CheckCircle2 class="h-3.5 w-3.5" />
      {{ t('settings.ai.saved') }}
    </p>

    <div v-if="store.isLoading && !store.settings" class="rounded border border-theme-border p-3 text-xs text-theme-text-muted">
      {{ t('settings.ai.loading') }}
    </div>

    <template v-else>
      <fieldset class="flex flex-col gap-3 rounded border border-theme-border p-3">
        <legend class="px-1 text-xs uppercase tracking-wide text-theme-text-muted">
          {{ t('settings.ai.providerLegend') }}
        </legend>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <label
            v-for="option in PROVIDERS"
            :key="option.id"
            class="flex cursor-pointer items-start gap-2 rounded border px-2 py-2 transition-colors"
            :class="provider === option.id
              ? 'border-theme-primary bg-theme-primary/5'
              : 'border-theme-border hover:border-theme-primary/40'"
          >
            <input
              type="radio"
              name="soc-assistant-provider"
              class="mt-0.5"
              :value="option.id"
              :checked="provider === option.id"
              @change="selectProvider(option.id)"
            />
            <span>
              <span class="block text-sm font-medium text-theme-text">{{ option.label }}</span>
              <span class="block text-[11px] text-theme-text-muted">
                {{ t('settings.ai.defaultModel', { model: option.defaultModel }) }}
              </span>
            </span>
          </label>
        </div>

        <label class="flex flex-col gap-1 text-xs">
          <span class="text-theme-text-muted">{{ t('settings.ai.modelLabel') }}</span>
          <input
            v-model="model"
            type="text"
            data-test="soc-assistant-model"
            :placeholder="selectedProvider.defaultModel"
            class="rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm"
          />
        </label>

        <label class="flex flex-col gap-1 text-xs">
          <span class="flex items-center gap-2 text-theme-text-muted">
            <KeyRound class="h-3.5 w-3.5" />
            {{ t('settings.ai.apiKeyLabel') }}
            <span
              v-if="store.settings?.apiKeySet"
              class="rounded bg-emerald-500/15 px-1 py-0.5 text-[10px] uppercase text-emerald-200"
            >
              {{ t('settings.ai.apiKeySavedBadge') }}
            </span>
          </span>
          <input
            v-model="apiKeyDraft"
            type="password"
            autocomplete="off"
            data-test="soc-assistant-api-key"
            :placeholder="store.settings?.apiKeySet
              ? t('settings.ai.apiKeyPlaceholderSaved')
              : t('settings.ai.apiKeyPlaceholderEmpty')"
            class="rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm font-mono"
          />
          <p class="text-[11px] text-theme-text-muted">{{ t('settings.ai.apiKeyHint') }}</p>
          <button
            v-if="store.settings?.apiKeySet"
            type="button"
            class="inline-flex items-center gap-1 self-start text-[11px] text-red-300 hover:underline disabled:opacity-50"
            :disabled="store.isSaving"
            @click="clearApiKey"
          >
            <Trash2 class="h-3 w-3" />
            {{ t('settings.ai.clearApiKey') }}
          </button>
        </label>
      </fieldset>

      <section class="rounded border border-theme-border p-3">
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div>
            <span class="block text-theme-text-muted">{{ t('settings.ai.configuredLabel') }}</span>
            <span
              class="mt-1 inline-flex rounded px-1.5 py-0.5 text-[11px]"
              :class="store.settings?.configured
                ? 'bg-emerald-500/15 text-emerald-200'
                : 'bg-amber-500/15 text-amber-100'"
            >
              {{ store.settings?.configured ? t('settings.ai.configuredYes') : t('settings.ai.configuredNo') }}
            </span>
          </div>
          <div>
            <span class="block text-theme-text-muted">{{ t('settings.ai.lastTestStatusLabel') }}</span>
            <span class="mt-1 block text-theme-text">
              {{ testStatusLabel(store.settings?.lastTestStatus) }}
            </span>
          </div>
          <div v-if="updatedAtLabel">
            <span class="block text-theme-text-muted">{{ t('settings.ai.updatedAtLabel') }}</span>
            <span class="mt-1 block text-theme-text">{{ updatedAtLabel }}</span>
          </div>
          <div v-if="lastTestedAtLabel">
            <span class="block text-theme-text-muted">{{ t('settings.ai.lastTestedAtLabel') }}</span>
            <span class="mt-1 block text-theme-text">{{ lastTestedAtLabel }}</span>
          </div>
          <div v-if="store.settings?.updatedBy" class="col-span-2">
            <span class="block text-theme-text-muted">{{ t('settings.ai.updatedByLabel') }}</span>
            <span class="mt-1 block break-all font-mono text-theme-text">{{ store.settings.updatedBy }}</span>
          </div>
        </div>
        <p v-if="store.settings?.lastTestError" class="mt-3 rounded border border-red-400/30 bg-red-950/20 p-2 text-xs text-red-200">
          {{ store.settings.lastTestError }}
        </p>
        <p
          v-if="store.testResult"
          class="mt-3 rounded border p-2 text-xs"
          :class="store.testResult.ok
            ? 'border-emerald-400/40 bg-emerald-950/20 text-emerald-200'
            : 'border-red-400/40 bg-red-950/20 text-red-200'"
        >
          {{ store.testResult.ok
            ? t('settings.ai.testOk')
            : (store.testResult.error || t('settings.ai.testFailed')) }}
        </p>
      </section>

      <footer class="flex items-center justify-between gap-2 border-t border-theme-border pt-3">
        <button
          type="button"
          data-test="soc-assistant-test"
          class="inline-flex items-center gap-2 rounded border border-theme-border px-3 py-1.5 text-sm text-theme-text hover:border-theme-primary/40 disabled:opacity-50"
          :disabled="store.isTesting || store.isSaving"
          @click="testConnection"
        >
          <PlugZap class="h-3.5 w-3.5" />
          {{ store.isTesting ? t('settings.ai.testing') : t('settings.ai.testConnection') }}
        </button>
        <button
          type="button"
          data-test="soc-assistant-save"
          class="inline-flex items-center gap-2 rounded bg-theme-primary px-3 py-1.5 text-sm font-medium text-theme-on-primary disabled:opacity-50"
          :disabled="!canSave"
          @click="save"
        >
          <Save class="h-3.5 w-3.5" />
          {{ store.isSaving ? t('settings.ai.saving') : t('settings.ai.save') }}
        </button>
      </footer>
    </template>
  </section>
</template>
