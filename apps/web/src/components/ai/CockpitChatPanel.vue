<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import {
  AlertCircle,
  BarChart2,
  Bot,
  CheckCircle2,
  Gauge,
  LayoutDashboard,
  PlusCircle,
  Send,
  Table,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import {
  sendCockpitChat,
  type ChatTurn,
  type WidgetDraftResponse,
} from '../../services/cockpitChatClient'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { renderSafeMarkdown } from '../../lib/markdown'

type Message = {
  role: 'user' | 'assistant'
  content: string
  widgetDrafts?: WidgetDraftResponse[]
}

const { locale } = useI18n()
const dashboardStore = useDashboardStore()

const messages = ref<Message[]>([])
const inputDraft = ref('')
const isLoading = ref(false)
const error = ref<string | null>(null)
const addedKeys = ref(new Set<string>())
const scrollEl = ref<HTMLElement | null>(null)

const canSend = computed(() => inputDraft.value.trim().length > 0 && !isLoading.value)

function draftKey(wd: WidgetDraftResponse, msgIdx: number) {
  return `${msgIdx}-${wd.draft.visualType}-${wd.draft.title}`
}

async function scrollToBottom() {
  await nextTick()
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
}

async function submit() {
  if (!canSend.value) return
  const content = inputDraft.value.trim()
  inputDraft.value = ''
  error.value = null

  const history: ChatTurn[] = messages.value.map(m => ({ role: m.role, content: m.content }))
  messages.value.push({ role: 'user', content })
  await scrollToBottom()

  isLoading.value = true
  try {
    const res = await sendCockpitChat([...history, { role: 'user', content }], locale.value)
    messages.value.push({
      role: 'assistant',
      content: res.reply,
      widgetDrafts: res.widgetDrafts ?? [],
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

function addToWorkspace(wd: WidgetDraftResponse, key: string) {
  dashboardStore.addWidgetDraft(wd.draft)
  addedKeys.value.add(key)
}

function visualIcon(type: string) {
  if (type === 'bar') return BarChart2
  if (type === 'table') return Table
  if (type === 'gauge') return Gauge
  return LayoutDashboard
}

const VISUAL_LABELS: Record<string, string> = {
  card: 'Card',
  kpi: 'KPI',
  gauge: 'Gauge',
  bar: 'Bar Chart',
  table: 'Tabela',
  feed: 'Feed',
  'status-list': 'Status',
  'risk-summary': 'Risk',
}

function visualLabel(type: string) {
  return VISUAL_LABELS[type] ?? type
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3 p-3 text-sm">
    <!-- Header -->
    <header class="flex items-center gap-2 border-b border-theme-border pb-2">
      <Bot class="h-4 w-4 text-theme-primary" />
      <span class="font-semibold text-theme-text">Assistente de Widgets</span>
    </header>

    <!-- Error -->
    <p
      v-if="error"
      class="rounded border border-red-400/40 bg-red-950/20 p-2 text-xs text-red-200"
    >
      {{ error }}
    </p>

    <!-- Message list -->
    <div
      ref="scrollEl"
      class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto rounded border border-theme-border bg-theme-surface/40 p-2"
    >
      <p v-if="messages.length === 0" class="text-xs text-theme-text-muted">
        Descreva o widget que quer criar.<br />
        Ex: <em>"crie um card com system.cpu do FortiGate"</em>
      </p>

      <template v-for="(msg, idx) in messages" :key="idx">
        <!-- User bubble -->
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <span class="max-w-[85%] rounded-lg bg-theme-primary/20 px-3 py-2 text-xs text-theme-text">
            {{ msg.content }}
          </span>
        </div>

        <!-- Assistant reply -->
        <div v-else class="flex flex-col gap-2">
          <div class="flex items-start gap-2">
            <Bot class="mt-0.5 h-3 w-3 shrink-0 text-theme-primary" />
            <div
              class="agent-markdown text-xs text-theme-text"
              v-html="renderSafeMarkdown(msg.content)"
            />
          </div>

          <!-- Widget draft preview cards -->
          <div
            v-for="(wd, wi) in msg.widgetDrafts"
            :key="wi"
            class="ml-5 rounded-lg border border-theme-primary/30 bg-theme-primary/5 p-3"
          >
            <!-- Title row -->
            <div class="flex items-center gap-2">
              <component
                :is="visualIcon(wd.draft.visualType)"
                class="h-4 w-4 shrink-0 text-theme-primary"
              />
              <span class="text-xs font-semibold text-theme-text">{{ wd.draft.title }}</span>
              <span class="rounded bg-theme-primary/15 px-1.5 py-0.5 text-[10px] text-theme-primary">
                {{ visualLabel(wd.draft.visualType) }}
              </span>
            </div>

            <!-- Fields -->
            <ul class="mt-2 flex flex-wrap gap-1">
              <li
                v-for="binding in wd.draft.fieldBindings"
                :key="binding.fieldId"
                class="rounded bg-theme-surface px-1.5 py-0.5 text-[10px] text-theme-text-muted"
              >
                {{ binding.label }}
                <span v-if="binding.unit" class="opacity-60">({{ binding.unit }})</span>
              </li>
            </ul>

            <!-- Validation warnings -->
            <div
              v-if="wd.validation.warnings.length"
              class="mt-2 flex items-center gap-1 text-[10px] text-amber-300"
            >
              <AlertCircle class="h-3 w-3 shrink-0" />
              {{ wd.validation.warnings.join('; ') }}
            </div>

            <!-- Add to workspace button -->
            <button
              type="button"
              class="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-default"
              :class="
                addedKeys.has(draftKey(wd, idx))
                  ? 'bg-emerald-600/20 text-emerald-300'
                  : 'bg-theme-primary text-theme-on-primary hover:opacity-90'
              "
              :disabled="addedKeys.has(draftKey(wd, idx))"
              @click="addToWorkspace(wd, draftKey(wd, idx))"
            >
              <CheckCircle2 v-if="addedKeys.has(draftKey(wd, idx))" class="h-3.5 w-3.5" />
              <PlusCircle v-else class="h-3.5 w-3.5" />
              {{ addedKeys.has(draftKey(wd, idx)) ? 'Adicionado à workspace' : 'Adicionar à workspace' }}
            </button>
          </div>
        </div>
      </template>

      <p v-if="isLoading" class="animate-pulse text-[10px] text-theme-text-muted">
        Processando…
      </p>
    </div>

    <!-- Input form -->
    <form class="flex items-center gap-2" @submit.prevent="submit">
      <input
        v-model="inputDraft"
        type="text"
        placeholder="Descreva o widget…"
        class="flex-1 rounded border border-theme-border bg-theme-surface px-2 py-1 text-sm"
        :disabled="isLoading"
      />
      <button
        type="submit"
        class="inline-flex items-center gap-1 rounded bg-theme-primary px-3 py-1 text-sm font-medium text-theme-on-primary disabled:opacity-50"
        :disabled="!canSend"
      >
        <Send class="h-3 w-3" />
        Enviar
      </button>
    </form>
  </section>
</template>

<style scoped>
.agent-markdown :deep(p) {
  margin: 0.2rem 0;
}
.agent-markdown :deep(code) {
  background: rgb(0 0 0 / 0.3);
  border-radius: 0.2rem;
  padding: 0.05rem 0.25rem;
  font-size: 0.7rem;
}
.agent-markdown :deep(strong) {
  font-weight: 600;
}
</style>
