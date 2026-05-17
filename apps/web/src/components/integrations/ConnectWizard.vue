<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from 'lucide-vue-next'
import { useIntegrationConnectStore, type CatalogEntry } from '../../stores/useIntegrationConnectStore'
import { useIntegrationsStore } from '../../stores/useIntegrationsStore'

const { t } = useI18n()
const connectStore = useIntegrationConnectStore()
const integrationsStore = useIntegrationsStore()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'openMarketplace'): void
}>()

const step = ref(1)
const selected = ref<CatalogEntry | null>(null)
const version = ref('')
const name = ref('')
const auth = reactive<Record<string, unknown>>({})
const wire = reactive({ siem: true, soar: true })
const testResult = ref<{
  ok: boolean
  device?: Record<string, unknown>
  message?: string
} | null>(null)
const wiringResult = ref<{
  siem?: { ok: boolean; detail?: string } | null
  soar?: { ok: boolean; detail?: string } | null
} | null>(null)
const busy = ref(false)
const errorMsg = ref<string | null>(null)

onMounted(() => connectStore.fetchCatalog())

const header = computed(() => (
  selected.value && version.value
    ? `${selected.value.name} ${version.value}`
    : t('integrations.wizard.title')
))

function pick(entry: CatalogEntry) {
  selected.value = entry
  version.value = entry.versions[0] ?? ''
  name.value = entry.name
  errorMsg.value = null
  testResult.value = null
  wiringResult.value = null
  for (const field of entry.authFields) {
    auth[field.id] = field.default ?? (field.type === 'boolean' ? false : '')
  }
}

function next() {
  step.value += 1
}

function back() {
  step.value = Math.max(1, step.value - 1)
}

async function runTest() {
  if (!selected.value) return
  busy.value = true
  errorMsg.value = null
  const res = await connectStore.testConnection({
    addonId: selected.value.addonId,
    version: version.value,
    name: name.value,
    auth: { ...auth },
  })
  busy.value = false
  if (res.success) {
    testResult.value = res.data
    step.value = 4
  } else {
    errorMsg.value = res.error
    testResult.value = { ok: false, message: res.error }
  }
}

async function finish() {
  if (!selected.value) return
  busy.value = true
  errorMsg.value = null
  const res = await connectStore.connect({
    addonId: selected.value.addonId,
    version: version.value,
    name: name.value,
    auth: { ...auth },
    wire: { siem: wire.siem, soar: wire.soar },
  })
  busy.value = false
  if (res.success) {
    wiringResult.value = res.data.wiring ?? null
    await integrationsStore.fetchIntegrations()
    step.value = 5
  } else {
    errorMsg.value = res.error
  }
}
</script>

