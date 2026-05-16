<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bot, KeyRound, Save, Terminal } from 'lucide-vue-next'
import {
  type AiPreferenceMode,
  type AiPreferenceResponse,
  getAiPreferences,
  updateAiPreferences,
} from '../../services/aiPreferencesClient'

type ProviderOption = {
  id: string
  label: string
  defaultModel: string
  enabled: boolean
  hint?: string
}

const PROVIDERS: ProviderOption[] = [
  {
    id: 'gemini',
    label: 'Google Gemini',
    defaultModel: 'gemini-flash-latest',
    enabled: true,
    hint: 'Pegue a key em https://aistudio.google.com/apikey',
  },
  { id: 'anthropic', label: 'Anthropic Claude', defaultModel: 'claude-haiku-4-5-20251001', enabled: false },
  { id: 'openai', label: 'OpenAI / Codex', defaultModel: 'gpt-4o-mini', enabled: false },
]

const state = ref<AiPreferenceResponse>({
  mode: 'api',
  provider: 'gemini',
  model: 'gemini-flash-latest',
  apiKeySet: false,
  cliBinary: '',
  updatedAt: null,
})
const apiKeyDraft = ref('')
const isLoading = ref(true)
const isSaving = ref(false)
const error = ref<string | null>(null)
const saved = ref(false)

async function load() {
  isLoading.value = true
  error.value = null
  try {
    state.value = await getAiPreferences()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    isLoading.value = false
  }
}

onMounted(load)

function selectProvider(id: string) {
  const option = PROVIDERS.find((p) => p.id === id)
  if (!option || !option.enabled) return
  state.value.provider = id
  if (!state.value.model) state.value.model = option.defaultModel
}

function selectMode(mode: AiPreferenceMode) {
  state.value.mode = mode
}

async function save() {
  isSaving.value = true
  error.value = null
  saved.value = false
  try {
    const update = {
      mode: state.value.mode,
      provider: state.value.provider,
      model: state.value.model,
      cliBinary: state.value.cliBinary,
      ...(apiKeyDraft.value ? { apiKey: apiKeyDraft.value } : {}),
    }
    state.value = await updateAiPreferences(update)
    apiKeyDraft.value = ''
    saved.value = true
    window.setTimeout(() => (saved.value = false), 2200)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    isSaving.value = false
  }
}

