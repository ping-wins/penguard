<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Bot, Check, Hammer, Play, Send, ShieldAlert, Trash2, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useAiAgentStore } from '../../stores/useAiAgentStore'

const store = useAiAgentStore()
const { t, locale } = useI18n()
const draft = ref('')

onMounted(async () => {
  await store.ensureCatalog()
})

onBeforeUnmount(() => {
  store.endSession()
})

const canSend = computed(
  () => draft.value.trim().length > 0 && !store.isStreaming,
)

async function start() {
  await store.startSession({ locale: locale.value })
}

async function submit() {
  if (!canSend.value) return
  const content = draft.value.trim()
  draft.value = ''
  await store.sendMessage(content)
}

function previewResult(value: unknown, limit = 320): string {
  if (value === null || value === undefined) return t('aiAgent.resultEmpty')
  try {
    const text = typeof value === 'string' ? value : JSON.stringify(value)
    return text.length > limit ? `${text.slice(0, limit - 1)}…` : text
  } catch {
    return String(value)
  }
}

const pendingApprovalTool = computed(() => {
  if (!store.pendingApproval) return null
  return store.tools.find((tool) => tool.name === store.pendingApproval?.toolName) ?? null
})

const pendingApprovalRisk = computed(() => {
  const tool = pendingApprovalTool.value
  if (tool?.category === 'execute') return t('aiAgent.approvalRiskExecute')
  if (tool?.category === 'write' || tool?.requiresApproval) return t('aiAgent.approvalRiskWrite')
  if (tool?.category === 'draft') return t('aiAgent.approvalRiskDraft')
  return t('aiAgent.approvalRiskRead')
})

const pendingApprovalPermissions = computed(() => {
  const permissions = pendingApprovalTool.value?.requiredPermissions ?? []
  return permissions.length ? permissions.join(', ') : t('aiAgent.noRequiredPermissions')
})

const pendingApprovalArgs = computed(() => previewResult(store.pendingApproval?.args ?? {}, 420))

const modelBadge = computed(() => {
  const model = store.session?.model || t('aiAgent.noModel')
  return t('aiAgent.modelBadge', {
    model,
    used: formatTokens(store.tokensIn + store.tokensOut),
  })
})

