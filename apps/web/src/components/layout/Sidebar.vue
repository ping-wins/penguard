<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Bot, ChevronDown, ChevronRight, LayoutDashboard, Settings, Send, LogOut, Plug, Trash2, History, FolderTree, Ticket as TicketIcon, Server, RefreshCcw, Workflow } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { useAuthStore } from '../../stores/useAuthStore'
import { useIntegrationsStore } from '../../stores/useIntegrationsStore'
import { useAuditStore } from '../../stores/useAuditStore'
import { useTicketsStore } from '../../stores/useTicketsStore'
import {
  useCockpitLayoutStore,
  SIDEBAR_DRAWER_MAX_WIDTH,
  SIDEBAR_DRAWER_MIN_WIDTH,
} from '../../stores/useCockpitLayoutStore'
import { useDraggableEdge } from '../../composables/useDraggableEdge'
import { aiChat, aiStatus, type AIStatus, type WidgetDraftResponse } from '../../services/aiClient'
import { renderMarkdown } from '../../lib/markdown'
import AuditFeed from '../audit/AuditFeed.vue'
import AgentPanel from '../ai/AgentPanel.vue'
import WorkspacePanel from '../workspace/WorkspacePanel.vue'
import TicketsPanel from '../tickets/TicketsPanel.vue'
import EndpointsPanel from '../endpoints/EndpointsPanel.vue'
import ConnectWizard from '../integrations/ConnectWizard.vue'
import { useRouter } from 'vue-router'

const { t } = useI18n()
type MainSurface = 'workspace' | 'playbooks'
const props = withDefaults(defineProps<{
  activeSurface?: MainSurface
}>(), {
  activeSurface: 'workspace',
})
const emit = defineEmits<{
  'open-settings': [tab?: 'profile' | 'marketplace']
  'select-surface': [surface: MainSurface]
}>()

const store = useDashboardStore()
const authStore = useAuthStore()
const integrationsStore = useIntegrationsStore()
const auditStore = useAuditStore()
const ticketsStore = useTicketsStore()
const layoutStore = useCockpitLayoutStore()
const router = useRouter()
const activeTab = ref<'none' | 'assistant' | 'settings' | 'integrations' | 'audit' | 'workspaces' | 'tickets' | 'endpoints'>('none')
// Agent mode is gated behind a "coming soon" flag while the streaming
// runtime is still wired through Gemini's openai-compat layer.
const assistantMode = ref<'chat' | 'agent'>('chat')

const showWizard = ref(false)
const integrationError = ref<string | null>(null)
const fortiwebTelemetryTokens = ref<Record<string, string>>({})
const integrationGroupsOpen = ref({
  fortinet: true,
  penguin: true,
  endpoint: false,
})
const fortigateIntegrations = computed(() => {
  return integrationsStore.integrations.filter(integration => integration.type === 'fortigate')
})
const fortiwebIntegrations = computed(() => {
  return integrationsStore.integrations.filter(integration => integration.type === 'fortiweb')
})
const penguinIntegrations = computed(() => {
  return integrationsStore.integrations.filter(integration => (
    integration.type === 'siem_kowalski'
    || integration.type === 'xdr_rico'
    || integration.type === 'soar_skipper'
  ))
})
const isAdmin = computed(() => authStore.user?.roles.includes('admin') ?? false)
const auditScope = computed<'admin' | 'mine'>(() => isAdmin.value ? 'admin' : 'mine')
const auditTitle = computed(() => isAdmin.value ? t('audit.adminTitle') : t('audit.mineTitle'))
const auditSubtitle = computed(() => isAdmin.value ? t('audit.adminSubtitle') : t('audit.mineSubtitle'))
const drawerPx = computed(() => layoutStore.sidebarDrawerWidth)
const drawerWidth = computed(() => {
  if (activeTab.value === 'none') return '0px'
  return `${drawerPx.value}px`
})
const drawerResizer = useDraggableEdge({
  edge: 'right',
  getCurrent: () => layoutStore.sidebarDrawerWidth,
  setValue: (next) => layoutStore.setSidebarDrawerWidth(next),
  min: SIDEBAR_DRAWER_MIN_WIDTH,
  max: SIDEBAR_DRAWER_MAX_WIDTH,
})

const chatInput = ref('')
type ChatMessage = {
  role: 'user' | 'assistant'
  text: string
  widgetDrafts?: WidgetDraftResponse[]
}

const chatMessages = ref<ChatMessage[]>([
  { role: 'assistant', text: t('chat.greeting') }
])
const isThinking = ref(false)
const providerStatus = ref<AIStatus | null>(null)
const addedDraftKeys = ref<Record<string, boolean>>({})

async function refreshProviderStatus() {
  try {
    providerStatus.value = await aiStatus()
  } catch {
    providerStatus.value = null
  }
}
function stopActiveRealtime() {
  if (activeTab.value === 'audit') auditStore.stopPolling()
  if (activeTab.value === 'tickets') ticketsStore.stopRealtime()
}

