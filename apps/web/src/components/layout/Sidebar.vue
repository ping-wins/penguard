<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ChevronDown, ChevronRight, LayoutDashboard, Settings, Menu, MessageSquare, Send, LogOut, Plug, Trash2, History, FolderTree, Ticket as TicketIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { useAuthStore } from '../../stores/useAuthStore'
import { useIntegrationsStore } from '../../stores/useIntegrationsStore'
import { useAuditStore } from '../../stores/useAuditStore'
import { useTicketsStore } from '../../stores/useTicketsStore'
import AuditFeed from '../audit/AuditFeed.vue'
import WorkspacePanel from '../workspace/WorkspacePanel.vue'
import TicketsPanel from '../tickets/TicketsPanel.vue'
import { useRouter } from 'vue-router'
import type { PenguinToolType } from '../../stores/useIntegrationsStore'

const { t } = useI18n()
const emit = defineEmits<{ 'open-settings': [] }>()

const store = useDashboardStore()
const authStore = useAuthStore()
const integrationsStore = useIntegrationsStore()
const auditStore = useAuditStore()
const ticketsStore = useTicketsStore()
const router = useRouter()
const activeTab = ref<'none' | 'chat' | 'settings' | 'integrations' | 'audit' | 'workspaces' | 'tickets'>('none')

const fgForm = ref({
  name: 'FortiGate Lab',
  host: 'https://fortigate.local',
  apiKey: '',
  verifyTls: false
})
const fgTestResult = ref<any>(null)
const fgTestError = ref<string | null>(null)
const penguinTestResults = ref<Record<PenguinToolType, any | null>>({
  siem_kowalski: null,
  xdr_rico: null,
  soar_skipper: null,
})
const penguinErrors = ref<Record<PenguinToolType, string | null>>({
  siem_kowalski: null,
  xdr_rico: null,
  soar_skipper: null,
})
const integrationGroupsOpen = ref({
  fortinet: true,
  penguin: true,
  endpoint: false,
})
const penguinTools: Array<{
  type: PenguinToolType
  title: string
  description: string
  defaultName: string
}> = [
  {
    type: 'siem_kowalski',
    title: 'Kowalski SIEM-lite',
    description: 'Events, detections, incidents and investigation widgets.',
    defaultName: 'Kowalski SIEM',
  },
  {
    type: 'xdr_rico',
    title: 'XDR/EDR-lite manager',
    description: 'Endpoint inventory, heartbeat and timeline widgets.',
    defaultName: 'Rico XDR',
  },
  {
    type: 'soar_skipper',
    title: 'SOAR-lite workflows',
    description: 'Playbooks, dry-run response and approval widgets.',
    defaultName: 'Skipper SOAR',
  },
]
const canSubmitFortigate = computed(() => {
  return fgForm.value.host.trim().length > 0 && fgForm.value.apiKey.trim().length > 0
})
const fortigateIntegrations = computed(() => {
  return integrationsStore.integrations.filter(integration => integration.type === 'fortigate')
})
const isAdmin = computed(() => authStore.user?.roles.includes('admin') ?? false)
const auditScope = computed<'admin' | 'mine'>(() => isAdmin.value ? 'admin' : 'mine')
const auditTitle = computed(() => isAdmin.value ? t('audit.adminTitle') : t('audit.mineTitle'))
const auditSubtitle = computed(() => isAdmin.value ? t('audit.adminSubtitle') : t('audit.mineSubtitle'))
const drawerWidth = computed(() => {
  if (activeTab.value === 'none') return '0px'
  if (activeTab.value === 'audit') return '420px'
  if (activeTab.value === 'integrations') return '380px'
  if (activeTab.value === 'workspaces') return '420px'
  if (activeTab.value === 'tickets') return '480px'
  return '320px'
})

const chatInput = ref('')
const chatMessages = ref<{role: 'user' | 'assistant', text: string}[]>([
  { role: 'assistant', text: t('chat.greeting') }
])
const isThinking = ref(false)
function toggleTab(tab: 'chat' | 'settings' | 'integrations' | 'audit' | 'workspaces' | 'tickets') {
  const isClosingCurrentTab = activeTab.value === tab
  if (activeTab.value === 'audit' && (isClosingCurrentTab || tab !== 'audit')) {
    auditStore.stopPolling()
  }
  if (activeTab.value === 'tickets' && (isClosingCurrentTab || tab !== 'tickets')) {
    ticketsStore.stopPolling()
  }

  if (activeTab.value !== tab && tab === 'integrations') {
    integrationsStore.fetchIntegrations()
  }
  if (activeTab.value !== tab && tab === 'audit') {
    auditStore.startPolling({ scope: auditScope.value, limit: 50, intervalMs: 5000 })
  }
  if (activeTab.value !== tab && tab === 'workspaces') {
    store.refreshWorkspaceList()
  }
  if (activeTab.value !== tab && tab === 'tickets') {
    ticketsStore.startPolling(8000)
  }
  activeTab.value = isClosingCurrentTab ? 'none' : tab
}