function formatTokens(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`
  return String(value)
}

</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3 p-3 text-sm">
    <header class="flex items-center justify-between gap-2 border-b border-theme-border pb-2">
      <div class="flex items-center gap-2">
        <Bot class="h-4 w-4 text-theme-primary" />
        <span class="font-semibold text-theme-text">{{ t('aiAgent.title') }}</span>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <button
          v-if="!store.session"
          type="button"
          class="inline-flex items-center gap-1 rounded bg-theme-primary px-2 py-1 text-xs font-medium text-theme-on-primary disabled:opacity-50"
          :disabled="store.isLoading"
          @click="start"
        >
          <Play class="h-3 w-3" />
          {{ t('aiAgent.start') }}
        </button>
        <button
          v-else
          type="button"
          class="inline-flex items-center gap-1 rounded border border-theme-border px-2 py-1 text-xs"
          :disabled="store.isStreaming"
          @click="store.endSession()"
        >
          <Trash2 class="h-3 w-3" />
          {{ t('aiAgent.end') }}
        </button>
      </div>
    </header>

    <div v-if="store.session" class="rounded border border-theme-border bg-theme-surface px-2 py-1 text-[11px] text-theme-text-muted">
      {{ modelBadge }}
    </div>

    <p v-if="store.error" class="rounded border border-red-400/40 bg-red-950/20 p-2 text-xs text-red-200">
      {{ store.error }}
    </p>

    <div
      v-if="store.pendingApproval"
      class="flex flex-col gap-3 rounded border border-amber-400/40 bg-amber-500/10 p-3 text-xs text-amber-100"
    >
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <ShieldAlert class="h-3.5 w-3.5 shrink-0 text-amber-200" />
            <p class="font-semibold">{{ t('aiAgent.approvalTitle') }}</p>
          </div>
          <p class="mt-1 break-all font-mono text-[11px]">{{ store.pendingApproval.toolName }}</p>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded bg-emerald-500 px-2 py-1 font-medium text-white"
            @click="store.approve(store.pendingApproval.callId, true)"
          >
            <Check class="h-3 w-3" />
            {{ t('aiAgent.approve') }}
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded border border-amber-300/60 px-2 py-1 font-medium"
            @click="store.approve(store.pendingApproval.callId, false)"
          >
            <X class="h-3 w-3" />
            {{ t('aiAgent.deny') }}
          </button>
        </div>
      </div>
      <dl class="grid gap-2 sm:grid-cols-2">
        <div>
          <dt class="text-[10px] font-medium uppercase text-amber-200/80">{{ t('aiAgent.approvalRiskLabel') }}</dt>
          <dd class="mt-0.5 text-theme-text">{{ pendingApprovalRisk }}</dd>
        </div>
        <div>
          <dt class="text-[10px] font-medium uppercase text-amber-200/80">{{ t('aiAgent.approvalPermissionsLabel') }}</dt>
          <dd class="mt-0.5 break-words font-mono text-[11px] text-theme-text">{{ pendingApprovalPermissions }}</dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-[10px] font-medium uppercase text-amber-200/80">{{ t('aiAgent.approvalReasonLabel') }}</dt>
          <dd class="mt-0.5 break-words text-theme-text">{{ store.pendingApproval.reason }}</dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-[10px] font-medium uppercase text-amber-200/80">{{ t('aiAgent.approvalArgsLabel') }}</dt>
          <dd class="mt-0.5 overflow-x-auto rounded bg-black/30 p-2 font-mono text-[11px] text-theme-text">
            {{ pendingApprovalArgs }}
          </dd>
        </div>
      </dl>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto rounded border border-theme-border bg-theme-surface/40 p-2">
      <div v-if="store.trace.length === 0" class="text-xs text-theme-text-muted">
        {{ t('aiAgent.empty') }}
      </div>
      <ol class="flex flex-col gap-2">
        <li
          v-for="(entry, idx) in store.trace"
          :key="`${entry.kind}-${idx}`"
          class="rounded border border-theme-border/60 bg-theme-bg/50 p-2"
        >
          <div v-if="entry.kind === 'user'" class="flex items-start gap-2">
            <span class="rounded bg-theme-primary/20 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-theme-primary">
              {{ t('common.you') }}
            </span>
            <p class="text-xs text-theme-text">{{ entry.content }}</p>
          </div>

          <div v-else-if="entry.kind === 'text'" class="flex items-start gap-2">
            <Bot class="mt-0.5 h-3 w-3 text-theme-primary" />
            <p class="whitespace-pre-wrap text-xs text-theme-text">{{ entry.text }}</p>
          </div>

          <div v-else-if="entry.kind === 'tool_call'" class="flex flex-col gap-1">
            <div class="flex items-center gap-2">
              <Hammer class="h-3 w-3 text-amber-300" />
              <span class="font-mono text-[11px] text-theme-text">{{ entry.toolName }}</span>
              <span
                v-if="entry.status"
                class="rounded px-1.5 py-0.5 text-[10px] uppercase"
                :class="entry.status === 'ok' ? 'bg-emerald-500/15 text-emerald-200' : 'bg-red-500/15 text-red-200'"
              >
                {{ entry.status }}
              </span>
              <span v-if="entry.latencyMs !== undefined" class="text-[10px] text-theme-text-muted">
                {{ entry.latencyMs }}ms
              </span>
            </div>
            <code v-if="Object.keys(entry.args).length" class="overflow-x-auto rounded bg-black/40 p-1.5 text-[10px] text-theme-text-muted">
              args: {{ previewResult(entry.args, 200) }}
            </code>
            <code v-if="entry.result !== undefined" class="overflow-x-auto rounded bg-black/40 p-1.5 text-[10px] text-theme-text">
              {{ previewResult(entry.result) }}
            </code>
            <p v-if="entry.error" class="text-[10px] text-red-300">{{ entry.error }}</p>
          </div>

          <div v-else-if="entry.kind === 'error'" class="text-xs text-red-300">
            <span class="font-mono text-[10px] uppercase">{{ entry.code }}</span>
            — {{ entry.message }}
          </div>
        </li>
      </ol>

      <p v-if="store.isStreaming" class="mt-2 text-[10px] text-theme-text-muted">
        {{ t('aiAgent.streaming') }}
      </p>
    </div>

    <form class="flex items-center gap-2" @submit.prevent="submit">
      <input
        v-model="draft"
        type="text"
        :placeholder="t('aiAgent.placeholder')"
        class="flex-1 rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm"
        :disabled="store.isStreaming"
      />
      <button
        type="submit"
        class="inline-flex items-center gap-1 rounded bg-theme-primary px-3 py-1 text-sm font-medium text-theme-on-primary disabled:opacity-50"
        :disabled="!canSend"
      >
        <Send class="h-3 w-3" />
        {{ t('aiAgent.send') }}
      </button>
    </form>
  </section>
</template>