function selectSurface(surface: MainSurface) {
  stopActiveRealtime()
  activeTab.value = 'none'
  emit('select-surface', surface)
}

function toggleTab(tab: 'assistant' | 'settings' | 'integrations' | 'audit' | 'workspaces' | 'tickets' | 'endpoints') {
  const isClosingCurrentTab = activeTab.value === tab
  if (activeTab.value === 'audit' && (isClosingCurrentTab || tab !== 'audit')) {
    auditStore.stopPolling()
  }
  if (activeTab.value === 'tickets' && (isClosingCurrentTab || tab !== 'tickets')) {
    ticketsStore.stopRealtime()
  }

  if (activeTab.value !== tab && tab === 'integrations') {
    integrationsStore.fetchIntegrations()
  }
  if (activeTab.value !== tab && tab === 'assistant' && assistantMode.value === 'chat') {
    refreshProviderStatus()
  }
  if (activeTab.value !== tab && tab === 'audit') {
    auditStore.startPolling({ scope: auditScope.value, limit: 50, intervalMs: 5000 })
  }
  if (activeTab.value !== tab && tab === 'workspaces') {
    store.refreshWorkspaceList()
  }
  if (activeTab.value !== tab && tab === 'tickets') {
    ticketsStore.startRealtime()
  }
  activeTab.value = isClosingCurrentTab ? 'none' : tab
}

function setAssistantMode(mode: 'chat' | 'agent') {
  if (assistantMode.value === mode) return
  assistantMode.value = mode
  if (mode === 'chat') refreshProviderStatus()
}

function refreshAuditTrail() {
  auditStore.fetchEvents({ scope: auditScope.value, limit: 50 })
}


onBeforeUnmount(() => {
  auditStore.stopPolling()
  ticketsStore.stopRealtime()
})

async function handleRemoveIntegration(integrationId: string) {
  integrationError.value = null
  const res = await integrationsStore.removeIntegration(integrationId)
  if (!res.success) {
    integrationError.value = res.error ?? 'Failed to remove integration'
  }
}

async function handleRunFortigateIngestion(integrationId: string) {
  integrationError.value = null
  const res = await integrationsStore.runFortigateIngestion(integrationId)
  if (!res.success) {
    integrationError.value = res.error ?? 'Failed to ingest FortiGate events'
  }
}

async function handleToggleFortigateIngestion(integrationId: string) {
  integrationError.value = null
  const current = fortigateIngestionStatus(integrationId)
  const res = await integrationsStore.configureFortigateIngestion(integrationId, {
    enabled: !current?.enabled,
    intervalSeconds: current?.intervalSeconds ?? 30,
  })
  if (!res.success) {
    integrationError.value = res.error ?? 'Failed to configure FortiGate ingestion'
  }
}

async function handleRotateFortiwebTelemetryToken(integrationId: string) {
  integrationError.value = null
  const res = await integrationsStore.rotateFortiwebTelemetryToken(integrationId)
  if (!res.success) {
    integrationError.value = res.error ?? 'Failed to rotate FortiWeb telemetry token'
    return
  }
  const token = res.data.telemetry.token
  if (token) fortiwebTelemetryTokens.value[integrationId] = token
}

function fortigateIngestionStatus(integrationId: string) {
  return integrationsStore.ingestionStatusById[integrationId]
}

function ingestionPipelineLabel(integrationId: string) {
  const status = fortigateIngestionStatus(integrationId)
  if (!status) return t('integrations.pipelineUnknown')
  return t('integrations.pipelineStatus', { status: status.status })
}

function toggleIntegrationGroup(group: keyof typeof integrationGroupsOpen.value) {
  integrationGroupsOpen.value[group] = !integrationGroupsOpen.value[group]
}

function integrationForCatalogItem(item: { source?: string, integrationType?: string }) {
  const integrationType = item.integrationType || item.source
  if (integrationType) {
    return integrationsStore.integrations.find(integration => integration.type === integrationType)
  }
  return integrationsStore.integrations[0]
}

function handleAddWidget(catalogId: string, integrationId?: string) {
  if (!integrationId) {
    const catalogItem = store.catalogItems.find(item => item.id === catalogId)
    const integration = catalogItem ? integrationForCatalogItem(catalogItem) : integrationsStore.integrations[0]
    integrationId = integration?.id
  }
  if (integrationId) {
    store.addWidget(catalogId, integrationId)
  }
}

function draftKey(messageIndex: number, draftIndex: number) {
  return `${messageIndex}:${draftIndex}`
}

