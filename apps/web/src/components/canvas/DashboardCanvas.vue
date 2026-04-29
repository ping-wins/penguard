<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { useIntegrationsStore } from '../../stores/useIntegrationsStore'
import { useProviderDataStore } from '../../stores/useProviderDataStore'
import { storeToRefs } from 'pinia'
import { PanelRightClose, PanelRightOpen, Filter, BarChart2, Database, Folder, FolderOpen, Table, Activity, Network } from 'lucide-vue-next'
import DraggableWidget from './DraggableWidget.vue'
import WidgetHealth from '../widgets/WidgetHealth.vue'
import WidgetThreats from '../widgets/WidgetThreats.vue'
import WidgetNetwork from '../widgets/WidgetNetwork.vue'
import WidgetKpiCard from '../widgets/WidgetKpiCard.vue'
import WidgetFirewallPolicies from '../widgets/WidgetFirewallPolicies.vue'
import WidgetEmptyVisual from '../widgets/WidgetEmptyVisual.vue'
import { isVisualTemplateId, visualTemplates, type VisualTemplate } from '../../constants/visualTemplates'
import type { ProviderDataField } from '../../services/providerDataClient'

const dashboardStore = useDashboardStore()
const integrationsStore = useIntegrationsStore()
const providerDataStore = useProviderDataStore()
const { activeWidgets, workspaceName, catalogItems } = storeToRefs(dashboardStore)
const {
  groups: dataFieldGroups,
  isLoading: isDataFieldsLoading,
  error: dataFieldsError,
} = storeToRefs(providerDataStore)

onMounted(async () => {
  await integrationsStore.fetchIntegrations()
  if (integrationsStore.hasFortigate) {
    await loadFortigateBuildPaneData()
  }
  await dashboardStore.loadWorkspace()
})

watch(() => integrationsStore.hasFortigate, (has) => {
  if (has) {
    loadFortigateBuildPaneData()
  }
})

const isBuildPaneOpen = ref(true)
const activeBuildTab = ref<'filters' | 'visuals' | 'data'>('visuals')
const fortigateIntegrations = computed(() => integrationsStore.integrations.filter(i => i.type === 'fortigate'))
let buildPaneDataLoad: Promise<void> | null = null

const expandedFolders = ref<Record<string, boolean>>({
  'system': true
})

function toggleFolder(id: string) {
  expandedFolders.value[id] = !expandedFolders.value[id]
}

function handleAddWidget(catalogId: string) {
  const firstFortigate = integrationsStore.integrations.find(i => i.type === 'fortigate')
  if (firstFortigate) {
    dashboardStore.addWidget(catalogId, firstFortigate.id)
  }
}

async function loadFortigateBuildPaneData() {
  if (buildPaneDataLoad) return buildPaneDataLoad
  buildPaneDataLoad = (async () => {
    const tasks: Array<Promise<unknown>> = []
    if (!dashboardStore.isCatalogLoaded && dashboardStore.catalogItems.length === 0) {
      tasks.push(dashboardStore.fetchCatalog())
    }
    if (!providerDataStore.isLoaded && !providerDataStore.isLoading) {
      tasks.push(providerDataStore.fetchFortigateFields())
    }
    await Promise.all(tasks)
  })()
  try {
    await buildPaneDataLoad
  } finally {
    buildPaneDataLoad = null
  }
}

function handleAddVisualTemplate(templateId: string) {
  dashboardStore.addVisualTemplate(templateId)
}

// Map from catalogId to component
const widgetMap: Record<string, any> = {
  'fortigate-system-status': WidgetHealth,
  'fortigate-top-threats': WidgetThreats,
  'fortigate-network-traffic': WidgetNetwork,
  'fortigate-kpi-sessions': WidgetKpiCard,
  'fortigate-firewall-policies': WidgetFirewallPolicies
}

function getIconForKind(kind: string) {
  switch (kind) {
    case 'kpi': return Activity
    case 'table': return Table
    case 'chart': return Network
    case 'summary': return Activity
    case 'feed': return Table
    case 'status-list': return Network
    default: return BarChart2
  }
}

function getIconForTemplate(template: VisualTemplate) {
  switch (template.kind) {
    case 'card': return Activity
    case 'gauge': return Activity
    case 'table': return Table
    case 'bar': return BarChart2
    case 'line': return Network
    case 'feed': return Database
    case 'list': return Network
    default: return BarChart2
  }
}

function getWidgetComponent(catalogId: string) {
  if (isVisualTemplateId(catalogId)) return WidgetEmptyVisual
  return widgetMap[catalogId]
}

