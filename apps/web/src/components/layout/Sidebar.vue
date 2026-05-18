<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Bot, ChevronDown, ChevronRight, LayoutDashboard, Settings, LogOut, Plug, Trash2, History, FolderTree, Ticket as TicketIcon, Server, RefreshCcw, Workflow } from 'lucide-vue-next'
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
import AuditFeed from '../audit/AuditFeed.vue'
import AgentPanel from '../ai/AgentPanel.vue'
import WorkspacePanel from '../workspace/WorkspacePanel.vue'
import TicketsPanel from '../tickets/TicketsPanel.vue'
import EndpointsPanel from '../endpoints/EndpointsPanel.vue'
import PlaybooksPanel from '../playbooks/PlaybooksPanel.vue'
import ConnectWizard from '../integrations/ConnectWizard.vue'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const emit = defineEmits<{ 'open-settings': [tab?: 'profile' | 'marketplace'] }>()

const store = useDashboardStore()
const authStore = useAuthStore()
const integrationsStore = useIntegrationsStore()
const auditStore = useAuditStore()
const ticketsStore = useTicketsStore()
const layoutStore = useCockpitLayoutStore()
const router = useRouter()
const activeTab = ref<'none' | 'assistant' | 'settings' | 'integrations' | 'audit' | 'workspaces' | 'tickets' | 'endpoints' | 'playbooks'>('none')

const showWizard = ref(false)
const integrationError = ref<string | null>(null)
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

function toggleTab(tab: 'assistant' | 'settings' | 'integrations' | 'audit' | 'workspaces' | 'tickets' | 'endpoints' | 'playbooks') {
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

async function handleLogout() {
  await authStore.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="flex h-full relative z-50">
    <!-- Icon Bar -->
    <aside class="w-16 h-full bg-theme-panel flex flex-col items-center py-4 border-r border-theme-border shrink-0 z-20">
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
          :class="activeTab === 'playbooks' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('playbooks')"
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
      <!-- Assistant Tab -->
      <div v-if="activeTab === 'assistant'" class="flex flex-col h-full shrink-0" :style="{ width: `${drawerPx}px` }">
        <div class="flex-1 min-h-0">
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

      <!-- Playbooks Tab -->
      <div v-if="activeTab === 'playbooks'" class="h-full shrink-0" :style="{ width: `${drawerPx}px` }">
        <PlaybooksPanel />
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