function integrationForDraft(draft: WidgetDraftResponse) {
  const explicitIntegrationId = draft.draft.integrationId
    || draft.draft.fieldBindings.find(binding => binding.integrationId)?.integrationId
  if (explicitIntegrationId) {
    return integrationsStore.integrations.find(integration => integration.id === explicitIntegrationId)
  }
  const provider = draft.draft.provider === 'soc'
    ? draft.draft.fieldBindings[0]?.provider
    : draft.draft.provider
  return integrationsStore.integrations.find(integration => integration.type === provider)
}

function handleAddWidgetDraft(draft: WidgetDraftResponse, key: string) {
  const integration = integrationForDraft(draft)
  if (!integration) {
    chatMessages.value.push({
      role: 'assistant',
      text: t('chat.widgetDraftNeedsIntegration', { provider: draft.draft.provider }),
    })
    return
  }
  const widget = store.addWidgetDraft(draft.draft, integration.id)
  if (!widget) {
    chatMessages.value.push({
      role: 'assistant',
      text: t('chat.widgetDraftUnsupported', { visualType: draft.draft.visualType }),
    })
    return
  }
  addedDraftKeys.value[key] = true
  chatMessages.value.push({
    role: 'assistant',
    text: t('chat.widgetDraftAdded', { title: draft.draft.title }),
  })
}

async function handleLogout() {
  await authStore.logout()
  router.push({ name: 'login' })
}

// Catalog quick-add: if the user phrase is a literal match (English title,
// id-tail) or a known pt-BR alias for a widget preset, short-circuit before
// calling the real model so the demo flow stays fast and free.
// Anything else goes to the configured AI provider.
const CATALOG_ALIASES: Record<string, string> = {
  'incidentes recentes': 'soc-recent-incidents',
  'incidentes por severidade': 'soc-incidents-by-severity',
  'severidade dos incidentes': 'soc-incidents-by-severity',
  'top entidades': 'soc-top-entities',
  'principais entidades': 'soc-top-entities',
  'status do sistema': 'fortigate-system-status',
  'status sistema': 'fortigate-system-status',
  'tráfego de rede': 'fortigate-network-traffic',
  'trafego de rede': 'fortigate-network-traffic',
  'tráfego': 'fortigate-network-traffic',
  'políticas de firewall': 'fortigate-firewall-policies',
  'politicas de firewall': 'fortigate-firewall-policies',
  'políticas': 'fortigate-firewall-policies',
  'politicas': 'fortigate-firewall-policies',
  'top ameaças': 'fortigate-top-threats',
  'top ameacas': 'fortigate-top-threats',
  'ameaças': 'fortigate-top-threats',
  'ameacas': 'fortigate-top-threats',
  'eventos recentes': 'fortigate-recent-events',
  'postura de risco': 'fortigate-risk-posture',
  'saúde das interfaces': 'fortigate-interface-health',
  'saude das interfaces': 'fortigate-interface-health',
  'destaques de anomalias': 'fortigate-anomaly-highlights',
  'kpi de sessões': 'fortigate-kpi-sessions',
  'kpi de sessoes': 'fortigate-kpi-sessions',
  'saúde dos endpoints': 'xdr-endpoint-health',
  'saude dos endpoints': 'xdr-endpoint-health',
  'execuções de playbook': 'soar-active-playbook-runs',
  'execucoes de playbook': 'soar-active-playbook-runs',
  'histórico de playbook': 'soar-playbook-run-history',
  'historico de playbook': 'soar-playbook-run-history',
}

function resolveAliasCatalogId(lowerText: string): string | null {
  for (const [alias, catalogId] of Object.entries(CATALOG_ALIASES)) {
    if (lowerText.includes(alias)) return catalogId
  }
  return null
}

function tryCatalogShortcut(text: string): boolean {
  const lowerText = text.toLowerCase()

  // Step 1: pt-BR alias map wins (covers natural phrasing).
  const aliasId = resolveAliasCatalogId(lowerText)
  if (aliasId) {
    const item = store.catalogItems.find(c => c.id === aliasId)
    if (item) {
      const integration = integrationForCatalogItem(item) ?? integrationsStore.integrations[0]
      if (integration) {
        handleAddWidget(item.id, integration.id)
        chatMessages.value.push({ role: 'assistant', text: t('chat.widgetAdded', { title: item.title }) })
        return true
      }
    }
  }

  // Step 2: literal English title or id-tail substring match (legacy path).
  for (const item of store.catalogItems) {
    if (lowerText.includes(item.title.toLowerCase()) || lowerText.includes(item.id.split('-').pop() || '')) {
      const integration = integrationForCatalogItem(item) ?? integrationsStore.integrations[0]
      if (integration) {
        handleAddWidget(item.id, integration.id)
        chatMessages.value.push({ role: 'assistant', text: t('chat.widgetAdded', { title: item.title }) })
        return true
      }
    }
  }
  return false
}