function fieldKey(field: string | { id: string }) {
  return typeof field === 'string' ? field : field.id
}

function fieldLabel(field: string | { label: string }) {
  return typeof field === 'string' ? field : field.label
}

function fieldTypeLabel(field: ProviderDataField) {
  return field.unit ? `${field.type} / ${field.unit}` : field.type
}

function handleWheel(e: WheelEvent) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const zoomSensitivity = 0.001
    const newZoom = dashboardStore.zoom - e.deltaY * zoomSensitivity
    dashboardStore.setZoom(Math.max(0.2, Math.min(newZoom, 3))) // Zoom entre 20% e 300%
  }
}
</script>

<template>
  <div class="flex-1 h-full overflow-hidden relative bg-theme-bg flex flex-col z-0">
    <!-- Header/Toolbar -->
    <header class="h-16 border-b border-theme-border flex items-center px-6 bg-theme-panel/50 backdrop-blur-sm z-40 relative shrink-0 justify-between">
      <h1 class="text-xl font-medium tracking-tight">{{ workspaceName }}</h1>
      
      <button 
        v-if="integrationsStore.hasFortigate"
        @click="isBuildPaneOpen = !isBuildPaneOpen" 
        class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
        :class="isBuildPaneOpen ? 'bg-theme-primary text-white' : 'bg-theme-border text-theme-text-muted hover:text-theme-text hover:bg-theme-text/10'"
      >
        <PanelRightOpen v-if="!isBuildPaneOpen" :size="18" />
        <PanelRightClose v-else :size="18" />
        Build Pane
      </button>
    </header>

    <div class="flex flex-1 overflow-hidden relative">
      <!-- Canvas Area -->
      <main class="flex-1 h-full relative overflow-auto bg-theme-bg no-scrollbar" @wheel="handleWheel">
        <div class="absolute inset-0 origin-top-left" :style="{ transform: `scale(${dashboardStore.zoom})`, width: `${100/dashboardStore.zoom}%`, height: `${100/dashboardStore.zoom}%` }">
          
          <!-- Grid Background -->
          <div class="absolute inset-0 z-0 opacity-10 pointer-events-none pattern-grid bg-fixed" 
               style="background-image: linear-gradient(#333 1px, transparent 1px), linear-gradient(90deg, #333 1px, transparent 1px); background-size: 80px 80px;">
          </div>
          
          <DraggableWidget
            v-for="widget in activeWidgets"
            :key="widget.instanceId"
            :instance-id="widget.instanceId"
            :catalog-id="widget.catalogId"
            :integration-id="widget.integrationId"
            :layout="widget.layout"
            v-slot="{ widgetData }"
          >
            <component
              :is="getWidgetComponent(widget.catalogId)"
              v-if="getWidgetComponent(widget.catalogId)"
              :data="widgetData"
              :catalog-id="widget.catalogId"
            />
            <div v-else class="text-gray-500 text-sm flex h-full items-center justify-center">
              Component not found for {{ widget.catalogId }}
            </div>
          </DraggableWidget>
        </div>
      </main>

      <!-- Build Pane (Power BI style) -->
      <aside 
        v-if="integrationsStore.hasFortigate"
        class="h-full bg-theme-panel border-l border-theme-border transition-all duration-300 flex flex-col z-30 shrink-0"
        :style="{ width: isBuildPaneOpen ? '300px' : '0px', opacity: isBuildPaneOpen ? 1 : 0 }"
      >
        <!-- Tabs Header -->
        <div class="flex border-b border-theme-border w-[300px] shrink-0">
          <button 
            @click="activeBuildTab = 'filters'"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'filters' ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
          >
            <Filter :size="14" /> Filters
          </button>
          <button 
            @click="activeBuildTab = 'visuals'"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'visuals' ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
          >
            <BarChart2 :size="14" /> Visuals
          </button>
          <button 
            @click="activeBuildTab = 'data'"
            data-test="build-tab-data"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'data' ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
          >
            <Database :size="14" /> Data
          </button>
        </div>

        <div class="flex-1 overflow-y-auto w-[300px] shrink-0">
          <!-- Filters Tab -->
          <div v-if="activeBuildTab === 'filters'" class="p-4 flex flex-col gap-6">
            <div class="flex flex-col gap-2">
              <label class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Time Range</label>
              <select class="w-full bg-theme-bg border border-theme-border rounded p-2 text-sm text-theme-text outline-none">
                <option>Last 1 hour</option>
                <option selected>Last 24 hours</option>
                <option>Last 7 days</option>
                <option>This month</option>
              </select>
            </div>
            
            <div class="flex flex-col gap-2">
              <label class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Device</label>
              <select class="w-full bg-theme-bg border border-theme-border rounded p-2 text-sm text-theme-text outline-none">
                <option value="all">All Devices</option>
                <option
                  v-for="integration in fortigateIntegrations"
                  :key="integration.id"
                  :value="integration.id"
                >
                  {{ integration.name || integration.host || integration.id }}
                </option>
              </select>
            </div>
            
            <div class="mt-4 pt-4 border-t border-theme-border">
              <button class="w-full bg-theme-border hover:opacity-80 text-theme-text rounded py-2 text-sm font-medium transition-colors">
                Apply Filters
              </button>
            </div>
          </div>

          <!-- Visualizations Tab -->
          <div v-if="activeBuildTab === 'visuals'" class="p-4 flex flex-col gap-4">
            <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">FortiGate presets</h3>
            <div class="grid grid-cols-2 gap-2">
              <div 
                v-for="item in catalogItems" 
                :key="item.id"
                @click="handleAddWidget(item.id)"
                class="bg-theme-bg border border-theme-border p-3 rounded hover:border-theme-primary/50 hover:bg-theme-border transition-colors flex flex-col items-center justify-center gap-2 cursor-pointer group text-center"
                :title="item.title"
              >
                <component :is="getIconForKind(item.kind)" :size="24" class="text-theme-text-muted group-hover:text-theme-primary transition-colors" />
                <span class="text-[10px] leading-tight font-medium text-theme-text-muted group-hover:text-theme-text">{{ item.title }}</span>
              </div>
            </div>

            <div class="mt-2 border-t border-theme-border pt-4">
              <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Criar dados ao seu visual</h3>
              <div class="mt-3 grid grid-cols-2 gap-2">
                <div
                  v-for="template in visualTemplates"
                  :key="template.id"
                  class="bg-theme-bg border border-dashed border-theme-border p-3 rounded hover:border-theme-primary/50 hover:bg-theme-border transition-colors flex flex-col items-center justify-center gap-2 cursor-pointer group text-center"
                  :title="template.description"
                  :data-test="`visual-template-${template.id}`"
                  @click="handleAddVisualTemplate(template.id)"
                >
                  <component :is="getIconForTemplate(template)" :size="23" class="text-theme-text-muted group-hover:text-theme-primary transition-colors" />
                  <span class="text-[10px] leading-tight font-medium text-theme-text-muted group-hover:text-theme-text">{{ template.title }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Data Tab -->
          <div v-if="activeBuildTab === 'data'" class="p-4 flex flex-col gap-2">
            <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider mb-2">Available Fields</h3>

            <div v-if="isDataFieldsLoading" class="rounded border border-theme-border bg-theme-bg p-3 text-sm text-theme-text-muted">
              Loading FortiGate fields...
            </div>
            <div v-else-if="dataFieldsError" class="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
              {{ dataFieldsError }}
            </div>
            <div v-else-if="dataFieldGroups.length === 0" class="rounded border border-theme-border bg-theme-bg p-3 text-sm text-theme-text-muted">
              No provider fields available.
            </div>
            
            <template v-else>
              <div v-for="group in dataFieldGroups" :key="group.id" class="flex flex-col">
                <div 
                  class="flex items-center gap-2 p-2 hover:bg-theme-border rounded cursor-pointer transition-colors text-sm text-theme-text"
                  @click="toggleFolder(group.id)"
                >
                  <FolderOpen v-if="expandedFolders[group.id]" :size="16" class="text-amber-500" />
                  <Folder v-else :size="16" class="text-amber-500" />
                  <span class="font-medium">{{ group.name }}</span>
                </div>

                <div v-if="expandedFolders[group.id]" class="flex flex-col ml-6 pl-2 border-l border-theme-border py-1 gap-1">
                  <div
                    v-for="field in group.fields"
                    :key="fieldKey(field)"
                    class="flex flex-col gap-1 p-1.5 text-xs text-theme-text-muted hover:text-theme-text cursor-pointer hover:bg-theme-border/50 rounded transition-colors"
                    :title="field.source"
                  >
                    <div class="flex items-center gap-2">
                      <Database :size="12" class="opacity-50" />
                      <span class="min-w-0 flex-1 truncate">{{ fieldLabel(field) }}</span>
                      <span class="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-300">Live</span>
                    </div>
                    <div class="ml-5 flex items-center gap-2 text-[10px] text-theme-text-muted">
                      <span>{{ fieldTypeLabel(field) }}</span>
                      <span class="truncate">{{ field.source }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