async function clearApiKey() {
  isSaving.value = true
  try {
    state.value = await updateAiPreferences({ apiKey: '' })
    apiKeyDraft.value = ''
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-2 text-sm">
    <header class="flex items-center gap-2">
      <Bot class="h-5 w-5 text-theme-primary" />
      <div>
        <h3 class="text-lg font-semibold text-theme-text">Assistente IA</h3>
        <p class="text-xs text-theme-text-muted">
          Escolha entre IA por API (Gemini, Anthropic, OpenAI) ou IA via CLI local
          (Claude Code, Codex CLI). Configuração é por usuário e fica criptografada
          no servidor.
        </p>
      </div>
    </header>

    <p v-if="error" class="rounded border border-red-400/40 bg-red-950/20 p-2 text-xs text-red-200">
      {{ error }}
    </p>
    <p v-if="saved" class="rounded border border-emerald-400/40 bg-emerald-950/20 p-2 text-xs text-emerald-200">
      Preferências salvas.
    </p>

    <fieldset v-if="!isLoading" class="flex flex-col gap-2 rounded border border-theme-border p-3">
      <legend class="px-1 text-xs uppercase tracking-wide text-theme-text-muted">Modo</legend>
      <div class="flex gap-2">
        <button
          type="button"
          class="flex-1 rounded border px-3 py-2 text-left text-xs transition-colors"
          :class="state.mode === 'api'
            ? 'border-theme-primary bg-theme-primary/10 text-theme-primary'
            : 'border-theme-border text-theme-text hover:border-theme-primary/40'"
          @click="selectMode('api')"
        >
          <div class="flex items-center gap-2 font-semibold"><KeyRound class="h-3 w-3" /> API direta</div>
          <p class="mt-1 text-[11px] text-theme-text-muted">
            Backend salva sua key e chama o provider. Funciona em qualquer deploy.
          </p>
        </button>
        <button
          type="button"
          class="flex-1 rounded border px-3 py-2 text-left text-xs transition-colors"
          :class="state.mode === 'cli'
            ? 'border-theme-primary bg-theme-primary/10 text-theme-primary'
            : 'border-theme-border text-theme-text hover:border-theme-primary/40'"
          @click="selectMode('cli')"
        >
          <div class="flex items-center gap-2 font-semibold"><Terminal class="h-3 w-3" /> CLI local</div>
          <p class="mt-1 text-[11px] text-theme-text-muted">
            Reusa o login do <code>claude</code>/<code>codex</code> instalado no host. Requer cockpit fora do Docker (em breve).
          </p>
        </button>
      </div>
    </fieldset>

    <fieldset v-if="state.mode === 'api' && !isLoading" class="flex flex-col gap-3 rounded border border-theme-border p-3">
      <legend class="px-1 text-xs uppercase tracking-wide text-theme-text-muted">Provider</legend>
      <div class="flex flex-col gap-2">
        <label
          v-for="provider in PROVIDERS"
          :key="provider.id"
          class="flex items-start gap-2 rounded border px-2 py-2 transition-colors"
          :class="state.provider === provider.id
            ? 'border-theme-primary bg-theme-primary/5'
            : 'border-theme-border'"
        >
          <input
            type="radio"
            name="ai-provider"
            class="mt-0.5"
            :value="provider.id"
            :checked="state.provider === provider.id"
            :disabled="!provider.enabled"
            @change="selectProvider(provider.id)"
          />
          <div class="flex-1">
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium text-theme-text">{{ provider.label }}</span>
              <span v-if="!provider.enabled" class="rounded bg-theme-border px-1.5 py-0.5 text-[10px] uppercase text-theme-text-muted">
                em breve
              </span>
            </div>
            <p v-if="provider.hint" class="mt-1 text-[11px] text-theme-text-muted">{{ provider.hint }}</p>
          </div>
        </label>
      </div>

      <label class="flex flex-col gap-1 text-xs">
        <span class="text-theme-text-muted">Modelo</span>
        <input
          v-model="state.model"
          type="text"
          placeholder="gemini-flash-latest"
          class="rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm"
        />
      </label>

      <label class="flex flex-col gap-1 text-xs">
        <span class="text-theme-text-muted">
          Chave de API
          <span v-if="state.apiKeySet" class="ml-1 rounded bg-emerald-500/15 px-1 py-0.5 text-[10px] uppercase text-emerald-200">
            salva
          </span>
        </span>
        <input
          v-model="apiKeyDraft"
          type="password"
          autocomplete="off"
          :placeholder="state.apiKeySet ? '••• key salva, deixe vazio pra manter' : 'AIzaSy… / sk-… / etc'"
          class="rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm font-mono"
        />
        <p class="text-[11px] text-theme-text-muted">
          A chave é criptografada com a master key do servidor antes de ir pro Postgres.
          Nunca volta plain-text no GET.
        </p>
        <button
          v-if="state.apiKeySet"
          type="button"
          class="self-start text-[11px] text-red-300 hover:underline"
          @click="clearApiKey"
        >
          Remover key salva
        </button>
      </label>
    </fieldset>

    <fieldset v-if="state.mode === 'cli' && !isLoading" class="flex flex-col gap-2 rounded border border-amber-500/30 bg-amber-950/15 p-3 text-amber-100">
      <legend class="px-1 text-xs uppercase tracking-wide text-amber-300">CLI local</legend>
      <p class="text-xs">
        Em breve: o backend vai chamar <code>claude -p ...</code> /
        <code>codex --prompt ...</code> via subprocess, reusando o auth no
        <code>~/.config</code>. Funciona apenas quando o cockpit roda fora do
        container Docker (modo dev nativo).
      </p>
      <label class="flex flex-col gap-1 text-xs">
        <span>Binário CLI (opcional, ex.: /usr/local/bin/claude)</span>
        <input
          v-model="state.cliBinary"
          type="text"
          placeholder="/usr/local/bin/claude"
          class="rounded border border-amber-500/40 bg-amber-950/30 px-2 py-1 text-sm"
        />
      </label>
    </fieldset>

    <footer class="flex items-center justify-between gap-2 border-t border-theme-border pt-3">
      <span v-if="state.updatedAt" class="text-[11px] text-theme-text-muted">
        Última atualização: {{ state.updatedAt }}
      </span>
      <button
        type="button"
        class="inline-flex items-center gap-2 rounded bg-theme-primary px-3 py-1.5 text-sm font-medium text-theme-on-primary disabled:opacity-50"
        :disabled="isSaving || isLoading"
        @click="save"
      >
        <Save class="h-3 w-3" />
        Salvar
      </button>
    </footer>
  </section>
</template>