async function handleChatSubmit() {
  if (!chatInput.value.trim()) return

  const text = chatInput.value
  chatMessages.value.push({ role: 'user', text })
  chatInput.value = ''

  if (integrationsStore.hasWorkspaceIntegrations && tryCatalogShortcut(text)) {
    return
  }

  isThinking.value = true
  try {
    const history = chatMessages.value.map((m) => ({
      role: m.role,
      content: m.text,
    }))
    const result = await aiChat(history)
    const reply = result.reply.trim() || t('chat.widgetNotFound')
    chatMessages.value.push({
      role: 'assistant',
      text: reply,
      widgetDrafts: result.widgetDrafts ?? [],
    })
  } catch (error: any) {
    chatMessages.value.push({
      role: 'assistant',
      text: error?.message ?? t('chat.error'),
    })
  } finally {
    isThinking.value = false
  }
}
</script>

<template>
  <div class="flex h-full relative z-50">
    <!-- Icon Bar -->
    <aside class="w-16 h-full bg-theme-panel flex flex-col items-center py-4 border-r border-theme-border shrink-0 z-20">
      <nav class="flex flex-col gap-4 flex-1">
        <div 
          class="p-3 rounded-lg cursor-pointer transition-colors"
          :class="activeTab === 'none' && props.activeSurface === 'workspace' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="selectSurface('workspace')"
          :title="t('sidebar.dashboard')"
        >
          <LayoutDashboard :size="20" />
        </div>

        <div
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'assistant' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('assistant')"
          :title="t('sidebar.assistant')"
          data-testid="sidebar-assistant-tab"
        >
          <Bot :size="20" />
        </div>

        <div
          v-if="authStore.hasPermission('integrations.write')"
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'integrations' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('integrations')"
          :title="t('sidebar.integrations')"
        >
          <Plug :size="20" />
        </div>

        <div
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'workspaces' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('workspaces')"
          :title="t('sidebar.workspaces')"
        >
          <FolderTree :size="20" />
        </div>

        <div
          v-if="authStore.hasPermission('tickets.manage')"
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'tickets' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('tickets')"
          :title="t('sidebar.tickets')"
        >
          <TicketIcon :size="20" />
        </div>

        <div
          v-if="authStore.isAdmin"
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'endpoints' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('endpoints')"
          :title="t('sidebar.endpoints')"
        >
          <Server :size="20" />
        </div>

        <div
          v-if="authStore.hasPermission('playbooks.execute')"
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'none' && props.activeSurface === 'playbooks' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="selectSurface('playbooks')"
          :title="t('sidebar.playbooks')"
        >
          <Workflow :size="20" />
        </div>

        <div
          v-if="authStore.hasPermission('audit.read')"
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'audit' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('audit')"
          :title="t('sidebar.audit')"
        >
          <History :size="20" />
        </div>
      </nav>
      
      <div class="mt-auto flex flex-col gap-2">
        <div
          class="p-3 rounded-lg hover:bg-theme-border cursor-pointer transition-colors relative text-theme-text-muted hover:text-theme-text"
          @click="$emit('open-settings')"
          :title="t('sidebar.settings')"
        >
          <Settings :size="20" />
        </div>
        <div @click="handleLogout" class="p-3 rounded-lg hover:bg-red-500/20 text-theme-text-muted hover:text-red-400 cursor-pointer transition-colors" :title="t('auth.logout')">
          <LogOut :size="20" />
        </div>
      </div>
    </aside>

    <!-- Drawer Panel -->
    <div
      class="h-full bg-theme-panel border-r border-theme-border flex flex-col overflow-hidden z-10"
      :class="{ 'transition-all duration-300': !drawerResizer.isDragging.value }"
      :style="{ width: drawerWidth, opacity: activeTab !== 'none' ? 1 : 0 }"
    >
      <!-- Assistant Tab (chat + agent unified) -->
      <div v-if="activeTab === 'assistant'" class="flex flex-col h-full shrink-0" :style="{ width: `${drawerPx}px` }">
        <div class="flex items-center justify-between gap-2 border-b border-theme-border px-4 pt-4 pb-2">
          <div class="inline-flex rounded-md border border-theme-border bg-theme-bg p-0.5">
            <button
              type="button"
              class="px-3 py-1 text-xs font-medium rounded transition-colors"
              :class="assistantMode === 'chat' ? 'bg-theme-primary/15 text-theme-primary' : 'text-theme-text-muted hover:text-theme-text'"
              data-testid="assistant-mode-chat"
              @click="setAssistantMode('chat')"
            >
              Chat
            </button>
            <button
              type="button"
              class="px-3 py-1 text-xs font-medium rounded transition-colors opacity-50 cursor-not-allowed flex items-center gap-1.5"
              data-testid="assistant-mode-agent"
              :title="t('chat.agentComingSoonTooltip')"
              disabled
            >
              Agente
              <span class="rounded-sm border border-amber-400/40 bg-amber-500/15 px-1 py-px text-[8px] uppercase tracking-wider text-amber-300">
                {{ t('chat.comingSoon') }}
              </span>
            </button>
          </div>
          <span
            v-if="assistantMode === 'chat' && providerStatus"
            class="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border"
            :class="providerStatus.ready
              ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300'
              : 'border-amber-500/40 bg-amber-500/15 text-amber-300'"
            :title="t('chat.providerTooltip', { provider: providerStatus.provider, model: providerStatus.model || '—' })"
          >
            {{ providerStatus.provider }}{{ providerStatus.model ? ` · ${providerStatus.model}` : '' }}
          </span>
        </div>

        <!-- Chat sub-mode -->
        <div v-if="assistantMode === 'chat'" class="p-4 flex flex-col flex-1 min-h-0">
        <div class="flex-1 overflow-y-auto flex flex-col gap-3 pr-2 mb-4">
          <div
            v-for="(msg, i) in chatMessages"
            :key="i"
            class="p-3 rounded-lg text-sm"
            :class="msg.role === 'user' ? 'bg-theme-primary/20 text-theme-text self-end ml-4' : 'bg-theme-border text-theme-text self-start mr-4'"
          >
            <div
              v-if="msg.role === 'assistant'"
              class="ai-markdown flex flex-col gap-1"
              v-html="renderMarkdown(msg.text)"
            />
            <p v-else class="whitespace-pre-wrap">{{ msg.text }}</p>
            <div v-if="msg.widgetDrafts?.length" class="mt-3 flex flex-col gap-2">
              <div
                v-for="(draft, draftIndex) in msg.widgetDrafts"
                :key="`${draft.draft.visualType}-${draft.draft.title}-${draftIndex}`"
                data-test="ai-widget-draft"
                class="rounded-lg border border-theme-primary/30 bg-theme-bg/80 p-3 text-xs text-theme-text"
              >
                <div class="mb-2 flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="text-[10px] font-semibold uppercase tracking-wider text-theme-text-muted">
                      {{ t('chat.widgetDraftLabel') }}
                    </p>
                    <h3 class="truncate text-sm font-semibold text-theme-text">{{ draft.draft.title }}</h3>
                    <p class="text-[11px] uppercase tracking-wider text-theme-text-muted">
                      {{ draft.draft.visualType }} · {{ draft.draft.provider }}
                    </p>
                  </div>
                  <span class="shrink-0 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300">
                    {{ t('chat.requiresConfirmation') }}
                  </span>
                </div>
                <div class="space-y-1">
                  <p class="text-[10px] font-semibold uppercase tracking-wider text-theme-text-muted">
                    {{ t('chat.draftFields') }}
                  </p>
                  <div
                    v-for="binding in draft.draft.fieldBindings"
                    :key="binding.fieldId"
                    class="rounded border border-theme-border bg-theme-panel/70 px-2 py-1"
                  >
                    <div class="font-medium text-theme-text">{{ binding.label }}</div>
                    <div class="text-[11px] text-theme-text-muted">{{ binding.fieldId }}</div>
                  </div>
                </div>
                <button
                  type="button"
                  data-test="ai-widget-draft-add"
                  class="mt-3 w-full rounded-md bg-theme-primary px-3 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="addedDraftKeys[draftKey(i, draftIndex)]"
                  @click="handleAddWidgetDraft(draft, draftKey(i, draftIndex))"
                >
                  {{ addedDraftKeys[draftKey(i, draftIndex)] ? t('chat.widgetDraftAddedButton') : t('chat.addWidgetDraft') }}
                </button>
              </div>
            </div>
          </div>
          <div v-if="isThinking" class="bg-theme-border text-theme-text-muted p-3 rounded-lg self-start text-xs italic animate-pulse">
            {{ t('chat.thinking') }}
          </div>
        </div>

        <form @submit.prevent="handleChatSubmit" class="mt-auto relative">
          <input
            v-model="chatInput"
            type="text"
            :placeholder="t('chat.inputPlaceholder')"
            class="w-full bg-theme-bg border border-theme-border rounded-lg pl-3 pr-10 py-2.5 text-sm focus:outline-none focus:border-theme-primary focus:ring-1 focus:ring-theme-primary text-theme-text"
            :disabled="isThinking"
          />
          <button
            type="submit"
            class="absolute right-2 top-2.5 text-theme-text-muted hover:text-theme-text disabled:opacity-50"
            :disabled="isThinking || !chatInput.trim()"
          >
            <Send :size="18" />
          </button>
        </form>
        </div>

        <!-- Agent sub-mode (multi-step tool-use) -->
        <div v-else-if="assistantMode === 'agent'" class="flex-1 min-h-0">
          <AgentPanel />
        </div>
      </div>

      <!-- Integrations Tab -->
      <div v-if="activeTab === 'integrations'" class="p-4 flex flex-col h-full shrink-0 overflow-y-auto" :style="{ width: `${drawerPx}px` }">
        <div class="mb-4">
          <h2 class="font-bold text-lg text-theme-text">{{ t('integrations.title') }}</h2>
          <p class="mt-1 text-xs text-theme-text-muted">
            {{ t('integrations.subtitle') }}
          </p>
        </div>

        <div v-if="integrationsStore.isLoading" class="mb-3 rounded border border-theme-border bg-theme-bg px-3 py-2 text-sm text-theme-text-muted">
          {{ t('integrations.loading') }}
        </div>

        <div v-if="integrationError" class="mb-3 rounded border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {{ integrationError }}
        </div>

        <div class="mb-4 flex flex-col gap-2">
          <button
            type="button"
            data-test="open-connect-wizard"
            class="rounded bg-theme-primary px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
            @click="showWizard = true"
          >
            {{ t('integrations.wizard.title') }}
          </button>
          <ConnectWizard
            v-if="showWizard"
            @close="showWizard = false"
            @open-marketplace="showWizard = false; emit('open-settings', 'marketplace')"
          />
        </div>

        <div class="flex flex-col gap-4">
          <section data-test="integration-group-fortinet" class="rounded-lg border border-theme-border bg-theme-bg/60 p-3">
            <button
              type="button"
              data-test="integration-toggle-fortinet"
              class="mb-3 flex w-full items-start justify-between gap-3 text-left"
              :aria-expanded="integrationGroupsOpen.fortinet ? 'true' : 'false'"
              @click="toggleIntegrationGroup('fortinet')"
            >
              <div class="flex min-w-0 gap-2">
                <component :is="integrationGroupsOpen.fortinet ? ChevronDown : ChevronRight" :size="15" class="mt-0.5 shrink-0 text-theme-text-muted" />
                <div class="min-w-0">
                  <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">{{ t('integrations.fortinetTitle') }}</h3>
                  <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                    {{ t('integrations.fortinetDescription') }}
                  </p>
                </div>
              </div>
              <span
                class="shrink-0 rounded border px-2 py-0.5 text-[10px] font-medium"
                :class="(fortigateIntegrations.length + fortiwebIntegrations.length) > 0 ? 'border-green-500/30 bg-green-500/20 text-green-400' : 'border-theme-border bg-theme-panel text-theme-text-muted'"
              >
                {{ (fortigateIntegrations.length + fortiwebIntegrations.length) > 0 ? t('integrations.connected') : t('integrations.notConnected') }}
              </span>
            </button>

            <div v-if="integrationGroupsOpen.fortinet" class="mb-3 flex flex-col gap-2">
              <div v-if="!integrationsStore.isLoading && fortigateIntegrations.length === 0 && fortiwebIntegrations.length === 0" class="rounded border border-dashed border-theme-border px-3 py-2 text-xs text-theme-text-muted">
                {{ t('integrations.noFortinet') }}
              </div>

              <div v-for="intg in fortigateIntegrations" :key="intg.id" class="rounded border border-theme-border bg-theme-panel p-3">
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <span class="block truncate text-sm font-medium text-theme-text">{{ intg.name }}</span>
                    <div v-if="intg.host" class="truncate font-mono text-xs text-theme-text-muted" :title="intg.host">
                      {{ intg.host }}
                    </div>
                    <div class="text-xs text-theme-text-muted">fortigate</div>
                  </div>
                  <div class="flex shrink-0 items-center gap-2">
                    <span class="rounded border border-green-500/30 bg-green-500/20 px-2 py-0.5 text-xs text-green-400">
                      {{ intg.status }}
                    </span>
                    <button
                      type="button"
                      class="rounded p-1 text-theme-text-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                      :disabled="integrationsStore.isDeleting[intg.id]"
                      :title="t('integrations.remove')"
                      @click="handleRemoveIntegration(intg.id)"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </div>
                </div>
                <div
                  class="mt-3 rounded border border-theme-border bg-theme-bg/70 p-2 text-xs text-theme-text-muted"
                  :data-test="`fortigate-ingestion-status-${intg.id}`"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="font-medium text-theme-text">{{ ingestionPipelineLabel(intg.id) }}</span>
                    <button
                      type="button"
                      class="rounded border border-theme-border p-1 text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="integrationsStore.isIngesting[intg.id]"
                      :data-test="`fortigate-ingest-run-${intg.id}`"
                      :title="t('integrations.runIngestion')"
                      @click="handleRunFortigateIngestion(intg.id)"
                    >
                      <RefreshCcw :size="13" :class="{ 'animate-spin': integrationsStore.isIngesting[intg.id] }" />
                    </button>
                  </div>
                  <div v-if="fortigateIngestionStatus(intg.id)" class="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                    <span>{{ t('integrations.rawEvents', { count: fortigateIngestionStatus(intg.id)?.lastRawEventCount ?? 0 }) }}</span>
                    <span>{{ t('integrations.createdEvents', { count: fortigateIngestionStatus(intg.id)?.lastCreatedCount ?? 0 }) }}</span>
                    <span v-if="fortigateIngestionStatus(intg.id)?.enabled">
                      {{ t('integrations.interval', { seconds: fortigateIngestionStatus(intg.id)?.intervalSeconds }) }}
                    </span>
                  </div>
                  <div v-if="fortigateIngestionStatus(intg.id)?.lastError" class="mt-1 text-red-400">
                    {{ fortigateIngestionStatus(intg.id)?.lastError }}
                  </div>
                  <button
                    type="button"
                    class="mt-2 rounded border border-theme-border px-2 py-1 text-[11px] font-medium text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text"
                    :data-test="`fortigate-ingest-toggle-${intg.id}`"
                    @click="handleToggleFortigateIngestion(intg.id)"
                  >
                    {{ fortigateIngestionStatus(intg.id)?.enabled ? t('integrations.disableScheduler') : t('integrations.enableScheduler') }}
                  </button>
                </div>
              </div>

              <div v-for="intg in fortiwebIntegrations" :key="intg.id" class="rounded border border-theme-border bg-theme-panel p-3">
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <span class="block truncate text-sm font-medium text-theme-text">{{ intg.name }}</span>
                    <div v-if="intg.host" class="truncate font-mono text-xs text-theme-text-muted" :title="intg.host">
                      {{ intg.host }}
                    </div>
                    <div class="text-xs text-theme-text-muted">fortiweb</div>
                  </div>
                  <div class="flex shrink-0 items-center gap-2">
                    <span class="rounded border border-green-500/30 bg-green-500/20 px-2 py-0.5 text-xs text-green-400">
                      {{ intg.status }}
                    </span>
                    <button
                      type="button"
                      class="rounded p-1 text-theme-text-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                      :disabled="integrationsStore.isDeleting[intg.id]"
                      :title="t('integrations.remove')"
                      @click="handleRemoveIntegration(intg.id)"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </div>
                </div>
                <div class="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <div class="rounded border border-theme-border bg-theme-bg/70 p-2">
                    <div class="text-theme-text-muted">{{ t('integrations.fortiweb.targetPolicy') }}</div>
                    <div class="mt-1 truncate font-mono text-theme-text">{{ intg.targetServerPolicy || '—' }}</div>
                  </div>
                  <div class="rounded border border-theme-border bg-theme-bg/70 p-2">
                    <div class="text-theme-text-muted">{{ t('integrations.fortiweb.ipListPolicy') }}</div>
                    <div class="mt-1 truncate font-mono text-theme-text">{{ intg.managedIpListPolicy || '—' }}</div>
                  </div>
                </div>
                <div v-if="intg.telemetry" class="mt-3 rounded border border-theme-border bg-theme-bg/70 p-2 text-xs">
                  <div class="flex items-center justify-between gap-2">
                    <div>
                      <div class="text-theme-text-muted">{{ t('integrations.fortiweb.telemetry') }}</div>
                      <div class="mt-1 font-medium text-theme-text">{{ intg.telemetry.status }}</div>
                    </div>
                    <button
                      type="button"
                      class="rounded p-1 text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text"
                      :title="t('integrations.fortiweb.rotateTelemetryToken')"
                      @click="handleRotateFortiwebTelemetryToken(intg.id)"
                    >
                      <RefreshCcw :size="13" />
                    </button>
                  </div>
                  <div class="mt-2 break-all font-mono text-[11px] text-theme-text-muted">
                    {{ intg.telemetry.endpointPath }}
                  </div>
                  <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-theme-text-muted">
                    <span>{{ t('integrations.fortiweb.telemetryEvents', { count: intg.telemetry.eventsReceived ?? 0 }) }}</span>
                    <span v-if="intg.telemetry.lastEventAt">{{ intg.telemetry.lastEventAt }}</span>
                  </div>
                  <div v-if="intg.telemetry.lastError" class="mt-1 text-red-400">
                    {{ intg.telemetry.lastError }}
                  </div>
                  <div v-if="fortiwebTelemetryTokens[intg.id]" class="mt-2 break-all rounded border border-green-500/30 bg-green-500/10 p-2 font-mono text-[11px] text-green-100">
                    {{ fortiwebTelemetryTokens[intg.id] }}
                  </div>
                </div>
              </div>
            </div>

            <h4 v-if="integrationGroupsOpen.fortinet" class="sr-only">{{ t('integrations.fortinetTitle') }}</h4>
          </section>

          <section data-test="integration-group-penguin" class="rounded-lg border border-theme-border bg-theme-bg/60 p-3">
            <button
              type="button"
              data-test="integration-toggle-penguin"
              class="mb-3 flex w-full items-start justify-between gap-3 text-left"
              :aria-expanded="integrationGroupsOpen.penguin ? 'true' : 'false'"
              @click="toggleIntegrationGroup('penguin')"
            >
              <div class="flex min-w-0 gap-2">
                <component :is="integrationGroupsOpen.penguin ? ChevronDown : ChevronRight" :size="15" class="mt-0.5 shrink-0 text-theme-text-muted" />
                <div class="min-w-0">
                  <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">{{ t('integrations.penguinTitle') }}</h3>
                  <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                    {{ t('integrations.penguinDescription') }}
                  </p>
                </div>
              </div>
              <span class="shrink-0 rounded border border-theme-border bg-theme-panel px-2 py-0.5 text-[10px] font-medium text-theme-text-muted">
                {{ t('integrations.connectedCount', { count: penguinIntegrations.length, total: 3 }) }}
              </span>
            </button>

            <div v-if="integrationGroupsOpen.penguin" class="grid grid-cols-1 gap-2">
              <div
                v-if="penguinIntegrations.length === 0"
                class="rounded border border-dashed border-theme-border px-3 py-2 text-xs text-theme-text-muted"
              >
                {{ t('integrations.notConnected') }}
              </div>
              <div
                v-for="integration in penguinIntegrations"
                :key="integration.id"
                class="rounded border border-theme-border bg-theme-panel p-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="text-sm font-medium text-theme-text">{{ integration.name }}</div>
                    <p class="mt-1 truncate font-mono text-xs leading-snug text-theme-text-muted">
                      {{ integration.host || integration.type }}
                    </p>
                  </div>
                  <div class="flex shrink-0 items-center gap-1">
                    <span
                      class="rounded border border-green-500/30 bg-green-500/20 px-2 py-0.5 text-[10px] font-medium text-green-400"
                    >
                      {{ t('integrations.connected') }}
                    </span>
                    <button
                      type="button"
                      class="rounded p-1 text-theme-text-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                      :disabled="integrationsStore.isDeleting[integration.id]"
                      :title="t('integrations.remove')"
                      @click="handleRemoveIntegration(integration.id)"
                    >
                      <Trash2 :size="13" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section data-test="integration-group-endpoint" class="rounded-lg border border-theme-border bg-theme-bg/60 p-3">
            <button
              type="button"
              data-test="integration-toggle-endpoint"
              class="flex w-full items-start justify-between gap-3 text-left"
              :class="integrationGroupsOpen.endpoint ? 'mb-3' : ''"
              :aria-expanded="integrationGroupsOpen.endpoint ? 'true' : 'false'"
              @click="toggleIntegrationGroup('endpoint')"
            >
              <div class="flex min-w-0 gap-2">
                <component :is="integrationGroupsOpen.endpoint ? ChevronDown : ChevronRight" :size="15" class="mt-0.5 shrink-0 text-theme-text-muted" />
                <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">{{ t('integrations.endpointTitle') }}</h3>
              </div>
              <span class="shrink-0 rounded border border-theme-border bg-theme-panel px-2 py-0.5 text-[10px] font-medium text-theme-text-muted">
                {{ t('integrations.endpointBadge') }}
              </span>
            </button>

            <div v-if="integrationGroupsOpen.endpoint" class="flex items-start justify-between gap-3">
              <div class="min-w-0 pl-6">
                <div class="mt-2 text-sm font-medium text-theme-text">agent_private</div>
                <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                  {{ t('integrations.endpointDescription') }}
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>

      <!-- Workspaces Tab -->
      <div v-if="activeTab === 'workspaces'" class="h-full shrink-0" :style="{ width: `${drawerPx}px` }">
        <WorkspacePanel />
      </div>

      <!-- Tickets Tab -->
      <div v-if="activeTab === 'tickets'" class="h-full shrink-0" :style="{ width: `${drawerPx}px` }">
        <TicketsPanel />
      </div>

      <!-- Endpoints Tab -->
      <div v-if="activeTab === 'endpoints'" class="h-full shrink-0" :style="{ width: `${drawerPx}px` }">
        <EndpointsPanel />
      </div>

      <!-- Audit Tab -->
      <div v-if="activeTab === 'audit'" class="h-full shrink-0 p-4" :style="{ width: `${drawerPx}px` }">
        <AuditFeed
          :events="auditStore.events"
          :is-loading="auditStore.isLoading"
          :error="auditStore.error"
          :title="auditTitle"
          :subtitle="auditSubtitle"
          @refresh="refreshAuditTrail"
        />
      </div>
    </div>

    <!-- Drawer resize handle (drag the right edge to grow the drawer) -->
    <div
      v-if="activeTab !== 'none'"
      data-test="sidebar-drawer-resizer"
      class="z-20 w-1 cursor-col-resize self-stretch bg-transparent hover:bg-theme-primary/40 transition-colors"
      :class="{ 'bg-theme-primary/60': drawerResizer.isDragging.value }"
      @pointerdown="drawerResizer.onPointerDown"
    />
  </div>
</template>