<template>
  <section class="connect-wizard">
    <header class="connect-wizard__header">
      <h2>{{ header }}</h2>
      <button
        type="button"
        class="connect-wizard__close"
        :aria-label="t('common.close')"
        :title="t('common.close')"
        @click="emit('close')"
      >
        <X :size="14" aria-hidden="true" />
      </button>
    </header>

    <p v-if="errorMsg" class="connect-wizard__error" data-test="error">
      {{ errorMsg }}
    </p>

    <section v-if="step === 1" class="connect-wizard__step">
      <p v-if="connectStore.isLoading" class="connect-wizard__muted">
        {{ t('integrations.loading') }}
      </p>
      <p v-else-if="connectStore.catalog.length === 0" class="connect-wizard__empty" data-test="empty">
        {{ t('integrations.wizard.empty') }}
        <button type="button" class="connect-wizard__link" @click="emit('openMarketplace')">
          {{ t('integrations.wizard.goMarketplace') }}
        </button>
      </p>
      <ul v-else class="connect-wizard__addons">
        <li v-for="entry in connectStore.catalog" :key="entry.addonId">
          <button
            type="button"
            :data-test="`addon-${entry.addonId}`"
            class="connect-wizard__addon"
            :class="{ 'connect-wizard__addon--active': selected?.addonId === entry.addonId }"
            @click="pick(entry)"
          >
            <span>{{ entry.name }}</span>
            <small>{{ entry.vendor }} · {{ entry.category }}</small>
          </button>
        </li>
      </ul>
      <div class="connect-wizard__actions">
        <button type="button" data-test="next" :disabled="!selected" @click="next">
          {{ t('integrations.wizard.next') }}
        </button>
      </div>
    </section>

    <section v-else-if="step === 2" class="connect-wizard__step">
      <label class="connect-wizard__field">
        <span>{{ t('integrations.wizard.version') }}</span>
        <select v-model="version" data-test="version">
          <option v-for="item in selected?.versions ?? []" :key="item" :value="item">
            {{ item }}
          </option>
        </select>
      </label>
      <div class="connect-wizard__actions">
        <button type="button" data-test="back" @click="back">
          {{ t('integrations.wizard.back') }}
        </button>
        <button type="button" data-test="next" :disabled="!version" @click="next">
          {{ t('integrations.wizard.next') }}
        </button>
      </div>
    </section>

    <section v-else-if="step === 3" class="connect-wizard__step">
      <label class="connect-wizard__field">
        <span>{{ t('integrations.wizard.name') }}</span>
        <input v-model="name" data-test="conn-name">
      </label>
      <label
        v-for="field in selected?.authFields ?? []"
        :key="field.id"
        class="connect-wizard__field"
      >
        <span>{{ field.label }}</span>
        <input
          v-if="field.type === 'boolean'"
          v-model="auth[field.id]"
          type="checkbox"
          :data-test="`auth-${field.id}`"
        >
        <input
          v-else
          v-model="auth[field.id]"
          :type="field.type === 'secret' ? 'password' : field.type === 'number' ? 'number' : 'text'"
          :placeholder="field.placeholder ?? undefined"
          :data-test="`auth-${field.id}`"
        >
      </label>
      <div class="connect-wizard__actions">
        <button type="button" data-test="back" @click="back">
          {{ t('integrations.wizard.back') }}
        </button>
        <button type="button" data-test="test" :disabled="busy" @click="runTest">
          {{ t('integrations.wizard.test') }}
        </button>
      </div>
    </section>

    <section v-else-if="step === 4" class="connect-wizard__step">
      <p class="connect-wizard__device" data-test="device">
        {{ testResult?.device?.hostname ?? testResult?.message }}
      </p>
      <label v-if="selected?.capabilities.logSource" class="connect-wizard__toggle">
        <input v-model="wire.siem" type="checkbox" data-test="wire-siem">
        <span>{{ t('integrations.wizard.wireSiem') }}</span>
      </label>
      <label v-if="selected?.capabilities.playbookTarget" class="connect-wizard__toggle">
        <input v-model="wire.soar" type="checkbox" data-test="wire-soar">
        <span>{{ t('integrations.wizard.wireSoar') }}</span>
      </label>
      <div class="connect-wizard__actions">
        <button type="button" data-test="back" @click="step = 3">
          {{ t('integrations.wizard.back') }}
        </button>
        <button type="button" data-test="finish" :disabled="busy" @click="finish">
          {{ t('integrations.wizard.connect') }}
        </button>
      </div>
    </section>

    <section v-else-if="step === 5" class="connect-wizard__step">
      <p
        v-if="wiringResult?.siem"
        class="connect-wizard__result"
        :class="wiringResult.siem.ok ? 'connect-wizard__result--ok' : 'connect-wizard__result--amber'"
        data-test="wiring-siem"
      >
        <strong>{{ t('integrations.wizard.wiringSiem') }}:</strong>
        {{ wiringResult.siem.detail }}
      </p>
      <p
        v-if="wiringResult?.soar"
        class="connect-wizard__result"
        :class="wiringResult.soar.ok ? 'connect-wizard__result--ok' : 'connect-wizard__result--amber'"
        data-test="wiring-soar"
      >
        <strong>{{ t('integrations.wizard.wiringSoar') }}:</strong>
        {{ wiringResult.soar.detail }}
      </p>
      <div class="connect-wizard__actions">
        <button type="button" data-test="done" @click="emit('close')">
          {{ t('integrations.wizard.done') }}
        </button>
      </div>
    </section>
  </section>
</template>

<style scoped>
.connect-wizard {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  border: 1px solid rgb(75 85 99 / 0.7);
  border-radius: 0.5rem;
  padding: 0.875rem;
}

.connect-wizard__header,
.connect-wizard__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.connect-wizard__header h2 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
}

.connect-wizard__close {
  width: 1.75rem;
  height: 1.75rem;
  border: 1px solid rgb(75 85 99 / 0.8);
  border-radius: 0.375rem;
}

.connect-wizard__step,
.connect-wizard__field {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.connect-wizard__addons {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.connect-wizard__addon {
  display: flex;
  width: 100%;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
  border: 1px solid rgb(75 85 99 / 0.8);
  border-radius: 0.5rem;
  padding: 0.625rem;
  text-align: left;
}

.connect-wizard__addon--active {
  border-color: rgb(34 197 94 / 0.8);
}

.connect-wizard__addon small,
.connect-wizard__muted {
  color: rgb(156 163 175);
}

.connect-wizard__field span,
.connect-wizard__toggle span {
  font-size: 0.75rem;
  color: rgb(209 213 219);
}

.connect-wizard__field input,
.connect-wizard__field select {
  width: 100%;
}

.connect-wizard__toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.connect-wizard__empty,
.connect-wizard__error,
.connect-wizard__device {
  margin: 0;
  font-size: 0.8rem;
}

.connect-wizard__error {
  color: rgb(252 165 165);
}

.connect-wizard__link {
  color: rgb(96 165 250);
  text-decoration: underline;
}

.connect-wizard__result {
  margin: 0;
  border: 1px solid rgb(75 85 99 / 0.7);
  border-radius: 0.375rem;
  padding: 0.5rem;
  font-size: 0.8rem;
}

.connect-wizard__result--ok {
  border-color: rgb(34 197 94 / 0.55);
  color: rgb(187 247 208);
}

.connect-wizard__result--amber {
  border-color: rgb(245 158 11 / 0.65);
  color: rgb(253 230 138);
}
</style>