function refreshAuditTrail() {
  auditStore.fetchEvents({ scope: auditScope.value, limit: 50 })
}

onBeforeUnmount(() => {
  auditStore.stopPolling()
  ticketsStore.stopPolling()
})

async function handleTestFortigate() {
  fgTestResult.value = null
  fgTestError.value = null
  const res = await integrationsStore.testFortigate(fgForm.value.host, fgForm.value.apiKey, fgForm.value.verifyTls)
  if (res.success) {
    fgTestResult.value = res.data
  } else {
    fgTestError.value = res.error ?? 'Connection failed'
  }
}

async function handleSaveFortigate() {
  const res = await integrationsStore.addFortigate(fgForm.value.name, fgForm.value.host, fgForm.value.apiKey, fgForm.value.verifyTls)
  if (res.success) {
    fgTestResult.value = null
    fgTestError.value = null
    fgForm.value.apiKey = ''
  } else {
    fgTestError.value = res.error ?? 'Failed to add integration'
  }
}

async function handleRemoveIntegration(integrationId: string) {
  fgTestError.value = null
  const res = await integrationsStore.removeIntegration(integrationId)
  if (!res.success) {
    fgTestError.value = res.error ?? 'Failed to remove integration'
  }
}

function connectedPenguinTool(type: PenguinToolType) {
  return integrationsStore.integrations.find(integration => integration.type === type)
}

function toggleIntegrationGroup(group: keyof typeof integrationGroupsOpen.value) {
  integrationGroupsOpen.value[group] = !integrationGroupsOpen.value[group]
}

async function handleTestPenguinTool(type: PenguinToolType) {
  penguinTestResults.value[type] = null
  penguinErrors.value[type] = null
  const res = await integrationsStore.testPenguinTool(type)
  if (res.success) {
    penguinTestResults.value[type] = res.data
  } else {
    penguinErrors.value[type] = res.error ?? 'Connection failed'
  }
}

async function handleAddPenguinTool(type: PenguinToolType, name: string) {
  penguinErrors.value[type] = null
  const res = await integrationsStore.addPenguinTool(type, name)
  if (res.success) {
    penguinTestResults.value[type] = res.data
  } else {
    penguinErrors.value[type] = res.error ?? 'Failed to add integration'
  }
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

async function handleLogout() {
  await authStore.logout()
  router.push({ name: 'login' })
}

function handleChatSubmit() {
  if (!chatInput.value.trim()) return
  
  const text = chatInput.value
  chatMessages.value.push({ role: 'user', text })
  chatInput.value = ''
  isThinking.value = true
  
  setTimeout(() => {
    isThinking.value = false

    if (!integrationsStore.hasWorkspaceIntegrations) {
      chatMessages.value.push({ role: 'assistant', text: t('chat.integrationRequired') })
      return
    }

    // NLP MOCK logic
    const lowerText = text.toLowerCase()
    let found = false
    for (const item of store.catalogItems) {
      if (lowerText.includes(item.title.toLowerCase()) || lowerText.includes(item.id.split('-').pop() || '')) {
        const integration = integrationForCatalogItem(item)
        if (integration) {
          handleAddWidget(item.id, integration.id)
          chatMessages.value.push({ role: 'assistant', text: t('chat.widgetAdded', { title: item.title }) })
          found = true
        }
        break
      }
    }

    if (!found) {
      chatMessages.value.push({ role: 'assistant', text: t('chat.widgetNotFound') })
    }
  }, 1000)
}
</script>

<template>
  <div class="flex h-full relative z-50">
    <!-- Icon Bar -->
    <aside class="w-16 h-full bg-theme-panel flex flex-col items-center py-4 border-r border-theme-border shrink-0 z-20">
      <div class="mb-8 cursor-pointer hover:opacity-80 text-theme-text transition-colors">
        <Menu :size="24" />
      </div>
      
      <nav class="flex flex-col gap-4 flex-1">
        <div 
          class="p-3 rounded-lg cursor-pointer transition-colors"
          :class="activeTab === 'none' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="activeTab = 'none'"
          :title="t('sidebar.dashboard')"
        >
          <LayoutDashboard :size="20" />
        </div>

        <div
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'chat' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('chat')"
          :title="t('sidebar.assistant')"
        >
          <MessageSquare :size="20" />
        </div>

        <div
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
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'tickets' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('tickets')"
          :title="t('sidebar.tickets')"
        >
          <TicketIcon :size="20" />
        </div>

        <div
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
      class="h-full bg-theme-panel border-r border-theme-border flex flex-col transition-all duration-300 overflow-hidden z-10"
      :style="{ width: drawerWidth, opacity: activeTab !== 'none' ? 1 : 0 }"
    >
      <!-- Chat Tab -->
      <div v-if="activeTab === 'chat'" class="p-4 flex flex-col h-full w-[320px] shrink-0">
        <h2 class="font-bold text-lg mb-4 text-theme-text">{{ t('chat.header') }}</h2>

        <div class="flex-1 overflow-y-auto flex flex-col gap-3 pr-2 mb-4">
          <div
            v-for="(msg, i) in chatMessages"
            :key="i"
            class="p-3 rounded-lg text-sm"
            :class="msg.role === 'user' ? 'bg-theme-primary/20 text-theme-text self-end ml-4' : 'bg-theme-border text-theme-text self-start mr-4'"
          >
            {{ msg.text }}
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

      <!-- Integrations Tab -->
      <div v-if="activeTab === 'integrations'" class="p-4 flex flex-col h-full w-[380px] shrink-0 overflow-y-auto">
        <div class="mb-4">
          <h2 class="font-bold text-lg text-theme-text">Integrações SOC</h2>
          <p class="mt-1 text-xs text-theme-text-muted">
            Connect live providers first; SOC-lite tools unlock their own workspace widgets.
          </p>
        </div>

        <div v-if="integrationsStore.isLoading" class="mb-3 rounded border border-theme-border bg-theme-bg px-3 py-2 text-sm text-theme-text-muted">
          Carregando integrações...
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
                  <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">Fortinet Providers</h3>
                  <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                    Real read-only FortiGate access for live firewall telemetry.
                  </p>
                </div>
              </div>
              <span
                class="shrink-0 rounded border px-2 py-0.5 text-[10px] font-medium"
                :class="fortigateIntegrations.length > 0 ? 'border-green-500/30 bg-green-500/20 text-green-400' : 'border-theme-border bg-theme-panel text-theme-text-muted'"
              >
                {{ fortigateIntegrations.length > 0 ? 'Connected' : 'Not connected' }}
              </span>
            </button>

            <div v-if="integrationGroupsOpen.fortinet" class="mb-3 flex flex-col gap-2">
              <div v-if="!integrationsStore.isLoading && fortigateIntegrations.length === 0" class="rounded border border-dashed border-theme-border px-3 py-2 text-xs text-theme-text-muted">
                No Fortinet provider connected.
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
                      title="Remover integração"
                      @click="handleRemoveIntegration(intg.id)"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="integrationGroupsOpen.fortinet" class="grid grid-cols-2 gap-2">
              <div class="flex flex-col gap-1">
                <label class="text-xs text-theme-text">Nome</label>
                <input v-model="fgForm.name" type="text" class="w-full rounded border border-theme-border bg-theme-panel px-2 py-1.5 text-sm text-theme-text outline-none focus:border-theme-primary" />
              </div>

              <div class="flex flex-col gap-1">
                <label class="text-xs text-theme-text">Host (URL)</label>
                <input v-model="fgForm.host" type="text" class="w-full rounded border border-theme-border bg-theme-panel px-2 py-1.5 text-sm text-theme-text outline-none focus:border-theme-primary" />
              </div>

              <div class="col-span-2 flex flex-col gap-1">
                <label class="text-xs text-theme-text">API Key</label>
                <input v-model="fgForm.apiKey" type="password" class="w-full rounded border border-theme-border bg-theme-panel px-2 py-1.5 text-sm text-theme-text outline-none focus:border-theme-primary" />
              </div>

              <label class="col-span-2 flex cursor-pointer items-center gap-2">
                <input v-model="fgForm.verifyTls" type="checkbox" class="rounded border-theme-border bg-theme-bg" />
                <span class="text-xs text-theme-text">Verificar TLS/SSL</span>
              </label>

              <div v-if="fgTestResult" class="col-span-2 rounded border border-green-500/20 bg-green-500/10 p-2 text-xs">
                <div class="mb-1 font-medium text-green-400">Conexão bem-sucedida!</div>
                <div class="text-theme-text-muted">Hostname: {{ fgTestResult.device?.hostname }}</div>
                <div class="text-theme-text-muted">Modelo: {{ fgTestResult.device?.model }}</div>
              </div>

              <div v-if="fgTestError" class="col-span-2 rounded border border-red-500/20 bg-red-500/10 p-2 text-xs text-red-400">
                {{ fgTestError }}
              </div>

              <div class="col-span-2 flex gap-2">
                <button
                  @click="handleTestFortigate"
                  class="flex-1 rounded border border-theme-border px-3 py-1.5 text-sm font-medium text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text disabled:opacity-50"
                  :disabled="integrationsStore.isTesting || !canSubmitFortigate"
                >
                  <span v-if="integrationsStore.isTesting">Testando...</span>
                  <span v-else>Testar Conexão</span>
                </button>
                <button
                  @click="handleSaveFortigate"
                  class="flex-1 rounded bg-theme-primary px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                  :disabled="!canSubmitFortigate"
                >
                  Salvar
                </button>
              </div>
            </div>

            <h4 v-if="integrationGroupsOpen.fortinet" class="sr-only">Adicionar FortiGate</h4>
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
                  <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">Penguin SOC Lite</h3>
                  <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                    Penguin tools connected through the BFF.
                  </p>
                </div>
              </div>
              <span class="shrink-0 rounded border border-theme-border bg-theme-panel px-2 py-0.5 text-[10px] font-medium text-theme-text-muted">
                {{ penguinTools.filter(tool => connectedPenguinTool(tool.type)).length }}/{{ penguinTools.length }} connected
              </span>
            </button>

            <div v-if="integrationGroupsOpen.penguin" class="grid grid-cols-1 gap-2">
              <div
                v-for="tool in penguinTools"
                :key="tool.type"
                class="rounded border border-theme-border bg-theme-panel p-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="text-sm font-medium text-theme-text">{{ tool.title }}</div>
                    <p class="mt-1 text-xs leading-snug text-theme-text-muted">{{ tool.description }}</p>
                  </div>
                  <div class="flex shrink-0 items-center gap-1">
                    <span
                      v-if="connectedPenguinTool(tool.type)"
                      class="rounded border border-green-500/30 bg-green-500/20 px-2 py-0.5 text-[10px] font-medium text-green-400"
                    >
                      Connected
                    </span>
                    <button
                      v-if="connectedPenguinTool(tool.type)"
                      type="button"
                      class="rounded p-1 text-theme-text-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                      :disabled="integrationsStore.isDeleting[connectedPenguinTool(tool.type)?.id || '']"
                      title="Remover integração"
                      @click="handleRemoveIntegration(connectedPenguinTool(tool.type)?.id || '')"
                    >
                      <Trash2 :size="13" />
                    </button>
                  </div>
                </div>

                <div v-if="connectedPenguinTool(tool.type)" class="mt-2 text-xs text-theme-text-muted">
                  Connected as {{ connectedPenguinTool(tool.type)?.name || connectedPenguinTool(tool.type)?.id }}
                </div>

                <div v-if="penguinTestResults[tool.type] && !connectedPenguinTool(tool.type)" class="mt-2 rounded border border-green-500/20 bg-green-500/10 p-2 text-xs">
                  <div class="font-medium text-green-400">Service reachable</div>
                  <div class="text-theme-text-muted">
                    {{ penguinTestResults[tool.type]?.status || 'connected' }}
                  </div>
                </div>

                <div v-if="penguinErrors[tool.type]" class="mt-2 rounded border border-red-500/20 bg-red-500/10 p-2 text-xs text-red-400">
                  {{ penguinErrors[tool.type] }}
                </div>

                <div class="mt-3 flex gap-2">
                  <button
                    type="button"
                    class="flex-1 rounded border border-theme-border px-2 py-1.5 text-xs font-medium text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text disabled:opacity-50"
                    :disabled="integrationsStore.isTesting"
                    :data-test="`penguin-test-${tool.type}`"
                    @click="handleTestPenguinTool(tool.type)"
                  >
                    Test
                  </button>
                  <button
                    type="button"
                    class="flex-1 rounded bg-theme-primary px-2 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                    :disabled="Boolean(connectedPenguinTool(tool.type))"
                    :data-test="`penguin-connect-${tool.type}`"
                    @click="handleAddPenguinTool(tool.type, tool.defaultName)"
                  >
                    Connect
                  </button>
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
                <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">Endpoint Sensor / Future</h3>
              </div>
              <span class="shrink-0 rounded border border-theme-border bg-theme-panel px-2 py-0.5 text-[10px] font-medium text-theme-text-muted">
                Future onboarding
              </span>
            </button>

            <div v-if="integrationGroupsOpen.endpoint" class="flex items-start justify-between gap-3">
              <div class="min-w-0 pl-6">
                <div class="mt-2 text-sm font-medium text-theme-text">agent_private</div>
                <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                  Lab endpoint sensor for future onboarding into xdr_rico. It is not a dashboard integration yet.
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>

      <!-- Workspaces Tab -->
      <div v-if="activeTab === 'workspaces'" class="h-full w-[420px] shrink-0">
        <WorkspacePanel />
      </div>

      <!-- Tickets Tab -->
      <div v-if="activeTab === 'tickets'" class="h-full w-[480px] shrink-0">
        <TicketsPanel />
      </div>

      <!-- Audit Tab -->
      <div v-if="activeTab === 'audit'" class="h-full w-[420px] shrink-0 p-4">
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
  </div>
</template>
